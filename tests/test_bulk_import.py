"""Large folder ingestion safety; never calls external providers."""
from pathlib import Path
import importlib
import sys
import tempfile
import threading
import time
import types
import unittest

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
package='picardwulf_bulk_test'
if package not in sys.modules:
    m=types.ModuleType(package)
    m.__path__=[str(ROOT/'neowulf_picard_repair')]
    sys.modules[package]=m
mod=importlib.import_module(package+'.universal_engine')

class TestBulkBackgroundIngest(unittest.TestCase):
    def test_10000_songs_persist_without_sqlite_io_on_gui_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            store=mod.ResultStore(Path(directory)/'queue.sqlite3')
            engine=mod.UniversalAggregator(store=store,credentials={},paused=True)
            try:
                duration=time.monotonic()
                for i in range(10000):
                    raw={
                        'artist':'Eminem','title':f'New track {i}',
                        'album':'Album','albumartist':'Eminem'}
                    deadline=time.monotonic()+10
                    while not engine.schedule_async(raw):
                        self.assertLess(time.monotonic(),deadline)
                        self.assertLessEqual(engine.status()['staging'],2048)
                        time.sleep(.005)
                enqueue_time=time.monotonic()-duration
                # Source hook only normalizes hashes; database connection and
                # network work are exclusively performed on background threads.
                self.assertLess(enqueue_time,7.0,f'GUI enqueue took {enqueue_time:.1f}s')
                deadline=time.monotonic()+25
                while store.job_count()<10000 and time.monotonic()<deadline:
                    time.sleep(.08)
                self.assertEqual(store.job_count(),10000)
                self.assertEqual(engine.status()['pending'],0)
                self.assertEqual(engine.status()['staging'],0)
                self.assertTrue(engine.status()['paused'])
            finally:
                engine.stop()
                self.assertTrue(engine.wait_stopped(10))

    def test_pause_resume_controls_dispatch_without_dropping_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            store=mod.ResultStore(Path(directory)/'queue.sqlite3')
            engine=mod.UniversalAggregator(store=store,credentials={},paused=True)
            try:
                self.assertTrue(engine.schedule_async({'artist':'Eminem','title':'Stan'}))
                deadline=time.monotonic()+5
                while store.job_count()!=1 and time.monotonic()<deadline:time.sleep(.03)
                self.assertEqual(store.job_count(),1)
                self.assertEqual(engine.status()['pending'],0)
                self.assertTrue(engine.paused)
            finally:
                engine.stop()
                self.assertTrue(engine.wait_stopped(10))
            # A new engine must recognise the persisted job without copying
            # the SQLite cache away or deleting unfinished work.
            fresh=mod.UniversalAggregator(store=store,credentials={},paused=True)
            try:
                self.assertTrue(fresh.wait_ready())
                self.assertEqual(fresh.status()['backlog'],1)
                self.assertEqual(fresh.status()['pending'],0)
            finally:
                fresh.stop()
                self.assertTrue(fresh.wait_stopped(10))

    def test_read_completed_results_in_one_sqlite_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            store=mod.ResultStore(Path(directory)/'queue.sqlite3')
            store.save_result('a',{'title':'one'},{'status':{'deezer':'ok'}})
            store.save_result('b',{'title':'two'},{'status':{'spotify':'ok'}})
            found=store.get_results(['a','b','c'])
            self.assertEqual(set(found),{'a','b'})
            self.assertEqual(found['b']['payload']['status']['spotify'],'ok')

    def test_installer_allows_hot_swap_only_after_explicit_user_acknowledgement(self):
        code=(ROOT/'Install-NEOWULF.ps1').read_text(encoding='utf8')
        self.assertIn('param([switch]$LiveUpdate)',code)
        self.assertIn('JA-PLUGIN-DEAKTIVIERT',code)
        self.assertIn('if (!$picardRunning)',code)
        self.assertIn("-LiveUpdate",(ROOT/'Install-PicardWulf-Live.cmd').read_text(encoding='utf8'))
        self.assertIn('api.register_tools_menu_action(SearchPauseAction)',
                      (ROOT/'neowulf_picard_repair/__init__.py').read_text(encoding='utf8'))

if __name__=='__main__':unittest.main()
