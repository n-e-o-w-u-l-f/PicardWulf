"""Execute pinned upstream File.save worker under deliberate profile/naming drift.

An isolated official patched Picard 3.0.2 checkout is supplied by
PICARD302_SOURCE. Without it the test class skips; no live media is touched.
"""
import ast
import copy
import functools
import os
from pathlib import Path
import tempfile
import types
import unittest


class NativeSavePlanDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checkout=os.environ.get("PICARD302_SOURCE")
        if not checkout:
            raise unittest.SkipTest("Need separately patched Picard 3.0.2 checkout")
        root=Path(checkout)
        tree=ast.parse((root/"picard/file.py").read_text(encoding="utf-8"))
        original=next(node for node in tree.body
                      if isinstance(node,ast.ClassDef) and node.name=="File")
        names={"save","_save_and_rename","_rename"}
        methods=[copy.deepcopy(node) for node in original.body
                 if isinstance(node,ast.FunctionDef) and node.name in names]
        if len(methods)!=3:
            raise AssertionError("Picard native Save/worker/move methods missing")
        for method in methods:
            method.decorator_list=[]
        cls.harness=ast.fix_missing_locations(ast.Module(
            body=[ast.ClassDef(name="RealFile",bases=[],keywords=[],
                               decorator_list=[],body=methods)],
            type_ignores=[]))
        cls.code=compile(cls.harness,str(root/"picard/file.py"),"exec")

    def create_queued_save(self,root):
        staging=root/"staging"
        library=root/"library"
        staging.mkdir()
        library.mkdir()
        source=staging/"Music.flac"
        source.write_bytes(b"TEST_ORIGINAL")
        active={
            "rename_files":True,
            "move_files":True,
            "move_files_to":str(library),
            "move_overwrite_existing_files":False,
            "test_naming":"Album",
            "enable_tag_saving":True,
            "preserve_timestamps":False,
            "delete_empty_dirs":False,
            "save_images_to_files":False,
        }
        queued=[]
        calls=[]
        class Meta(dict):
            def copy(self,other):
                self.clear()
                self.update(other)
        class Processor:
            def prepare(self):
                return (True,str(root/"recovery"))
            def __call__(self,old,new,settings,loaded,policy):
                calls.append(("collision",str(new),policy))
                return {"action":"KEEP"}
        resolver=Processor()
        globals_={
            "os":os,
            "Metadata":Meta,
            "IS_WIN":False,
            "get_config":lambda:types.SimpleNamespace(setting=active),
            "log":types.SimpleNamespace(debug=lambda *args:None),
            "File":types.SimpleNamespace(
                State=types.SimpleNamespace(REMOVED="removed")),
            "PICARD_APP_NAME":"Picard",
            "run_file_pre_save_processors":lambda *args:None,
            "file_move_collision_processors":types.SimpleNamespace(
                functions=[resolver]),
            "thread":types.SimpleNamespace(run_task=lambda task,done,thread_pool=None:
                                           queued.append((task,done))),
            "partial":functools.partial,
            "get_available_filename":lambda dest,old:dest,
        }
        exec(self.code,globals_)
        target=lambda: library/active["test_naming"]/"Music.flac"
        obj=globals_["RealFile"]()
        obj.filename=str(source)
        obj.state="normal"
        obj.metadata=Meta(title="Track")
        obj.make_filename=lambda filename,metadata,settings: str(
            library/settings["test_naming"]/"Music.flac")
        obj.set_pending=lambda:None
        obj._saving_finished=lambda *args,**kwargs:None
        obj.tagger=types.SimpleNamespace(
            stopping=False,
            _saving_files_count=0,
            files={str(source):obj},
            save_thread_pool=object())
        def fake_save(filename, metadata):
            calls.append(("tag_write",str(filename)))
            source.write_bytes(b"TAGGED_SOURCE")
        obj._save=fake_save
        obj._retry_on_permission_error=lambda callback:callback()
        obj._move_with_retry=lambda a,b:calls.append(("move",a,b))
        obj._move_additional_files=lambda *args:calls.append(("sidecar",))
        obj.save()
        self.assertEqual(len(queued),1)
        self.assertEqual(obj.tagger._saving_files_count,1)
        return source,target(),active,calls,queued[0][0]

    def test_native_destination_root_change_before_worker_never_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src,dst,settings,calls,worker=self.create_queued_save(root)
            settings["move_files_to"]=str(root/"other")
            with self.assertRaisesRegex(RuntimeError,"before tag save"):
                worker()
            self.assertEqual(src.read_bytes(),b"TEST_ORIGINAL")
            self.assertFalse(dst.exists())
            self.assertFalse(calls)

    def test_native_rename_template_change_before_worker_never_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src,dst,settings,calls,worker=self.create_queued_save(root)
            settings["test_naming"]="Different Album"
            with self.assertRaisesRegex(RuntimeError,"before tag save"):
                worker()
            self.assertEqual(src.read_bytes(),b"TEST_ORIGINAL")
            self.assertFalse(dst.exists())
            self.assertEqual(calls,[])

    def test_native_overwrite_and_move_flags_cannot_drift(self):
        for key,value in (
                ("move_overwrite_existing_files",True),
                ("move_files",False),
                ("rename_files",False)):
            with self.subTest(setting=key),tempfile.TemporaryDirectory() as tmp:
                src,dst,settings,calls,worker=self.create_queued_save(Path(tmp))
                settings[key]=value
                with self.assertRaisesRegex(RuntimeError,"before tag save"):
                    worker()
                self.assertEqual(src.read_bytes(),b"TEST_ORIGINAL")
                self.assertFalse(dst.exists())
                self.assertEqual(calls,[])

    def test_change_during_tag_write_aborts_before_library_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src,dst,settings,calls,worker=self.create_queued_save(root)
            def tag_then_change(file,meta):
                calls.append(("tag_write",file))
                settings["test_naming"]="Other Album"
                src.write_bytes(b"TAGGED_SOURCE")
            # Obtain the bound object without executing the worker.
            native_file=worker.func.__self__
            native_file._save=tag_then_change
            with self.assertRaisesRegex(RuntimeError,"during tag save"):
                worker()
            # Metadata tag writes happened before the late profile change.
            # Canonical media and sidecars must remain completely untouched.
            self.assertEqual(src.read_bytes(),b"TAGGED_SOURCE")
            self.assertFalse(dst.exists())
            self.assertEqual([kind for kind,*_ in calls],["tag_write"])


if __name__=="__main__":
    unittest.main()
