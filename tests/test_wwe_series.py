import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location(
    'wwe_series_test', ROOT/'neowulf_picard_repair'/'wwe_series.py')
# Standard dataclasses require registered module.
import sys
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)


class WweSeriesTests(unittest.TestCase):
    EXPECTED={
        2:(1997,"WWF The Music, Volume 2"),
        3:(1998,"WWF The Music, Volume 3"),
        4:(1999,"WWF The Music, Volume 4"),
        5:(2001,"WWF The Music, Vol. 5"),
        6:(2004,"ThemeAddict: WWE The Music, Vol. 6"),
        7:(2007,"WWE The Music, Vol. 7"),
        8:(2008,"WWE The Music, Vol. 8"),
        9:(2009,"Voices: WWE The Music, Vol. 9"),
    }
    def test_volumes_2_to_9_requested_exact_canonical_folders(self):
        for number,(year,album) in self.EXPECTED.items():
            with self.subTest(volume=number):
                item=module.wwe_folder(album)
                self.assertIsNotNone(item)
                self.assertEqual(item.volume,number)
                self.assertEqual(item.year,year)
                self.assertEqual(item.relative_folder,
                    f"Various Artists/WWE The Music/{year} - WWE The Music Volume {number}")
                route=module.route_metadata({
                    "album":album, "artist":"Jim Johnston",
                    "albumartist":"Jim Johnston",
                    "_secondaryreleasetype":"compilation",
                })
                self.assertEqual(route["state"],"WWE_SERIES")
                self.assertEqual(route["albumartist_for_folder"],"Various Artists")

    def test_wwe_volume_1_full_metal_ambiguous_year_not_guessed(self):
        title="WWF Full Metal: The Album"
        self.assertIsNone(module.wwe_folder(title))
        self.assertEqual(module.wwe_volume(title),1)
        for year in (1995,1996):
            self.assertEqual(module.wwe_folder(title,str(year)).relative_folder,
                f"Various Artists/WWE The Music/{year} - WWE The Music Volume 1")
        self.assertIsNone(module.wwe_folder(title,"2012"))
        self.assertEqual(module.wwe_folder("WWE: The Music, Volume 1","1996").volume,1)

    def test_volume_10_canonical_still_supported(self):
        f=module.wwe_folder("WWE The Music: A New Day, Vol. 10")
        self.assertEqual(f.relative_folder,
            "Various Artists/WWE The Music/2010 - WWE The Music Volume 10")

    def test_old_reissue_year_uses_original_catalogue_and_reviews(self):
        f=module.wwe_folder("WWF The Music Volume 2", date="2005-03-10")
        self.assertEqual(f.year,1997)
        self.assertTrue(f.year_conflict)
        self.assertFalse(module.wwe_folder("WWE The Music Volume 7","2007").year_conflict)

    def test_does_not_confuse_related_wwe_albums_for_volume_series(self):
        for title in (
            "WWE Uncaged, Volume 9", "WWE Originals",
            "WWE The Music: The Beginning",
            "WWE Wreckless Intent", "WWF Aggression",
            "WWE Greatest Hits Volume 9", "Voices - Vol. 9",
            "ThemeAddict Vol. 6", "WWF Full Metal: Remix",
            "Completely Unrelated: The Music Volume 4",
        ):
            with self.subTest(title=title):
                self.assertIsNone(module.wwe_folder(title))

    def test_normal_artist_compilation_stays_with_albumartist(self):
        for albumartist in ("Eminem","Madonna","Nena","Various Artists"):
            out=module.route_metadata({
                "album":"Greatest Hits", "albumartist":albumartist,
                "artist":"Eminem", "_secondaryreleasetype":"compilation",
            })
            if albumartist=="Various Artists":
                self.assertEqual(out["state"],"VA_OR_REVIEW")
                self.assertTrue(out["needs_review"])
            else:
                self.assertEqual(out["state"],"ARTIST_ALBUM")
                self.assertEqual(out["albumartist_for_folder"],albumartist)
                self.assertFalse(out["needs_review"])

    def test_single_track_performer_cannot_override_va_sampler_credit(self):
        data={"album":"Bravo Hits, Vol. 38","albumartist":"Various Artists",
              "artist":"Eminem","_secondaryreleasetype":"compilation"}
        out=module.route_metadata(data)
        self.assertEqual(out["albumartist_for_folder"],"Various Artists")
        self.assertTrue(out["needs_review"])
        self.assertEqual(data["albumartist"],"Various Artists")

    def test_provider_artist_and_missing_album_remain_review(self):
        for artist in ("Apple Music", "Spotify", ""):
            self.assertEqual(module.route_metadata({
                "album":"Curtain Call 2","artist":"Eminem",
                "albumartist":artist})["state"],"REVIEW")
        self.assertEqual(module.route_metadata({"album":""})["state"],"REVIEW")

    def test_native_picard_script_function_has_no_disk_side_effects(self):
        expected="Various Artists/WWE The Music/2009 - WWE The Music Volume 9"
        self.assertEqual(
            module.picard_wwe_folder(None,"Voices: WWE The Music, Vol. 9","2009"),expected)
        self.assertEqual(module.picard_wwe_folder(None,"Encore","2004"),"")


class WweInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location(
            "wwe_audit_test",ROOT/"tools"/"audit_wwe_music.py")
        cls.audit=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.audit)

    def test_readonly_find_displaced_volumes_from_audio_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            misplaced=root/"Various Artists"/"Wrong releases"/"Track.flac"
            misplaced.parent.mkdir(parents=True)
            misplaced.write_bytes(b"fake audio - read-only tags injected")
            correct=root/"Various Artists"/"WWE The Music"/"2009 - WWE The Music Volume 9"/"Track.mp3"
            correct.parent.mkdir(parents=True)
            correct.write_bytes(b"non-destructive")
            files={
                misplaced:{"album":"WWF The Music, Volume 2","artist":"Jim Johnston"},
                correct:{"album":"Voices: WWE The Music, Vol. 9"},
            }
            result=self.audit.scan_library([root],reader=lambda p:files[p])
            self.assertEqual(result["audio_files_scanned"],2)
            self.assertEqual(result["by_volume"]["2"]["misplaced_candidates"],1)
            self.assertEqual(result["by_volume"]["9"]["misplaced_candidates"],0)
            self.assertEqual(misplaced.read_bytes(),b"fake audio - read-only tags injected")
            self.assertEqual(correct.read_bytes(),b"non-destructive")
            self.assertEqual(result["status"],"READ_ONLY_NO_MOVES")

    def test_solo_compilation_false_various_credit_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            va=root/"Various Artists"/"Curtain Call 2"
            va.mkdir(parents=True)
            files={}
            for i in range(1,5):
                f=va/f"{i:02d} Song {i}.flac"
                f.write_bytes(b"untouched musician audio file")
                files[f]={"album":"Curtain Call 2",
                          "albumartist":"Various Artists","artist":"Eminem"}
            report=self.audit.scan_library([root],reader=lambda p:files[p])
            flagged=report["potentially_misfiled_artist_compilations"]
            self.assertEqual(len(flagged),1)
            self.assertEqual(flagged[0]["artist"],"eminem")
            self.assertEqual(flagged[0]["track_count"],4)
            self.assertIn("NO_AUTOMATIC_RETAG",flagged[0]["action"])
            self.assertTrue(all(p.read_bytes()==b"untouched musician audio file" for p in files))

    def test_real_various_artists_mix_not_misclassified_as_solo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            va=root/"Various Artists"/"Bravo Hits 38"
            va.mkdir(parents=True)
            credits=["Eminem","Madonna","Rihanna","Nena"]
            files={}
            for i,artist in enumerate(credits):
                path=va/f"{i} Track.flac"
                path.write_bytes(b"test")
                files[path]={"album":"Bravo Hits 38","albumartist":"Various Artists",
                             "artist":artist}
            result=self.audit.scan_library([root],reader=lambda p:files[p])
            self.assertFalse(result["potentially_misfiled_artist_compilations"])

    def test_path_alias_fallback_without_album_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            media=root/"Unknown"/"ThemeAddict - WWE The Music Vol. 6"/"theme.flac"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"unknown tags")
            out=self.audit.scan_library([root],reader=lambda p:{})
            self.assertEqual(out["by_volume"]["6"]["audio_files"],1)
            self.assertEqual(out["by_volume"]["6"]["misplaced_candidates"],1)

    def test_symlink_file_never_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"outside.flac";target.write_bytes(b"test")
            link=root/"link.flac"
            try:link.symlink_to(target)
            except (OSError,NotImplementedError):self.skipTest("No symlinks available")
            out=self.audit.scan_library([root],reader=lambda p:{"album":"WWE The Music Vol. 8"})
            self.assertEqual(out["audio_files_scanned"],1)

    def test_bounded_and_invalid_roots_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"one.flac").write_bytes(b"synthetic")
            with self.assertRaises(ValueError):
                self.audit.scan_library([root],max_audio=0)
            with self.assertRaises(ValueError):
                self.audit.scan_library([root],max_audio=0,sample_limit=0)
            with self.assertRaises(ValueError):
                self.audit.scan_library([root/"missing"])

if __name__=="__main__":
    unittest.main()
