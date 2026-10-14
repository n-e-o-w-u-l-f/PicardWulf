"""Real Qt regression: retain manual force under backpressure and selection changes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from concurrent.futures import Future
import importlib
from pathlib import Path
import sys
import time
import types
from unittest.mock import patch
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication,QComboBox,QDialog,QPushButton,QMessageBox

ROOT=Path(__file__).parents[1]
pkg=types.ModuleType('native_probe');pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules['native_probe']=pkg
ui=importlib.import_module('native_probe.native_ui')
class Metadata(dict):
    def copy(self,other):self.clear();self.update(other)
api_module=types.ModuleType('picard.plugin3.api');api_module.Metadata=Metadata
class File:
    def __init__(self,title):
        self.filename=f'synthetic/{title}.flac'
        self.metadata={'artist':'Synthetic','title':title,'album':'Album'}
class Engine:
    def __init__(self):self.force=[];self.accepted=False
    def request_results(self,keys):
        receipt=Future()
        receipt.set_result({key:{'updated':1,'payload':{'candidates':[]}} for key in keys})
        return receipt
    def schedule_async(self,raw,force=False):
        if force:
            self.force.append(dict(raw))
            self.accepted=len(self.force)>=4
            return self.accepted
        return True

def run():
    app=QApplication([])
    runner=Engine()
    api=types.SimpleNamespace(logger=types.SimpleNamespace(warning=lambda *a:None))
    files=[File('1'),File('2')]
    clicked=[False]
    started=time.monotonic()
    control=QTimer()
    def tick():
        dialogs=[w for w in app.topLevelWidgets() if isinstance(w,QDialog)]
        if not dialogs:return
        dlg=dialogs[0]
        if not clicked[0]:
            clicked[0]=True
            for timer in dlg.findChildren(QTimer):timer.setInterval(10)
            button=next(b for b in dlg.findChildren(QPushButton) if b.text()=='Erneut suchen')
            button.click()
            dlg.findChild(QComboBox).setCurrentIndex(1)
        if runner.accepted or time.monotonic()-started>2:dlg.reject()
    control.timeout.connect(tick);control.start(5)
    with patch.dict(sys.modules,{'picard.plugin3.api':api_module}), \
            patch.object(QMessageBox,'warning',return_value=None):
        ui.show_native_window(api,runner,files,lambda f:f.metadata)
    control.stop()
    assert runner.accepted,'manual force was lost when staging was full'
    assert all(q['title']=='1' for q in runner.force),'selection change redirected force'
    print('PASS: manual force retained through backpressure and selection change')

if __name__=='__main__':run()
