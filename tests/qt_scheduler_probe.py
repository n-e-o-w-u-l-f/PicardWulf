"""Real Qt S1 load probe, run separately from tests that mock PyQt6.

Uses only synthetic identities and a temporary database. No network/media I/O.
Run: QT_QPA_PLATFORM=offscreen python tests/qt_scheduler_probe.py
"""
from collections import deque
import importlib
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
import tracemalloc
import types
from unittest.mock import patch
from concurrent.futures import Future

from PyQt6.QtCore import QCoreApplication, QObject, QTimer

ROOT=Path(__file__).parents[1]
pkg=types.ModuleType('qt_probe')
pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules['qt_probe']=pkg
engine=importlib.import_module('qt_probe.universal_engine')
auto=importlib.import_module('qt_probe.auto_apply')
workflow=importlib.import_module('qt_probe.native_workflow')


class File:
    def __init__(self,index):
        self.filename=f'synthetic/{index}.flac'
        self.metadata={'artist':'Synthetic','title':str(index),'album':'Album'}


def percentile(values,percent):
    return sorted(values)[min(len(values)-1,int(len(values)*percent/100))]


def run():
    app=QCoreApplication.instance() or QCoreApplication([])
    owner=threading.get_ident()
    api=types.SimpleNamespace(tagger=QObject(),plugin_config={'auto_apply_best':False},
                             logger=types.SimpleNamespace(info=lambda *a:None,
                                                          warning=lambda *a:None,error=lambda *a:None))
    files=[File(i) for i in range(39000)]
    with tempfile.TemporaryDirectory() as directory:
        store=engine.ResultStore(Path(directory)/'queue.db')
        for offset in range(0,29000,256):
            entries=[]
            for file in files[offset:min(offset+256,29000)]:
                q=engine.clean_track(file.metadata)
                entries.append((engine.query_key(q),q,False))
            store.enqueue_many(entries)
        connect=sqlite3.connect
        violations=[]
        def checked_connect(*args,**kwargs):
            if threading.get_ident()==owner:violations.append('SQLite GUI connection')
            return connect(*args,**kwargs)
        tracemalloc.start()
        baseline=tracemalloc.get_traced_memory()[0]
        with patch.object(engine.sqlite3,'connect',checked_connect):
            runner=engine.UniversalAggregator(store=store,credentials={},paused=True)
            controller=auto.AutoApplyController(api,runner,lambda file:file.metadata)
            controller.timer.setInterval(2)  # exercise bounded retries aggressively
            samples=[]
            last=[time.monotonic()]
            started=time.monotonic()
            admitted=[0]
            maximum=[0]
            failure=[]
            tick=QTimer()
            def heartbeat():
                now=time.monotonic()
                samples.append(max(0,(now-last[0]-.01)*1000));last[0]=now
            tick.timeout.connect(heartbeat);tick.start(10)
            producer=QTimer()
            def produce():
                begin=admitted[0]
                for file in files[begin:begin+32]:controller.watch(file,file.metadata)
                admitted[0]=min(39000,begin+32)
                if admitted[0]==39000:producer.stop()
            producer.timeout.connect(produce);producer.start(1)
            monitor=QTimer()
            def observe():
                state=runner.status()
                maximum[0]=max(maximum[0],state['staging'])
                if state['db_error']:failure.append(state['db_error']);app.quit()
                if time.monotonic()-started>120:failure.append('load timeout');app.quit()
                if (admitted[0]==39000 and not state['staging'] and
                        all(w.admitted for w in controller.watches.values()) and state['backlog']==39000):
                    app.quit()
            monitor.timeout.connect(observe);monitor.start(20)
            app.exec()
            producer.stop();monitor.stop();tick.stop()
            memory=tracemalloc.get_traced_memory()[1]-baseline
            controller.stop();runner.stop()
            assert runner.wait_stopped(10), runner.status()
        tracemalloc.stop()
        assert not failure,failure
        assert not violations,violations
        assert store.job_count()==39000
        assert maximum[0]<=2048,maximum
        assert memory<96*1024*1024,memory
        assert percentile(samples,95)<100,samples[-20:]
        assert percentile(samples,99)<250,samples[-20:]
        assert max(samples)<1000,max(samples)
        print(json.dumps({'identities':39000,'historical':29000,'new':10000,
              'staging_max':maximum[0],'extra_peak_mib':round(memory/1024/1024,2),
              'gui_lag_p95_ms':round(percentile(samples,95),2),
              'gui_lag_p99_ms':round(percentile(samples,99),2),
              'gui_lag_max_ms':round(max(samples),2),
              'elapsed_s':round(time.monotonic()-started,2),'gui_sqlite_calls':len(violations)}))


