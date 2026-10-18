"""Native Picard core-collision adapter tests, with disposable fake FLAC bytes."""
import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType("native_collision_contract_tests")
pkg.__path__=[str(ROOT/"neowulf_picard_repair")]
sys.modules[pkg.__name__]=pkg
bridge=importlib.import_module(pkg.__name__+".native_move_bridge")
importer=importlib.import_module(pkg.__name__+".staged_flac_import")


def fake_inspect(path):
    p=Path(path)
    return {
        "extension": ".flac",
        "identity": ("Artist","Track","Album","1","1"),
        "seconds": 210,
        "size": p.stat().st_size,
    }


class NativeMoveBridgeTests(unittest.TestCase):
    def roots(self, directory, existing=20, incoming=60):
        root=Path(directory)
        staging=root/"staging"
        library=root/"library"
        recovery=root/"recovery"
        for d in (staging,library,recovery):
            d.mkdir()
        src=staging/"Audio.flac"
        dst=library/"Audio.flac"
        src.write_bytes(b"S"*incoming)
        if existing is not None:
            dst.write_bytes(b"T"*existing)
        settings={
            "move_files":True,
            "move_files_to":str(library),
            "move_overwrite_existing_files":False,
        }
        def move(source,destination,**kw):
            return importer.import_staged_flac(
                source,destination,**kw,inspect=fake_inspect,
                decode=lambda path:True)
        return src,dst,recovery,settings,move

    def test_replace_copies_verified_larger_flac_and_keeps_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp)
            original=dst.read_bytes()
            result=bridge.arbitrate_native_flac_move(
                src,dst,settings,backup,import_fn=move)
            self.assertEqual(result["action"],"COMMITTED")
            self.assertEqual(dst.read_bytes(),src.read_bytes())
            self.assertEqual(Path(result["backup"]).read_bytes(),original)
            self.assertTrue(src.exists())

    def test_same_size_or_larger_canonical_stays_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp,existing=90)
            original=dst.read_bytes()
            result=bridge.arbitrate_native_flac_move(
                src,dst,settings,backup,import_fn=move)
            self.assertEqual(result["action"],"KEEP")
            self.assertEqual(dst.read_bytes(),original)
            self.assertEqual(list(backup.iterdir()),[])

    def test_create_missing_album_target_without_losing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp,existing=None)
            target=dst.parent/"Series"/"Volume 2"/dst.name
            result=bridge.arbitrate_native_flac_move(
                src,target,settings,backup,import_fn=move)
            self.assertEqual(result["action"],"COMMITTED")
            self.assertEqual(target.read_bytes(),src.read_bytes())
            self.assertTrue(src.is_file())

    def test_loaded_destination_is_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp)
            fn=Mock()
            result=bridge.arbitrate_native_flac_move(
                src,dst,settings,backup,destination_loaded=True,import_fn=fn)
            self.assertEqual(result["action"],"KEEP")
            fn.assert_not_called()
            self.assertEqual(dst.read_bytes(),b"T"*20)

    def test_unsafe_native_overwrite_or_incomplete_profile_never_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp)
            fn=Mock()
            for mods in ({"move_overwrite_existing_files":True},
                         {"move_files":False},
                         {"move_files_to":""}):
                active=dict(settings,**mods)
                res=bridge.arbitrate_native_flac_move(
                    src,dst,active,backup,import_fn=fn)
                self.assertEqual(res["action"],"KEEP")
            settings.pop("move_files_to")
            self.assertEqual(bridge.arbitrate_native_flac_move(
                src,dst,settings,backup,import_fn=fn)["action"],"KEEP")
            fn.assert_not_called()

    def test_other_format_explicitly_unhandled(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp)
            result=bridge.arbitrate_native_flac_move(
                src.with_suffix(".mp3"),dst.with_suffix(".mp3"),
                settings,backup,import_fn=Mock())
            self.assertEqual(result["action"],"UNHANDLED")

    def test_unexpected_import_result_is_not_treated_as_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp)
            with self.assertRaises(importer.StagedImportRejected):
                bridge.arbitrate_native_flac_move(
                    src,dst,settings,backup,
                    import_fn=lambda *a,**k: {"action":"UNKNOWN"})

    def test_fake_commit_not_matching_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp)
            def fake_commit(*args,**kwargs):
                return {"action":"REPLACED","backup":"unverified"}
            with self.assertRaises(importer.StagedImportRejected):
                bridge.arbitrate_native_flac_move(
                    src,dst,settings,backup,import_fn=fake_commit)

    def test_missing_recovery_root_refuses_even_free_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,backup,settings,move=self.roots(tmp,existing=None)
            result=bridge.arbitrate_native_flac_move(
                src,dst,settings,backup/"missing",import_fn=Mock())
            self.assertEqual(result["action"],"KEEP")
            self.assertFalse(dst.exists())


if __name__=="__main__":
    unittest.main()
