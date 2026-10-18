"""Version-pinned source-level contract test for a patched Picard 3.0.2 core.

Run with PICARD302_SOURCE=/path/to/isolated/patched/picard/repo .
The normal PicardWulf suite skips the genuine core tests without the
separate upstream checkout. No Qt imports or user media required.
"""
import ast
import copy
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock


class NativePicard302CoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=os.environ.get("PICARD302_SOURCE")
        if not root or not (Path(root)/"picard/file.py").is_file():
            raise unittest.SkipTest("patched Picard 3.0.2 source checkout not supplied")
        tree=ast.parse((Path(root)/"picard/file.py").read_text())
        found=[node for node in tree.body if isinstance(node,ast.ClassDef)
               and node.name=="File"]
        if len(found)!=1:
            raise AssertionError("Picard 3.0.2 File class missing")
        rename=[node for node in found[0].body if isinstance(node,ast.FunctionDef)
                and node.name=="_rename"]
        if len(rename)!=1:
            raise AssertionError("native _rename method missing")
        method=copy.deepcopy(rename[0])
        method.decorator_list=[]
        harness=ast.ClassDef(
            name="Harness", bases=[], keywords=[],
            body=[method],decorator_list=[])
        ast.fix_missing_locations(harness)
        module=ast.Module(body=[harness],type_ignores=[])
        cls.code=compile(module,"<real-patched-Picard-3.0.2-file.py>","exec")

    def setup_native(self,callbacks,new_target):
        import os as real_os
        namespace={
            "os":real_os,
            "file_move_collision_processors":types.SimpleNamespace(
                functions=callbacks),
            "log":types.SimpleNamespace(debug=lambda *args:None),
            "get_available_filename":lambda dst,src:dst,
        }
        exec(self.code,namespace)
        instance=namespace["Harness"]()
        instance.make_filename=lambda old,metadata,settings:str(new_target)
        instance.moves=[]
        def move(old,new):
            instance.moves.append((old,new))
            Path(new).write_bytes(Path(old).read_bytes())
        instance._move_with_retry=move
        return instance

    def settings(self):
        return {"move_files":True,"move_overwrite_existing_files":False,
                "rename_files":True}

    def test_native_core_keep_aborts_move_without_modifying_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"source"); dst.write_bytes(b"existing")
            handler=Mock(return_value={"action":"KEEP"})
            file=self.setup_native([handler],dst)
            result=file._rename(str(src),{},self.settings(),True)
            self.assertEqual(result,str(src))
            self.assertEqual(dst.read_bytes(),b"existing")
            self.assertEqual(file.moves,[])
            self.assertTrue(handler.call_args.args[3])

    def test_native_core_precommitted_copy_skips_private_move(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"large")
            def handler(old,new,settings,loaded):
                self.assertFalse(loaded)
                Path(new).write_bytes(Path(old).read_bytes())
                return {"action":"COMMITTED","destination":new}
            file=self.setup_native([handler],dst)
            result=file._rename(str(src),{},self.settings(),False)
            self.assertEqual(result,str(dst))
            self.assertEqual(dst.read_bytes(),src.read_bytes())
            self.assertTrue(src.is_file())
            self.assertEqual(file.moves,[])

    def test_native_core_unregistered_preserves_old_upstream_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"source")
            file=self.setup_native([],dst)
            self.assertEqual(file._rename(str(src),{},self.settings()),str(dst))
            self.assertEqual(len(file.moves),1)

    def test_native_core_unhandled_preserves_standard_file_move(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"source")
            file=self.setup_native([lambda *args:{"action":"UNHANDLED"}],dst)
            self.assertEqual(file._rename(str(src),{},self.settings()),str(dst))
            self.assertEqual(len(file.moves),1)

    def test_native_core_bad_receipt_refuses_unverified_commit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"source")
            file=self.setup_native([
                lambda *args:{"action":"COMMITTED","destination":"wrong.flac"}
            ],dst)
            with self.assertRaises(RuntimeError):
                file._rename(str(src),{},self.settings())
            self.assertFalse(dst.exists())
            self.assertEqual(file.moves,[])

    def test_two_collision_resolvers_cannot_both_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"source")
            file=self.setup_native([lambda *args:None, lambda *args:None],dst)
            with self.assertRaises(RuntimeError):
                file._rename(str(src),{},self.settings())
            self.assertEqual(file.moves,[])


if __name__=="__main__":
    unittest.main()
