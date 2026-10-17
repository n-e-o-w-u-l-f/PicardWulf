"""Picard 3 supported menu-action integration, safe import and UI lifecycle tests."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType("picardwulf_safe_import_tests")
pkg.__path__=[str(ROOT/"neowulf_picard_repair")]
sys.modules[pkg.__name__]=pkg
ui=importlib.import_module(pkg.__name__+".picard_safe_import")


class PicardFile:
    def __init__(self,source,dest):
        self.filename=str(source)
        self.destination=str(dest)
        self.metadata={"artist":"Artist","title":"Track"}
        self.errors=[]
        self.saved=True
        self.calls=[]
    def is_saved(self):
        return self.saved
    def make_filename(self,source,metadata,settings):
        self.calls.append((source,metadata,settings))
        return self.destination


class Tracker:
    def __init__(self):
        self.inflight=False
    def has_inflight(self):
        return self.inflight


class Messages:
    class StandardButton:
        Yes=1
        No=2
    answer=1
    dialogs=[]
    @classmethod
    def warning(cls,*args):
        cls.dialogs.append(("warn",args))
    @classmethod
    def information(cls,*args):
        cls.dialogs.append(("info",args))
    @classmethod
    def question(cls,*args):
        cls.dialogs.append(("question",args))
        return cls.answer


class FolderPicker:
    folder=""
    @classmethod
    def getExistingDirectory(cls,*args):
        return cls.folder


class Signal:
    def __init__(self):
        self.callback=None
    def connect(self,fn):
        self.callback=fn


class Timer:
    instances=[]
    def __init__(self,parent=None):
        self.timeout=Signal()
        self.running=False
        self.instances.append(self)
    def setInterval(self,interval):
        self.interval=interval
    def start(self):
        self.running=True
    def stop(self):
        self.running=False
    def poll(self):
        if self.running and self.timeout.callback:
            self.timeout.callback()


class GuiTests(unittest.TestCase):
    def setUp(self):
        Messages.answer=Messages.StandardButton.Yes
        Messages.dialogs.clear()
        Timer.instances.clear()
        ui.stop_safe_imports()

    def fixture(self,tmp):
        root=Path(tmp)
        src=root/"staging"
        lib=root/"library"
        rollback=root/"recovery"
        for f in (src,lib,rollback):
            f.mkdir()
        a=src/"Track.flac"
        a.write_bytes(b"generated test FLAC, codec mocked")
        b=lib/"Track.flac"
        f=PicardFile(a,b)
        settings={"move_files":True,"rename_files":True,
                  "move_overwrite_existing_files":False,
                  "move_files_to":str(lib)}
        tracker=Tracker()
        api=types.SimpleNamespace(global_config=types.SimpleNamespace(setting=settings),
            tagger=types.SimpleNamespace(window=object()),
            logger=types.SimpleNamespace(warning=lambda *args:None))
        return f,settings,rollback,tracker,api

    def test_filename_uses_active_picard_preset_and_no_config_changes(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,_=self.fixture(t)
            settings["active_file_naming_script_id"]="Preset 3"
            before=dict(settings)
            snap=ui.capture_safe_import(f,settings,backup,tracker)
            self.assertEqual(snap["destination"],f.destination)
            self.assertEqual(snap["source"],f.filename)
            self.assertEqual(f.calls,[(f.filename,f.metadata,settings)])
            self.assertEqual(settings,before)

    def test_unsaved_file_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,_=self.fixture(t)
            f.saved=False
            with self.assertRaises(ui.SafeImportUnavailable):
                ui.capture_safe_import(f,settings,backup,tracker)

    def test_inflight_save_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,_=self.fixture(t)
            tracker.inflight=True
            with self.assertRaises(ui.SafeImportUnavailable):
                ui.capture_safe_import(f,settings,backup,tracker)

    def test_native_overwrite_risk_refused_without_changing_option(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,_=self.fixture(t)
            settings["move_overwrite_existing_files"]=True
            with self.assertRaises(ui.SafeImportUnavailable):
                ui.capture_safe_import(f,settings,backup,tracker)
            self.assertTrue(settings["move_overwrite_existing_files"])

    def test_no_native_move_or_relative_library_refused(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,_=self.fixture(t)
            settings["move_files"]=False
            with self.assertRaises(ui.SafeImportUnavailable):
                ui.capture_safe_import(f,settings,backup,tracker)
            settings["move_files"]=True
            settings["move_files_to"]="Relative/Music"
            with self.assertRaises(ui.SafeImportUnavailable):
                ui.capture_safe_import(f,settings,backup,tracker)

    def test_destination_must_be_within_effective_library_root(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,_=self.fixture(t)
            f.destination=str(Path(t)/"other"/"Track.flac")
            with self.assertRaises(ui.SafeImportUnavailable):
                ui.capture_safe_import(f,settings,backup,tracker)

    def fake_qt(self):
        qt=types.ModuleType("PyQt6")
        qtcore=types.ModuleType("PyQt6.QtCore")
        qtwidgets=types.ModuleType("PyQt6.QtWidgets")
        qtcore.QTimer=Timer
        qtwidgets.QMessageBox=Messages
        qtwidgets.QFileDialog=FolderPicker
        return {"PyQt6":qt,"PyQt6.QtCore":qtcore,"PyQt6.QtWidgets":qtwidgets}

    def drain(self):
        deadline=time.monotonic()+4
        while ui._ACTIVE and time.monotonic()<deadline:
            for timer in list(Timer.instances):
                timer.poll()
            time.sleep(0.004)
        self.assertFalse(ui._ACTIVE,"Import callback did not finish")

    def test_gui_decline_performs_only_dry_run(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,api=self.fixture(t)
            FolderPicker.folder=str(backup)
            Messages.answer=Messages.StandardButton.No
            calls=[]
            def simulated(**kw):
                calls.append(dict(kw))
                return {"action":"WOULD_REPLACE"}
            with patch.dict(sys.modules,self.fake_qt()),patch.object(ui,"import_staged_flac",side_effect=simulated):
                self.assertTrue(ui.show_safe_import(api,[f],tracker))
                self.drain()
            self.assertEqual(len(calls),1)
            self.assertIs(calls[0]["apply"],False)
            self.assertTrue(any(m[0]=="question" for m in Messages.dialogs))

    def test_gui_confirmation_runs_reverified_apply(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,api=self.fixture(t)
            FolderPicker.folder=str(backup)
            calls=[]
            def simulated(**kw):
                calls.append(dict(kw))
                return {"action":"REPLACED" if kw["apply"] else "WOULD_REPLACE"}
            with patch.dict(sys.modules,self.fake_qt()),patch.object(ui,"import_staged_flac",side_effect=simulated):
                self.assertTrue(ui.show_safe_import(api,[f],tracker))
                self.drain()
            self.assertEqual([x["apply"] for x in calls],[False,True])
            self.assertTrue(any(m[0]=="info" and "REPLACED" in str(m[1]) for m in Messages.dialogs))
            self.assertTrue(f.is_saved())

    def test_gui_changed_profile_during_preview_refuses_apply(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,api=self.fixture(t)
            FolderPicker.folder=str(backup)
            calls=[]
            def simulated(**kw):
                calls.append(dict(kw))
                settings["move_overwrite_existing_files"]=True
                return {"action":"WOULD_REPLACE"}
            with patch.dict(sys.modules,self.fake_qt()),patch.object(ui,"import_staged_flac",side_effect=simulated):
                self.assertTrue(ui.show_safe_import(api,[f],tracker))
                self.drain()
            self.assertEqual(len(calls),1)
            self.assertTrue(any(m[0]=="warn" for m in Messages.dialogs))

    def test_gui_ambiguous_identity_never_applies(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,api=self.fixture(t)
            FolderPicker.folder=str(backup)
            calls=[]
            def simulated(**kw):
                calls.append(dict(kw))
                return {"action":"REVIEW"}
            with patch.dict(sys.modules,self.fake_qt()),patch.object(ui,"import_staged_flac",side_effect=simulated):
                self.assertTrue(ui.show_safe_import(api,[f],tracker))
                self.drain()
            self.assertEqual(len(calls),1)
            self.assertFalse(calls[0]["apply"])

    def test_gui_wrong_selection_does_not_start_worker(self):
        with tempfile.TemporaryDirectory() as t:
            f,settings,backup,tracker,api=self.fixture(t)
            FolderPicker.folder=str(backup)
            with patch.dict(sys.modules,self.fake_qt()),patch.object(ui,"import_staged_flac") as worker:
                self.assertFalse(ui.show_safe_import(api,[f,f],tracker))
                worker.assert_not_called()
                self.assertEqual(ui._ACTIVE,{})


if __name__=="__main__":
    unittest.main()
