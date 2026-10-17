"""Picard 3 gold UI retirement gates; entirely disposable, no personal media."""
import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

MODULE = pathlib.Path(__file__).resolve().parents[1] / "neowulf_picard_repair" / "gold_retirement.py"
spec = importlib.util.spec_from_file_location("gold_retirement_pure_test", MODULE)
gold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gold)


def fields():
    return {"artist": "Artist", "title": "Track", "album": "Album",
            "tracknumber": "2", "discnumber": "1", "albumartist": "Artist"}


class Track:
    def is_complete(self):
        return True


class AudioFile:
    def __init__(self, filename):
        self.filename = str(filename)
        self.metadata = fields()
        self.orig_metadata = fields()
        self.errors = []
        self.saved = True

    def is_saved(self):
        return self.saved


class Album:
    id = "valid-release"
    loaded = True

    def __init__(self, files):
        self.files = files
        self.tracks = [Track() for _ in files]
        self.errors = []
        self.complete = True
        self.unmatched = 0
        self.unsaved = 0

    def is_complete(self):
        return self.complete

    def get_num_unmatched_files(self):
        return self.unmatched

    def get_num_unsaved_files(self):
        return self.unsaved

    def get_num_matched_tracks(self):
        return len(self.tracks)

    def iterfiles(self):
        return iter(self.files)


class Tagger:
    def __init__(self, album):
        self.albums = {album.id: album}


class Tracker:
    def __init__(self):
        self.inflight = False
        self.states = {}

    def has_inflight(self):
        return self.inflight

    def path_state(self, path):
        return self.states.get(str(path))


class FakeFlac:
    def __init__(self, tags=None, duration=180):
        self.tags = tags or {k: [v] for k, v in fields().items()}
        self.info = types.SimpleNamespace(length=duration)


