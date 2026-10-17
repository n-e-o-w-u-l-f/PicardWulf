"""Synthetic Qt event-queue contracts for gold retirement; no actual Picard UI."""
import importlib.util
import pathlib
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

MODULE=pathlib.Path(__file__).resolve().parents[1]/'neowulf_picard_repair'/'gold_retirement.py'
spec=importlib.util.spec_from_file_location('gold_controller_test_module',MODULE)
gold=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gold)


class Signal:
    def __init__(self):
        self.slot=None
        self.messages=[]
    def connect(self,slot,*args):
        self.slot=slot
    def emit(self, value):
        self.messages.append((value,threading.get_ident()))
    def flush(self):
        while self.messages:
            value,thread=self.messages.pop(0)
            self.slot(value)


class Descriptor:
    def __init__(self):
        self.name=None
    def __set_name__(self,cls,name):
        self.name='_signal_'+name
    def __get__(self,instance,owner):
        if instance is None:
            return self
        if not hasattr(instance,self.name):
            setattr(instance,self.name,Signal())
        return getattr(instance,self.name)


class FakeTimer:
    def __init__(self,*args):
        self.timeout=Signal()
        self.running=False
    def setInterval(self,ms):
        self.interval=ms
    def start(self):
        self.running=True
    def stop(self):
        self.running=False
    @staticmethod
    def singleShot(*args):
        pass


def qt_stub():
    qt=types.ModuleType('PyQt6')
    core=types.ModuleType('PyQt6.QtCore')
    class QObject:
        def __init__(self,*args):
            pass
    Qt=types.SimpleNamespace(
        ConnectionType=types.SimpleNamespace(QueuedConnection=1))
    core.QObject=QObject
    core.QTimer=FakeTimer
    core.Qt=Qt
    core.pyqtSignal=lambda *args:Descriptor()
    return {'PyQt6':qt,'PyQt6.QtCore':core}


class File:
    def __init__(self,path):
        self.filename=str(path)
        self.metadata={'title':'Title','artist':'Artist','album':'Album',
                       'tracknumber':'1','discnumber':'1'}
        self.orig_metadata=dict(self.metadata)
        self.errors=[]
    def is_saved(self):
        return True


class Album:
    id='test-album'
    loaded=True
    errors=[]
    def __init__(self,file):
        self.file=file
        self.tracks=[self]
    def is_complete(self):
        return True
    def get_num_unmatched_files(self):
        return 0
    def get_num_unsaved_files(self):
        return 0
    def get_num_matched_tracks(self):
        return 1
    def iterfiles(self):
        return iter([self.file])


class Tracker:
    def __init__(self):
        self.inflight=False
        self.failed=False
    def has_inflight(self):
        return self.inflight
    def path_state(self,path):
        return 'MISMATCH' if self.failed else None


