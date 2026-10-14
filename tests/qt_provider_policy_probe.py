"""Real Qt operator-dialog smoke test with fake Picard/vault; no API/media/secret access."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from concurrent.futures import Future
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import patch
from PyQt6.QtCore import QObject,QTimer
from PyQt6.QtWidgets import (QApplication,QDialog,QCheckBox,QSpinBox,QDialogButtonBox,QLineEdit)

ROOT=Path(__file__).parents[1]
for name in ('picard','picard.plugin3','picard.plugin3.api','picard.script'):
    sys.modules[name]=types.ModuleType(name)
sys.modules['picard.plugin3.api'].BaseAction=type('BaseAction',(),{})
sys.modules['picard.plugin3.api'].Metadata=dict
sys.modules['picard.script'].ScriptParser=type('ScriptParser',(),{})
spec=importlib.util.spec_from_file_location('qt_s2_plugin',ROOT/'neowulf_picard_repair/__init__.py',
    submodule_search_locations=[str(ROOT/'neowulf_picard_repair')])
plugin=importlib.util.module_from_spec(spec);sys.modules[spec.name]=plugin;spec.loader.exec_module(plugin)

class Engine:
    stopped=False
    def __init__(self):self.options=None;self.values=None;self.receipt=Future()
    def configure_providers(self,options):self.options=options
    def update_credentials(self,values,persist=False):
        assert persist
        self.values=dict(values)
        QTimer.singleShot(150,lambda:self.receipt.set_result({'saved':True}))
        return self.receipt

def run():
    app=QApplication([])
    eng=Engine();plugin._aggregator=eng
    config={'disabled_providers':[],'provider_requests_per_hour':3000}
    api=types.SimpleNamespace(tagger=QObject(),plugin_config=config,
        logger=types.SimpleNamespace(error=lambda *args:None))
    messages=[]
    policy=plugin.ProviderPolicyAction();policy.api=api
    def configure():
        dlg=next(w for w in app.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())
        for checkbox in dlg.findChildren(QCheckBox):
            if checkbox.text()=='Deezer':checkbox.setChecked(False)
            elif 'Alle zugänglichen' in checkbox.text() or 'bereits ein zulässiger' in checkbox.text():
                checkbox.setChecked(True)
        dlg.findChild(QSpinBox).setValue(42)
        box=dlg.findChild(QDialogButtonBox)
        box.button(QDialogButtonBox.StandardButton.Save).click()
    with patch.object(plugin,'_show',side_effect=lambda *args:messages.append(args)):
        QTimer.singleShot(10,configure);policy.callback([])
    assert config['disabled_providers']==['deezer']
    assert config['provider_requests_per_hour']==42
    assert eng.options['exhaustive'] and eng.options['spotify_existing_access_confirmed']
    credential=plugin.CredentialsAction();credential.api=api
    def edit():
        dlg=next(w for w in app.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())
        entries=dlg.findChildren(QLineEdit)
        assert len(entries)==7,'internal rotation marker/expiry must not be editable'
        entries[-2].setText('synthetic-rotated-refresh')
        dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    with patch.object(plugin,'_show',side_effect=lambda *args:messages.append(args)), \
            patch.object(plugin,'os',types.SimpleNamespace(name='nt')), \
            patch.object(plugin,'load_credentials',return_value={'soundcloud_token':'synthetic-old'}), \
            patch.object(plugin,'save_credentials',side_effect=AssertionError('GUI vault write')):
        QTimer.singleShot(10,edit);credential.callback([])
        assert not eng.receipt.done(),'GUI must not wait for credential storage'
        assert eng.values=={'soundcloud_refresh_token':'synthetic-rotated-refresh'}
        QTimer.singleShot(350,app.quit);app.exec()
    assert eng.receipt.done()
    assert any('verschlüsselt gespeichert' in str(message) for message in messages)
    print('PASS: provider options and asynchronous credential acknowledgement on real Qt')

if __name__=='__main__':run()
