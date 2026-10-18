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
        save_worker=[node for node in found[0].body
                     if isinstance(node,ast.FunctionDef)
                     and node.name=="_save_and_rename"]
        if len(save_worker)!=1:
            raise AssertionError("native save worker missing")
        save_worker=copy.deepcopy(save_worker[0])
        save_worker.decorator_list=[]
        harness=ast.ClassDef(
            name="Harness", bases=[], keywords=[],
            body=[method,save_worker],decorator_list=[])
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
            "File":types.SimpleNamespace(State=types.SimpleNamespace(
                REMOVED="removed")),
            "PICARD_APP_NAME":"Picard",
            "get_config":lambda:types.SimpleNamespace(setting={
                "enable_tag_saving":False,"rename_files":True,
                "move_files":True,"move_overwrite_existing_files":False,
                "move_files_to":str(Path(new_target).parent),
                "delete_empty_dirs":False,"save_images_to_files":False,
                "move_additional_files":True,
            }),
        }
        exec(self.code,namespace)
        instance=namespace["Harness"]()
        instance.make_filename=lambda old,metadata,settings:str(new_target)
        instance.moves=[]
        instance.sidecars=[]
        instance._move_additional_files=lambda *args:instance.sidecars.append(args)
        instance.state="normal"
        instance.tagger=types.SimpleNamespace(stopping=False)
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
                return {"action":"COMMITTED","destination":new,
                        "source_preserved":old}
            file=self.setup_native([handler],dst)
            result=file._rename(str(src),{},self.settings(),False)
            self.assertEqual(result,str(src))
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

    def test_native_worker_safe_copy_keeps_staging_companion_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"staging.flac"; dst=root/"library.flac"
            companion=root/"cover.jpg"
            src.write_bytes(b"verified")
            companion.write_bytes(b"cover")
            def handler(old,new,settings,loaded):
                Path(new).write_bytes(Path(old).read_bytes())
                return {"action":"COMMITTED","destination":new,
                        "source_preserved":old}
            file=self.setup_native([handler],dst)
            result=file._save_and_rename(str(src),{},False)
            self.assertEqual(result,str(src))
            self.assertEqual(dst.read_bytes(),src.read_bytes())
            self.assertEqual(companion.read_bytes(),b"cover")
            self.assertEqual(file.sidecars,[])
            self.assertEqual(file.moves,[])

    def test_real_decoded_flac_native_worker_end_to_end(self):
        import shutil
        import subprocess
        import wave
        if not shutil.which("flac"):
            self.skipTest("flac CLI not installed")
        try:
            from mutagen.flac import FLAC
        except ImportError:
            self.skipTest("mutagen not installed")
        import importlib
        import sys
        from pathlib import Path
        import types
        root_pkg="picard302_native_worker_test"
        pkg=types.ModuleType(root_pkg)
        pkg.__path__=[str(Path(__file__).parents[1]/"neowulf_picard_repair")]
        sys.modules[root_pkg]=pkg
        bridge=importlib.import_module(root_pkg+".native_move_bridge")
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            staging=root/"staging"
            library=root/"library"
            recovery=root/"recovery"
            for folder in (staging,library,recovery):
                folder.mkdir()
            wav=root/"test.wav"
            with wave.open(str(wav),"wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(22050)
                f.writeframes(b"\x00\x00"*22050)
            src=staging/"Track.flac"; dest=library/"Track.flac"
            subprocess.run(["flac","-f","--silent","-o",str(src),str(wav)],
                           check=True,capture_output=True)
            tags=FLAC(str(src))
            for k,v in {
                    "artist":"Synthetic Artist","title":"Synthetic Track",
                    "album":"Synthetic Release","discnumber":"1",
                    "tracknumber":"1"}.items():
                tags[k]=v
            tags.save()
            shutil.copy2(src,dest)
            older=dest.read_bytes()
            tags=FLAC(str(src))
            tags["comment"]="Independent high metadata payload "+("Q"*50000)
            tags.save()
            self.assertGreater(src.stat().st_size,dest.stat().st_size)
            companion=staging/"cover.jpg"; companion.write_bytes(b"cover")
            def collision(old,new,settings,loaded):
                return bridge.arbitrate_native_flac_move(
                    old,new,settings,recovery,destination_loaded=loaded)
            file=self.setup_native([collision],dest)
            result=file._save_and_rename(str(src),{},False)
            self.assertEqual(result,str(src))
            self.assertEqual(dest.read_bytes(),src.read_bytes())
            self.assertTrue(src.exists())
            self.assertEqual(companion.read_bytes(),b"cover")
            self.assertEqual(file.moves,[])
            self.assertEqual(file.sidecars,[])
            backups=[p for p in recovery.iterdir() if p.is_file()]
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_bytes(),older)

    def test_late_loaded_canonical_owner_is_not_overwritten_by_copy(self):
        # A second File can be loaded while native saving is asynchronous.
        # Returning source prevents _saving_finished from rewriting that
        # other File's canonical registry entry.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"verified source")
            other_owner=object()
            loaded={str(src):"source File",str(dst):other_owner}
            def handler(old,new,settings,loaded_at_start):
                self.assertFalse(loaded_at_start)
                Path(new).write_bytes(Path(old).read_bytes())
                return {"action":"COMMITTED","destination":new,
                        "source_preserved":old}
            file=self.setup_native([handler],dst)
            result=file._save_and_rename(str(src),{},False)
            self.assertEqual(result,str(src))
            loaded.pop(str(src))
            loaded[result]="source File"
            self.assertIs(loaded[str(dst)],other_owner)
            self.assertEqual(loaded[str(src)],"source File")
            self.assertEqual(dst.read_bytes(),src.read_bytes())

    def test_committed_missing_preserved_source_receipt_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"source.flac"; dst=root/"library.flac"
            src.write_bytes(b"source")
            def bad_handler(old,new,*other):
                Path(new).write_bytes(Path(old).read_bytes())
                return {"action":"COMMITTED","destination":new}
            file=self.setup_native([bad_handler],dst)
            with self.assertRaisesRegex(RuntimeError,"copy receipt"):
                file._rename(str(src),{},self.settings())
            self.assertEqual(file.moves,[])
            self.assertTrue(src.is_file())

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
