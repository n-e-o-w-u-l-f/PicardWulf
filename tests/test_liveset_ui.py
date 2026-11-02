"""LiveSet GUI background API search: consent, lifecycle, no tag writes."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType("pw_liveset_test")
pkg.__path__=[str(ROOT/"neowulf_picard_repair")]
sys.modules[pkg.__name__]=pkg
ui=importlib.import_module(pkg.__name__+".liveset_ui")


class Message:
    class StandardButton:
        Yes=1
        No=2
    consent=2
    shown=[]
    @classmethod
    def question(cls,*args):
        cls.shown.append(("question",args))
        return cls.consent
    @classmethod
    def information(cls,*args):
        cls.shown.append(("info",args))
    @classmethod
    def warning(cls,*args):
        cls.shown.append(("warn",args))


class Signal:
    def connect(self,fn):
        self.callback=fn


class Timer:
    all=[]
    def __init__(self,parent=None):
        self.timeout=Signal()
        self.running=False
        self.all.append(self)
    def setInterval(self,value): pass
    def start(self):self.running=True
    def stop(self):self.running=False
    def poll(self):
        if self.running and hasattr(self.timeout,'callback'):
            self.timeout.callback()


class LiveSetUiTests(unittest.TestCase):
    def setUp(self):
        ui.stop_live_set_lookups()
        Message.shown=[]
        Message.consent=Message.StandardButton.No
        Timer.all=[]
        qt=types.ModuleType("PyQt6")
        qtcore=types.ModuleType("PyQt6.QtCore")
        qtwidget=types.ModuleType("PyQt6.QtWidgets")
        qtcore.QTimer=Timer
        qtwidget.QMessageBox=Message
        self.patch=patch.dict(sys.modules,{
            "PyQt6":qt,"PyQt6.QtCore":qtcore,"PyQt6.QtWidgets":qtwidget})
        self.patch.start()
    def tearDown(self):
        ui.stop_live_set_lookups()
        self.patch.stop()

    @staticmethod
    def fixture():
        meta={"album":"Boiler Room Berlin DJ Set",
              "albumartist":"DJ Example", "date":"2025"}
        file=types.SimpleNamespace(metadata=meta)
        api=types.SimpleNamespace(tagger=types.SimpleNamespace(window=object()))
        return api,file

    def poll(self):
        deadline=time.monotonic()+4
        while ui._ACTIVE and time.monotonic()<deadline:
            for timer in list(Timer.all):
                timer.poll()
            time.sleep(.003)
        self.assertFalse(ui._ACTIVE,"LiveSet worker did not finish")

    def test_declined_remote_search_never_calls_provider(self):
        api,file=self.fixture()
        called=[]
        self.assertFalse(ui.show_liveset_lookup(api,[file],
                  search=lambda *args:called.append(args)))
        self.assertFalse(called)
        self.assertFalse(ui._ACTIVE)
        self.assertEqual(Message.shown[0][0],"question")
        self.assertIn('Mixcloud',str(Message.shown[0]))

    def test_opt_in_fetch_runs_async_and_does_not_touch_metadata(self):
        api,file=self.fixture()
        saved=dict(file.metadata)
        calls=[]
        Message.consent=Message.StandardButton.Yes
        def fetch(artist,title):
            calls.append((artist,title))
            return {"status":"SUGGESTION_ONLY",
                    "matches":[{
                        "artist":artist,"title":title,
                        "source_url":"https://www.mixcloud.com/dj/set/",
                        "uploaded_on":"2025-10-27"}]}
        self.assertTrue(ui.show_liveset_lookup(api,[file],search=fetch))
        self.poll()
        self.assertEqual(calls,[("DJ Example","Boiler Room Berlin DJ Set")])
        self.assertEqual(file.metadata,saved)
        text=' '.join(str(v) for v in Message.shown)
        self.assertIn('Auftrittsdatum: NICHT BELEGT',text)
        self.assertIn('mixcloud.com',text)
        self.assertTrue(any(t[0]=='info' for t in Message.shown))

    def test_ambiguous_match_does_not_mutate_tags(self):
        api,file=self.fixture()
        saved=dict(file.metadata)
        Message.consent=Message.StandardButton.Yes
        self.assertTrue(ui.show_liveset_lookup(api,[file],search=lambda *args:{
            "status":"REVIEW","matches":[{"source_url":"https://www.mixcloud.com/dj/x"}]}))
        self.poll()
        self.assertEqual(file.metadata,saved)
        self.assertIn('Kein eindeutiger',str(Message.shown))

    def test_worker_exception_is_reported_without_leaking_credential(self):
        api,file=self.fixture()
        Message.consent=Message.StandardButton.Yes
        def fail(*args):
            raise RuntimeError("TEST_SECRET_NEVER_DISPLAY")
        self.assertTrue(ui.show_liveset_lookup(api,[file],search=fail))
        self.poll()
        text=str(Message.shown)
        self.assertIn('RuntimeError',text)
        self.assertNotIn('TEST_SECRET',text)
        self.assertEqual(file.metadata['albumartist'],'DJ Example')

    def test_shutdown_cancels_or_ignores_unfinished_jobs(self):
        api,file=self.fixture()
        Message.consent=Message.StandardButton.Yes
        self.assertTrue(ui.show_liveset_lookup(api,[file],
            search=lambda *args:{"status":"ABSTAIN","matches":[]}))
        ui.stop_live_set_lookups()
        self.assertFalse(ui._ACTIVE)
        self.assertFalse(any(t.running for t in Timer.all))

    def test_no_metadata_or_multiple_files_never_calls_remote(self):
        api,file=self.fixture()
        self.assertFalse(ui.show_liveset_lookup(api,[file,file]))
        self.assertFalse(ui.show_liveset_lookup(
            api,[types.SimpleNamespace(metadata={})]))
        self.assertFalse(ui._ACTIVE)


if __name__=="__main__":
    unittest.main()