class ControllerTests(unittest.TestCase):
    def context(self,directory):
        path=pathlib.Path(directory)/'one.flac'
        path.write_bytes(b'not real audio; decoder is mocked')
        file=File(path)
        album=Album(file)
        panel=types.SimpleNamespace(remove=lambda albums:self.removed.extend(albums))
        window=types.SimpleNamespace(panel=panel)
        tagger=types.SimpleNamespace(window=window,albums={album.id:album})
        logger=types.SimpleNamespace(info=lambda *a:None, warning=lambda *a:None)
        self.removed=[]
        return types.SimpleNamespace(
            tagger=tagger,logger=logger,
            global_config=types.SimpleNamespace(
                setting={'remove_complete_albums_after_save':False})),album

    def run_case(self,valid=True,mutate=None):
        with tempfile.TemporaryDirectory() as directory:
            api,album=self.context(directory)
            tracker=Tracker()
            with patch.dict(sys.modules,qt_stub()), patch.object(gold,'verify_gold_files',return_value=valid):
                controller=gold.start_gold_retirement(api,tracker)
                try:
                    controller.tick()
                    until=time.monotonic()+5
                    while not controller.finished.messages and time.monotonic()<until:
                        time.sleep(.005)
                    self.assertTrue(controller.finished.messages)
                    # An asynchronous result must not have removed the album yet.
                    self.assertEqual(self.removed,[])
                    if mutate:
                        mutate(tracker,album)
                    controller.finished.flush() # Simulate Qt queued delivery on UI thread.
                    return list(self.removed),album
                finally:
                    controller.stop()

    def test_native_picard_auto_removal_or_unknown_option_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            api,album=self.context(directory)
            tracker=Tracker()
            with patch.dict(sys.modules,qt_stub()), patch.object(gold,'verify_gold_files') as worker:
                controller=gold.start_gold_retirement(api,tracker)
                try:
                    for settings in ({'remove_complete_albums_after_save': True},
                                     {}):
                        api.global_config.setting=settings
                        controller.tick()
                        self.assertIsNone(controller._pending)
                        self.assertEqual(self.removed,[])
                        worker.assert_not_called()
                    api.global_config.setting={'remove_complete_albums_after_save':False}
                    controller.tick()
                    self.assertIsNotNone(controller._pending)
                finally:
                    controller.stop()

    def test_native_option_enabled_during_verification_prevents_ui_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            api,album=self.context(directory)
            tracker=Tracker()
            with patch.dict(sys.modules,qt_stub()), patch.object(
                    gold,'verify_gold_files',return_value=True):
                controller=gold.start_gold_retirement(api,tracker)
                try:
                    controller.tick()
                    until=time.monotonic()+5
                    while not controller.finished.messages and time.monotonic()<until:
                        time.sleep(.005)
                    self.assertTrue(controller.finished.messages)
                    api.global_config.setting['remove_complete_albums_after_save']=True
                    controller.finished.flush()
                    self.assertEqual(self.removed,[])
                finally:
                    controller.stop()

    def test_bounded_album_registry_scan_never_materializes_every_album(self):
        with tempfile.TemporaryDirectory() as directory:
            api,album=self.context(directory)
            tracker=Tracker()
            class MeasuredRegistry(dict):
                scanned=0
                def values(self):
                    for value in super().values():
                        self.scanned+=1
                        yield value
            registry=MeasuredRegistry()
            for n in range(2500):
                registry[str(n)]=types.SimpleNamespace(id=str(n),loaded=False)
            api.tagger.albums=registry
            with patch.dict(sys.modules,qt_stub()), patch.object(
                    gold,'verify_gold_files') as worker:
                controller=gold.start_gold_retirement(api,tracker)
                try:
                    controller.tick()
                    self.assertEqual(registry.scanned,100)
                    controller.tick()
                    self.assertEqual(registry.scanned,200)
                    worker.assert_not_called()
                    # Adding an album invalidates a dict iterator; next
                    # bounded scan must not throw or retire stale objects.
                    registry['new']=types.SimpleNamespace(id='new',loaded=False)
                    controller.tick()
                    controller.tick()
                    self.assertLessEqual(registry.scanned,300)
                    self.assertEqual(self.removed,[])
                finally:
                    controller.stop()

    def test_verified_album_removed_only_after_ui_delivery(self):
        removed,album=self.run_case()
        self.assertEqual(removed,[album])

    def test_worker_mismatch_never_removes(self):
        removed,_=self.run_case(valid=False)
        self.assertEqual(removed,[])

    def test_new_failure_after_worker_readback_prevents_removal(self):
        removed,_=self.run_case(mutate=lambda tracker,album:setattr(tracker,'failed',True))
        self.assertEqual(removed,[])

    def test_concurrent_save_after_readback_prevents_removal(self):
        removed,_=self.run_case(mutate=lambda tracker,album:setattr(tracker,'inflight',True))
        self.assertEqual(removed,[])

    def test_removed_album_during_readback_cannot_be_removed_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            api,album=self.context(directory)
            tracker=Tracker()
            def mutate(tracker,album):
                api.tagger.albums.clear()
            # Separate locally to ensure same API is passed into a controller.
            with patch.dict(sys.modules,qt_stub()), patch.object(gold,'verify_gold_files',return_value=True):
                controller=gold.start_gold_retirement(api,tracker)
                try:
                    controller.tick()
                    until=time.monotonic()+5
                    while not controller.finished.messages and time.monotonic()<until:
                        time.sleep(.005)
                    self.assertTrue(controller.finished.messages)
                    api.tagger.albums.clear()
                    controller.finished.flush()
                    self.assertEqual(self.removed,[])
                finally:
                    controller.stop()


if __name__=='__main__':
    unittest.main()
