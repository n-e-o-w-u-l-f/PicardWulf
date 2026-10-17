"""Synthetic, isolated tests: no real music, Picard process or cloud APIs."""
import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "neowulf_picard_repair" / "retention_policy.py"
spec = importlib.util.spec_from_file_location("retention_test_policy", MODULE)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def inspect(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if not path.is_file() or suffix not in {".mp3", ".flac"}:
        raise policy.RetentionRejected("bad audio")
    # Test fixture injects trusted album identity, independent of random bytes.
    return {"path": path, "extension": suffix, "size": path.stat().st_size,
            "identity": ("eminem", "mockingbird", "encore", "1", "2"),
            "seconds": 260.0}


class RetentionTests(unittest.TestCase):
    def make(self, root, name, size):
        path = Path(root) / name
        path.write_bytes(b"A" * size)
        return path

    def test_existing_larger_is_skipped(self):
        with tempfile.TemporaryDirectory() as t:
            old = self.make(t, "existing.flac", 100)
            new = self.make(t, "incoming.flac", 20)
            self.assertEqual(policy.decide_duplicate(old, new, inspect=inspect)["action"], "SKIP")
            self.assertEqual(old.stat().st_size, 100)

    def test_equal_sized_copy_is_skipped(self):
        with tempfile.TemporaryDirectory() as t:
            old = self.make(t, "existing.flac", 60)
            new = self.make(t, "incoming.flac", 60)
            self.assertEqual(policy.decide_duplicate(old, new, inspect=inspect)["action"], "SKIP")

    def test_verified_larger_flac_replaces_with_rollback_copy(self):
        with tempfile.TemporaryDirectory() as t:
            parent = Path(t)
            media = parent / "media"
            media.mkdir()
            old = self.make(media, "existing.flac", 20)
            new = self.make(media, "incoming.flac", 90)
            result = policy.replace_smaller_flac(old, new, parent / "backups", inspect=inspect)
            self.assertEqual(result["action"], "REPLACED")
            self.assertEqual(old.stat().st_size, 90)
            self.assertEqual(Path(result["backup"]).read_bytes(), b"A" * 20)
            self.assertEqual(new.stat().st_size, 90)

    def test_refuse_mismatched_track(self):
        with tempfile.TemporaryDirectory() as t:
            old = self.make(t, "existing.flac", 20)
            new = self.make(t, "incoming.flac", 90)
            def mismatched(path):
                out = inspect(path)
                if Path(path).name == "incoming.flac":
                    out["identity"] = ("other", "album", "track", "1", "2")
                return out
            self.assertEqual(policy.decide_duplicate(old, new, inspect=mismatched)["action"],
                             "REVIEW")
            self.assertEqual(old.stat().st_size, 20)

    def test_different_musicbrainz_release_prevents_replacement(self):
        with tempfile.TemporaryDirectory() as t:
            old = self.make(t, "existing.flac", 20)
            new = self.make(t, "incoming.flac", 90)
            def tagged(path):
                value = inspect(path)
                release = "mbid-old-release" if Path(path) == old else "mbid-new-release"
                value["evidence"] = (("musicbrainz_albumid", release),)
                return value
            self.assertEqual(policy.decide_duplicate(old, new, inspect=tagged)["action"],
                             "REVIEW")
            self.assertEqual(old.stat().st_size, 20)

    def test_one_sided_isrc_is_not_positive_identity(self):
        with tempfile.TemporaryDirectory() as t:
            old = self.make(t, "existing.flac", 20)
            new = self.make(t, "incoming.flac", 90)
            def tagged(path):
                value = inspect(path)
                value["evidence"] = (("isrc", "DETEST1234567" if Path(path) == old else ""),)
                return value
            self.assertEqual(policy.decide_duplicate(old, new, inspect=tagged)["action"],
                             "REVIEW")

    def test_matching_recording_and_release_ids_permit_size_decision(self):
        with tempfile.TemporaryDirectory() as t:
            old = self.make(t, "existing.flac", 20)
            new = self.make(t, "incoming.flac", 90)
            def tagged(path):
                value = inspect(path)
                value["evidence"] = (("musicbrainz_recordingid", "same-recording"),
                                     ("musicbrainz_albumid", "same-release"),
                                     ("isrc", "DETEST1234567"))
                return value
            self.assertEqual(policy.decide_duplicate(old, new, inspect=tagged)["action"],
                             "REPLACE")

    def test_mp3_never_removed_without_decoded_matching_flac(self):
        with tempfile.TemporaryDirectory() as t:
            mp3 = self.make(t, "track.mp3", 20)
            flac = self.make(t, "track.flac", 50)
            result = policy.remove_verified_mp3(mp3, flac, inspect=inspect, decode=lambda _: False)
            self.assertEqual(result["action"], "REVIEW")
            self.assertTrue(mp3.exists())

    def test_verified_mp3_removed_without_recycle_bin(self):
        with tempfile.TemporaryDirectory() as t:
            mp3 = self.make(t, "track.mp3", 20)
            flac = self.make(t, "track.flac", 50)
            recovery = Path(t) / "recovery.copy"
            recovery.write_bytes(mp3.read_bytes())
            receipt = {"path": str(mp3), "backup": str(recovery),
                       "sha256": hashlib.sha256(mp3.read_bytes()).hexdigest()}
            result = policy.remove_verified_mp3(mp3, flac, backup_receipt=receipt,
                                                inspect=inspect, decode=lambda _: True)
            self.assertEqual(result["action"], "REMOVED")
            self.assertFalse(mp3.exists())
            self.assertTrue(flac.exists())

    def test_verified_pair_without_recovery_receipt_must_not_delete(self):
        with tempfile.TemporaryDirectory() as t:
            mp3 = self.make(t, "track.mp3", 20)
            flac = self.make(t, "track.flac", 50)
            with self.assertRaises(policy.RetentionRejected):
                policy.remove_verified_mp3(mp3, flac, inspect=inspect,
                                           decode=lambda _: True)
            self.assertTrue(mp3.exists())

    def test_mp3_with_no_counterpart_is_retained(self):
        with tempfile.TemporaryDirectory() as t:
            mp3 = self.make(t, "track.mp3", 20)
            result = policy.remove_verified_mp3(mp3, Path(t) / "missing.flac",
                                                inspect=inspect, decode=lambda _: True)
            self.assertEqual(result["action"], "REVIEW")
            self.assertTrue(mp3.exists())

    def test_identical_filename_but_different_track_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as t:
            mp3 = self.make(t, "track.mp3", 20)
            flac = self.make(t, "track.flac", 50)
            def mismatch(path):
                data = inspect(path)
                if Path(path).suffix == ".mp3":
                    data["identity"] = ("different", "song", "release", "1", "1")
                return data
            self.assertEqual(policy.remove_verified_mp3(mp3, flac, inspect=mismatch,
                                                         decode=lambda _: True)["action"], "REVIEW")
            self.assertTrue(mp3.exists())


if __name__ == "__main__":
    unittest.main()
