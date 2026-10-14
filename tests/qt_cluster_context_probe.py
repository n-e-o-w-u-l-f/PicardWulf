"""Real Qt event-loop smoke: context album menu choice is source neutral."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from concurrent.futures import Future
import importlib
from pathlib import Path
import sys
import time
import types
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QTableWidget

ROOT=Path(__file__).parents[1]
pkg=types.ModuleType('qt_cluster_live')
pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules[pkg.__name__]=pkg
ui=importlib.import_module(pkg.__name__+'.cluster_ui')
ad=importlib.import_module(pkg.__name__+'.universal_adapters')
engine=importlib.import_module(pkg.__name__+'.universal_engine')

class File:
    def __init__(self,n):
        self.filename='synthetic_%d.flac'%n
        self.metadata={'artist':'Artist','albumartist':'Artist',
                       'album':'Album','title':'Track %02d'%n,
                       'duration_ms':'100000'}

class TestEngine:
    paused=False
    def __init__(self,files):
        self.rows={}
        for n,file in enumerate(files,1):
            q=engine.clean_track(file.metadata)
            self.rows[engine.query_key(q)]={'updated':time.time()+1,
                'payload':{'completion':'COMPLETE',
                'status':{'musicbrainz':'ok','deezer':'ok','soundcloud':'CREDENTIALS_REQUIRED'},
                'candidates':[
                    ad.item('musicbrainz',q['title'],'Artist','Album',99000,
                            albumartist='Artist',
                            release_mbid='12345678-1234-4234-8234-123456789012'),
                    ad.item('deezer',q['title'],'Artist','Album',100000,
                            albumartist='Artist',provider_album_id=9955)]}}
        self.scheduled=[]
    def schedule_async(self,q,force=False):
        self.scheduled.append((engine.query_key(q),force))
        return True
    def request_results(self,keys):
        f=Future();f.set_result({k:self.rows[k] for k in keys});return f

def run():
    app=QApplication([])
    files=[File(1),File(2)]
    source=TestEngine(files)
    api=types.SimpleNamespace(logger=types.SimpleNamespace(warning=lambda *a:None))
    status={'rows':0,'winner':''}
    timer=QTimer()
    started=time.monotonic()
    def check():
        widgets=[w for w in app.topLevelWidgets() if isinstance(w,QDialog)]
        if not widgets:return
        dialog=widgets[0]
        table=dialog.findChild(QTableWidget)
        if table is not None and table.rowCount()>=2:
            status['rows']=table.rowCount()
            status['winner']=table.item(0,2).text()
            dialog.reject()
        elif time.monotonic()-started>3:
            dialog.reject()
    timer.timeout.connect(check)
    timer.start(10)
    ui.show_similar_albums(api,source,files,lambda f:f.metadata)
    timer.stop()
    assert status['rows']>=2,status
    assert status['winner']=='deezer',status
    assert len(source.scheduled)==2 and all(force for _,force in source.scheduled),source.scheduled
    print('PASS: real Qt dialog displayed %d provider release options; Deezer highest'%status['rows'])

if __name__=='__main__':run()
