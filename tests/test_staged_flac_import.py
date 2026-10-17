"""Disposable staging-root -> canonical-library FLAC arbitration regressions."""
import importlib
from pathlib import Path
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
package=types.ModuleType("picardwulf_import_test")
package.__path__=[str(ROOT/"neowulf_picard_repair")]
sys.modules[package.__name__]=package
imp=importlib.import_module(package.__name__+".staged_flac_import")


def fake_inspect(path):
    path=Path(path)
    if not path.is_file() or path.suffix.casefold()!=".flac":
        raise ValueError("Not flac")
    # Test fixtures have synthetic bytes but a correctly shaped known identity.
    identity=("artist","title","album","1","2")
    if b"DIFFERENT" in path.read_bytes():
        identity=("other","track","album","1","2")
    return {"path":path,"extension":".flac","size":path.stat().st_size,
            "identity":identity,"seconds":181.5}


class StagedImportTests(unittest.TestCase):
    def fixture(self, root, *, existing=15, incoming=60):
        base=Path(root)
        staging, library, backup=(base/n for n in ("staging","library","recovery"))
        for folder in (staging, library, backup):
            folder.mkdir()
        source=staging/"Track.flac"
        target=library/"Track.flac"
        source.write_bytes(b"S"*incoming)
        if existing is not None:
            target.write_bytes(b"T"*existing)
        opts={"staging_root":staging,"library_root":library,
              "recovery_root":backup,"inspect":fake_inspect,
              "decode":lambda p:True}
        return source,target,backup,opts

    def test_default_dry_run_larger_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            baseline=(src.read_bytes(),dst.read_bytes())
            report=imp.import_staged_flac(src,dst,**opt)
            self.assertEqual(report["action"],"WOULD_REPLACE")
            self.assertEqual((src.read_bytes(),dst.read_bytes()),baseline)
            self.assertEqual(list(back.iterdir()),[])

    def test_replace_smaller_target_with_sha_verified_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            old=dst.read_bytes()
            report=imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(report["action"],"REPLACED")
            self.assertEqual(dst.read_bytes(),src.read_bytes())
            self.assertEqual(Path(report["backup"]).read_bytes(),old)
            self.assertEqual(src.read_bytes(),b"S"*60)
            self.assertFalse(any(p.name.endswith(".lock") for p in back.iterdir()))

    def test_post_commit_decoder_failure_restores_existing_flac(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target, recovery, opts = self.fixture(tmp)
            old_bytes=target.read_bytes()
            new_bytes=source.read_bytes()
            def decoder(path):
                data=Path(path).read_bytes()
                # Before commit both streams pass; after atomically replacing
                # target with the larger source, target decodes as invalid.
                return not (Path(path)==target and data==new_bytes)
            opts['decode']=decoder
            with self.assertRaises(imp.StagedImportRejected) as err:
                imp.import_staged_flac(source,target,apply=True,**opts)
            self.assertIn('original restored',str(err.exception))
            self.assertEqual(target.read_bytes(),old_bytes)
            self.assertEqual(source.read_bytes(),new_bytes)
            backups=[p for p in recovery.iterdir() if p.is_file()]
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_bytes(),old_bytes)

    def test_preserve_larger_target_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp,existing=90,incoming=15)
            old=dst.read_bytes()
            result=imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(result["action"],"SKIPPED")
            self.assertEqual(dst.read_bytes(),old)
            self.assertTrue(src.is_file())
            self.assertEqual(list(back.iterdir()),[])

    def test_equal_size_keeps_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,_,opt=self.fixture(tmp,existing=15,incoming=15)
            self.assertEqual(imp.import_staged_flac(src,dst,apply=True,**opt)["action"],"SKIPPED")
            self.assertEqual(dst.read_bytes(),b"T"*15)

    def test_new_target_exclusive_create_no_source_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp,existing=None)
            self.assertEqual(imp.import_staged_flac(src,dst,**opt)["action"],"WOULD_CREATE")
            self.assertFalse(dst.exists())
            result=imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(result["action"],"CREATED")
            self.assertEqual(dst.read_bytes(),src.read_bytes())
            self.assertTrue(src.exists())
            self.assertEqual(list(back.iterdir()),[])

    def test_missing_nested_album_and_series_folder_created_only_on_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp,existing=None)
            target=Path(opt["library_root"])/"Various Artists"/"Bravo Hits"/"Volume 03"/"Track.flac"
            self.assertEqual(imp.import_staged_flac(src,target,**opt)["action"],"WOULD_CREATE")
            self.assertFalse(target.parent.exists())
            result=imp.import_staged_flac(src,target,apply=True,**opt)
            self.assertEqual(result["action"],"CREATED")
            self.assertEqual(target.read_bytes(),src.read_bytes())
            self.assertTrue(src.is_file())

    def test_failed_create_removes_only_new_empty_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp,existing=None)
            target=Path(opt["library_root"])/"Artist"/"Album"/"Track.flac"
            with patch.object(imp.os,"link",side_effect=OSError("Not supported")):
                with self.assertRaises(imp.StagedImportRejected):
                    imp.import_staged_flac(src,target,apply=True,**opt)
            self.assertFalse(target.parent.exists())
            self.assertFalse((Path(opt["library_root"])/"Artist").exists())
            self.assertTrue(Path(opt["library_root"]).is_dir())
            self.assertTrue(src.is_file())

    def test_reviewed_replace_success_is_bound_to_original_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            snapshot=imp.import_staged_flac(src,dst,**opt)
            self.assertEqual(snapshot["action"],"WOULD_REPLACE")
            self.assertEqual(len(snapshot["source_sha256"]),64)
            self.assertEqual(len(snapshot["destination_sha256"]),64)
            out=imp.import_staged_flac(src,dst,apply=True,
                                       expected_preview=snapshot,**opt)
            self.assertEqual(out["action"],"REPLACED")
            self.assertEqual(dst.read_bytes(),src.read_bytes())
            self.assertTrue(src.is_file())

    def test_changed_staging_bytes_after_preview_abstains(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            snapshot=imp.import_staged_flac(src,dst,**opt)
            old=dst.read_bytes()
            src.write_bytes(b"X"*src.stat().st_size) # same size and identity
            with self.assertRaisesRegex(imp.StagedImportRejected,
                                        "changed after confirmed preview"):
                imp.import_staged_flac(src,dst,apply=True,
                                       expected_preview=snapshot,**opt)
            self.assertEqual(dst.read_bytes(),old)
            self.assertEqual(list(back.iterdir()),[])

    def test_changed_destination_bytes_after_preview_abstains(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            snapshot=imp.import_staged_flac(src,dst,**opt)
            dst.write_bytes(b"Z"*dst.stat().st_size)
            with self.assertRaisesRegex(imp.StagedImportRejected,
                                        "changed after confirmed preview"):
                imp.import_staged_flac(src,dst,apply=True,
                                       expected_preview=snapshot,**opt)
            self.assertEqual(dst.read_bytes(),b"Z"*15)
            self.assertTrue(src.is_file())
            self.assertEqual(list(back.iterdir()),[])

    def test_new_destination_appears_during_confirmation_abstains(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp,existing=None)
            snapshot=imp.import_staged_flac(src,dst,**opt)
            self.assertEqual(snapshot["action"],"WOULD_CREATE")
            dst.write_bytes(b"ANOTHER_USER_TRACK")
            with self.assertRaisesRegex(imp.StagedImportRejected,
                                        "changed after confirmed preview"):
                imp.import_staged_flac(src,dst,apply=True,
                                       expected_preview=snapshot,**opt)
            self.assertEqual(dst.read_bytes(),b"ANOTHER_USER_TRACK")
            self.assertEqual(list(back.iterdir()),[])

    def test_missing_album_directory_stays_absent_if_preview_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp,existing=None)
            album=Path(opt["library_root"])/"Series"/"Volume II"/"Track.flac"
            snapshot=imp.import_staged_flac(src,album,**opt)
            src.write_bytes(b"NEW"*20)
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,album,apply=True,
                                       expected_preview=snapshot,**opt)
            self.assertFalse(album.parent.exists())
            self.assertEqual(list(back.iterdir()),[])

    def test_manipulated_expected_decision_cannot_be_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            snapshot=imp.import_staged_flac(src,dst,**opt)
            forged=dict(snapshot,action="WOULD_SKIP")
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,dst,apply=True,
                                       expected_preview=forged,**opt)
            self.assertEqual(dst.read_bytes(),b"T"*15)
            self.assertEqual(list(back.iterdir()),[])

    def test_conflicting_identity_is_review_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp,incoming=40,existing=20)
            src.write_bytes(b"DIFFERENT"+b"S"*40)
            old=dst.read_bytes()
            result=imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(result["action"],"REVIEW")
            self.assertEqual(dst.read_bytes(),old)
            self.assertEqual(list(back.iterdir()),[])

    def test_decode_failure_denies_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            opt["decode"]=lambda _:False
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(dst.read_bytes(),b"T"*15)
            self.assertEqual(list(back.iterdir()),[])

    def test_reject_mp3_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,_,opt=self.fixture(tmp)
            mp3=src.with_suffix(".mp3")
            mp3.write_bytes(b"NOT_AUDIO")
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(mp3,dst,apply=True,**opt)

    def test_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,_,opt=self.fixture(tmp)
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,Path(tmp)/"outside.flac",apply=True,**opt)
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(dst,dst,apply=True,**opt)

    def test_reject_roots_overlapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            opt["recovery_root"]=Path(tmp)/"staging"
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,dst,apply=True,**opt)

    def test_reject_symlink_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,_,opt=self.fixture(tmp)
            inside=Path(tmp)/"library"/"real"
            inside.mkdir()
            alias=Path(tmp)/"library"/"alias"
            try:
                alias.symlink_to(inside,target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,alias/"Track.flac",apply=True,**opt)

    def test_reject_source_and_destination_hardlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            dst.unlink()
            try:
                os.link(src,dst)
            except OSError:
                self.skipTest("Hardlinks unavailable")
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(dst.read_bytes(),src.read_bytes())
            self.assertEqual(list(back.iterdir()),[])

    def test_stale_lock_blocks_while_preserving_music(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,back,opt=self.fixture(tmp)
            import hashlib
            marker=back/("picardwulf-"+hashlib.sha256(
                str(dst).casefold().encode("utf-8")).hexdigest()+".lock")
            marker.write_text("stale",encoding="utf-8")
            before=dst.read_bytes()
            with self.assertRaises(imp.StagedImportRejected):
                imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(dst.read_bytes(),before)
            self.assertEqual(marker.read_text(),"stale")

    def test_exclusive_create_refuses_concurrent_file_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,dst,_,opt=self.fixture(tmp,existing=None)
            from unittest.mock import patch
            original=imp.os.link
            def collision(source,target,**kw):
                Path(target).write_bytes(b"OTHER_TASK")
                raise FileExistsError("concurrent")
            with patch.object(imp.os,"link",side_effect=collision):
                with self.assertRaises(imp.StagedImportRejected):
                    imp.import_staged_flac(src,dst,apply=True,**opt)
            self.assertEqual(dst.read_bytes(),b"OTHER_TASK")
            self.assertTrue(src.exists())


if __name__=="__main__":
    unittest.main()