class GoldTests(unittest.TestCase):
    def prepared(self, root):
        path = pathlib.Path(root) / "track.flac"
        path.write_bytes(b"fake-flac-test-only")
        file = AudioFile(path)
        album = Album([file])
        return path, file, album, Tagger(album), Tracker()

    def test_complete_gold_snapshot_has_all_fields(self):
        with tempfile.TemporaryDirectory() as root:
            path, file, album, tagger, tracker = self.prepared(root)
            snap = gold.capture_gold(album, tagger, tracker)
            self.assertEqual(snap[0], album.id)
            self.assertEqual(snap[1][0][0], str(path))

    def test_no_unmatched_unsaved_or_not_loaded(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            for key, value in (("unmatched", 1), ("unsaved", 1), ("complete", False), ("loaded", False)):
                setattr(album, key, value)
                self.assertIsNone(gold.capture_gold(album, tagger, tracker), key)
                setattr(album, key, True if key in ("complete", "loaded") else 0)

    def test_no_gold_with_conflict_or_modified_file(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            file.metadata["~picardwulf_review"] = "LATER_RELEASE_CONFLICT"
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))
            file.metadata.pop("~picardwulf_review")
            file.saved = False
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))
            file.saved = True
            file.errors = ["write failed"]
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))

    def test_no_gold_if_mp3_or_missing_tags(self):
        with tempfile.TemporaryDirectory() as root:
            path, file, album, tagger, tracker = self.prepared(root)
            file.filename = str(path.with_suffix(".mp3"))
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))
            file.filename = str(path)
            file.metadata.pop("discnumber")
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))

    def test_pending_failed_save_blocks_even_perfect_picard_icon(self):
        with tempfile.TemporaryDirectory() as root:
            path, file, album, tagger, tracker = self.prepared(root)
            tracker.inflight = True
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))
            tracker.inflight = False
            for state in ("MISMATCH", "UNKNOWN_TIMEOUT", "UNVERIFIED", "START_FAILED", "PENDING"):
                tracker.states[str(path)] = state
                self.assertIsNone(gold.capture_gold(album, tagger, tracker), state)
            tracker.states[str(path)] = "VERIFIED"
            self.assertIsNotNone(gold.capture_gold(album, tagger, tracker))

    def test_original_metadata_disagreement_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            file.orig_metadata["title"] = "Different"
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))

    def test_optional_release_id_change_blocks_gold(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            file.orig_metadata['musicbrainz_albumid'] = 'release-A'
            file.metadata['musicbrainz_albumid'] = 'release-B'
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))

    def test_optional_album_id_removed_blocks_gold(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            file.orig_metadata['musicbrainz_albumid'] = 'release-A'
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))

    def test_multivalue_genre_secondary_mismatch_blocks_gold(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            file.orig_metadata['genre'] = ['Techno', 'Hardcore']
            file.metadata['genre'] = ['Techno', 'Gabber']
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))

    def test_real_picard_getall_separates_multivalues(self):
        class PicardMetadata:
            def __init__(self, values):
                self.values=values
            def getall(self, key):
                return self.values.get(key, [])
            def get(self, key, default=''):
                return '; '.join(self.getall(key)) or default

        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            file.metadata=PicardMetadata({**{k:[v] for k,v in fields().items()},
                                          'genre':['Techno','Hardcore']})
            file.orig_metadata=PicardMetadata({**{k:[v] for k,v in fields().items()},
                                               'genre':['Techno','Gabber']})
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))
            file.orig_metadata=PicardMetadata({**{k:[v] for k,v in fields().items()},
                                               'genre':['Techno','Hardcore']})
            snapshot=gold.capture_gold(album,tagger,tracker)
            self.assertIsNotNone(snapshot)
            self.assertIn(('genre',('Techno','Hardcore')),snapshot[1][0][1])

    def test_disk_readback_all_multivalues_must_match(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            file.orig_metadata['genre'] = ['Techno', 'Hardcore']
            file.metadata['genre'] = ['Techno', 'Hardcore']
            snap = gold.capture_gold(album, tagger, tracker)
            self.assertIsNotNone(snap)
            module = types.ModuleType('mutagen')
            flac_mod = types.ModuleType('mutagen.flac')
            flac_mod.FLAC = FakeFlac
            wrong = FakeFlac()
            wrong.tags['genre'] = ['Techno', 'Gabber']
            module.File = lambda *args, **kwargs: wrong
            with patch.dict(sys.modules, {'mutagen': module, 'mutagen.flac': flac_mod}):
                self.assertFalse(gold.verify_gold_files(snap))
            right = FakeFlac()
            right.tags['genre'] = ['Techno', 'Hardcore']
            module.File = lambda *args, **kwargs: right
            with patch.dict(sys.modules, {'mutagen': module, 'mutagen.flac': flac_mod}):
                self.assertTrue(gold.verify_gold_files(snap))

    def test_disk_readback_accepts_matching_flac(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            snap = gold.capture_gold(album, tagger, tracker)
            module = types.ModuleType("mutagen")
            flac_mod = types.ModuleType("mutagen.flac")
            flac_mod.FLAC = FakeFlac
            module.File = lambda *args, **kwargs: FakeFlac()
            with patch.dict(sys.modules, {"mutagen": module, "mutagen.flac": flac_mod}):
                self.assertTrue(gold.verify_gold_files(snap))

    def test_disk_readback_rejects_wrong_tag(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            snap = gold.capture_gold(album, tagger, tracker)
            module = types.ModuleType("mutagen")
            flac_mod = types.ModuleType("mutagen.flac")
            flac_mod.FLAC = FakeFlac
            wrong = FakeFlac()
            wrong.tags["title"] = ["Unrelated Song"]
            module.File = lambda *args, **kwargs: wrong
            with patch.dict(sys.modules, {"mutagen": module, "mutagen.flac": flac_mod}):
                self.assertFalse(gold.verify_gold_files(snap))

    def test_disk_readback_rejects_deleted_file(self):
        with tempfile.TemporaryDirectory() as root:
            path, file, album, tagger, tracker = self.prepared(root)
            snap = gold.capture_gold(album, tagger, tracker)
            path.unlink()
            self.assertFalse(gold.verify_gold_files(snap))

    def test_stale_album_reference_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            _, file, album, tagger, tracker = self.prepared(root)
            tagger.albums[album.id] = Album([file])
            self.assertIsNone(gold.capture_gold(album, tagger, tracker))


if __name__ == "__main__":
    unittest.main()
