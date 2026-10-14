"""GUI-neutral regression of the two-phase post-backup save gate.

No Qt, live music file, Picard process, or network access is required.
"""
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import weakref

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('presave_gate_test')
pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules[pkg.__name__]=pkg
auto=importlib.import_module(pkg.__name__+'.auto_apply')


class FakeFile:
    def __init__(self):
        self.filename='synthetic/path.flac'
        self.metadata={'title':'Track', 'artist':'Artist'}


class FakeIO:
    def __init__(self):
        self.backups={}
        self.checks=[]

    def pre_save_check(self, token, backup, path):
        self.checks.append((token, backup, path))
        return True


class PreSaveGateTests(unittest.TestCase):
    def build(self):
        f=FakeFile()
        identity=(f.filename,id(f))
        baseline='{"artist": "Artist", "title": "Track"}'
        watch=auto.Watch(weakref.ref(f),{},'key',0,id(f),baseline,True,False)
        io=FakeIO()
        controller=object.__new__(auto.AutoApplyController)
        controller.io=io
        controller.engine=types.SimpleNamespace(paused=False)
        controller.save_tracker=None
        controller.api=types.SimpleNamespace(
            plugin_config={'auto_save_with_backup':True,'auto_apply_best':True},
            logger=types.SimpleNamespace(warning=lambda *args:None))
        controller.watches={identity:watch}
        controller.done=set()
        controller._backup_wait=('backup',identity,watch,{'payload':{}},baseline,None)
        return controller,io,f,identity

    def test_no_save_until_second_background_check_finishes(self):
        controller,io,f,identity=self.build()
        backup={'backup':'private-backup','path':f.filename}
        io.backups['backup:auto']={'value':backup}
        with patch.object(auto,'apply_best_to_file') as apply:
            controller._finish_backup()
            apply.assert_not_called()
            self.assertEqual(io.checks,[('preflight:auto',backup,f.filename)])
            self.assertEqual(controller._backup_wait[0],'preflight')
            self.assertIn(identity,controller.watches)
            io.backups['preflight:auto']={'value':True}
            controller._finish_backup()
            apply.assert_called_once()
            self.assertIsNone(controller._backup_wait)
            self.assertIn(identity,controller.done)

    def test_changed_original_denied_by_background_check(self):
        controller,io,f,identity=self.build()
        io.backups['backup:auto']={'value':{'backup':'private-backup','path':f.filename}}
        with patch.object(auto,'apply_best_to_file') as apply:
            controller._finish_backup()
            io.backups['preflight:auto']={'error':'UnsafeCandidate'}
            controller._finish_backup()
            apply.assert_not_called()
            self.assertIsNone(controller._backup_wait)
            self.assertIn(identity,controller.done)

    def test_metadata_change_during_preflight_denies_write(self):
        controller,io,f,identity=self.build()
        io.backups['backup:auto']={'value':{'backup':'private-backup','path':f.filename}}
        with patch.object(auto,'apply_best_to_file') as apply:
            controller._finish_backup()
            f.metadata['title']='Manual edit'
            io.backups['preflight:auto']={'value':True}
            controller._finish_backup()
            apply.assert_not_called()
            self.assertNotIn(identity,controller.watches)

    def test_paused_search_during_preflight_denies_auto_write(self):
        controller,io,f,identity=self.build()
        io.backups['backup:auto']={'value':{'backup':'private-backup','path':f.filename}}
        with patch.object(auto,'apply_best_to_file') as apply:
            controller._finish_backup()
            controller.engine.paused=True
            io.backups['preflight:auto']={'value':True}
            controller._finish_backup()
            apply.assert_not_called()
            self.assertNotIn(identity,controller.watches)

    def test_disabled_auto_apply_during_preflight_denies_write(self):
        controller,io,f,identity=self.build()
        io.backups['backup:auto']={'value':{'backup':'private-backup','path':f.filename}}
        with patch.object(auto,'apply_best_to_file') as apply:
            controller._finish_backup()
            controller.api.plugin_config['auto_apply_best']=False
            io.backups['preflight:auto']={'value':True}
            controller._finish_backup()
            apply.assert_not_called()
            self.assertNotIn(identity,controller.watches)


if __name__=='__main__':
    unittest.main()