def backup_cases():
    app=QCoreApplication.instance() or QCoreApplication([])
    owner=threading.get_ident()
    saved=[]
    timer_ticks=[]
    for scenario in ('success','edited','renamed','disabled','failure','replacement'):
        with tempfile.TemporaryDirectory() as directory:
            runner=engine.UniversalAggregator(store=engine.ResultStore(Path(directory)/'queue.db'),
                                               credentials={},paused=True)
            assert runner.wait_ready()
            api=types.SimpleNamespace(tagger=QObject(),
                plugin_config={'auto_apply_best':True,'auto_save_with_backup':True},
                logger=types.SimpleNamespace(info=lambda *a:None,warning=lambda *a:None,error=lambda *a:None))
            file=File(1)
            controller=auto.AutoApplyController(api,runner,lambda f:f.metadata)
            controller.timer.stop()
            controller.watch(file,file.metadata)
            watch=next(iter(controller.watches.values()))
            controller.io.results[watch.key]={'payload':{}}
            original_read=controller.io.read
            controller.io.read=lambda keys:None
            # No actual dispatcher/network is ever resumed in this probe.
            controller.engine=types.SimpleNamespace(paused=False,schedule_async=runner.schedule_async)
            def backup(path):
                assert threading.get_ident()!=owner
                time.sleep(.15)
                if scenario=='failure':raise OSError('synthetic disk full')
                return {'path':path,'backup':'synthetic-backup'}
            def apply(*args,**kwargs):
                assert threading.get_ident()==owner
                assert kwargs.get('verified_backup',{}).get('backup')=='synthetic-backup'
                saved.append(scenario)
            with patch.object(workflow,'backup_envelope',backup), \
                    patch.object(auto,'proposal_for_auto',return_value=({},{})), \
                    patch.object(auto,'apply_best_to_file',side_effect=apply):
                controller.poll()
                assert controller._backup_wait is not None
                if scenario=='edited':file.metadata['albumartist']='Manual edit'
                if scenario=='renamed':file.filename='synthetic/renamed.flac'
                if scenario=='disabled':controller.stop()
                if scenario=='replacement':controller.watch(file,file.metadata,force=True)
                tick=QTimer()
                tick.timeout.connect(lambda:timer_ticks.append(time.monotonic()))
                tick.start(10)
                QTimer.singleShot(300,app.quit)
                app.exec();tick.stop()
                if not controller.stopped:controller._finish_backup()
                if scenario=='replacement':
                    assert (file.filename,id(file)) in controller.watches,'obsolete backup removed fresh watch'
            controller.stop();runner.stop()
            assert runner.wait_stopped(10)
    assert saved==['success'],saved
    assert len(timer_ticks)>=50,len(timer_ticks)
    print(json.dumps({'backup_scenarios':6,'saved_only_unmodified_identity':True,
                      'backup_gui_ticks':len(timer_ticks),'gui_media_operations':0}))


def generation_case():
    app=QCoreApplication.instance() or QCoreApplication([])
    module=importlib.import_module('qt_probe.background_io')
    parent=QObject()
    runner=types.SimpleNamespace()
    io=module.create_gui_io(parent,runner)
    old=Future();old.set_result({'old-key':{'payload':{'stale':True}}})
    # A Qt queued signal is still in transit when the user forces a refresh.
    io.deliver('results',old,('old-key',))
    io.invalidate('old-key')
    app.processEvents()
    assert 'old-key' not in io.results,'obsolete envelope repopulated result cache'
    io.stop()
    print(json.dumps({'forced_refresh_generation_fence':True}))


if __name__=='__main__':
    if '--backup-only' not in sys.argv:run()
    backup_cases()
    generation_case()
