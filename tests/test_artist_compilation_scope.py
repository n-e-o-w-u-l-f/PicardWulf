"""No artist-compilation may become a VA sampler merely for a type flag.

Contract: *album-wide* identity keeps all discs under one release folder,
preserves original track filename, and abstains on conflicting catalog data.
"""
from pathlib import Path
import importlib
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]/"neowulf_picard_repair"
pkg=types.ModuleType("_pw_artist_releases")
pkg.__path__=[str(ROOT)]
sys.modules[pkg.__name__]=pkg
policy=importlib.import_module(pkg.__name__+".release_scope")
bmax=importlib.import_module(pkg.__name__+".bmax_naming")
preset=importlib.import_module(pkg.__name__+".preset3_corrections")
migrate=importlib.import_module(pkg.__name__+".preset3_migration")
VA="![-1.2-VARiOUS-ARTiSTz-]!"


class ReleaseWideCompilationTests(unittest.TestCase):
    def artist(self, album, credit, year, folder, **extra):
        md={"album":album,"albumartist":credit,"date":year,
            "_secondaryreleasetype":"compilation"}
        md.update(extra)
        for route in (bmax.classify_bmax,preset.route_preset3):
            with self.subTest(route=route.__name__,title=album):
                result=route(md)
                self.assertFalse(result.requires_review if hasattr(result,"requires_review")
                                 else result.review, result)
                observed=result.relative_folder if hasattr(result,"relative_folder") else result.folder
                self.assertEqual(observed,folder)
                self.assertNotIn(VA,observed)

    def test_die_sekte_compilations_remain_artist(self):
        self.artist("Ihr Nutten","Various Artists","2001","Die Sekte/2001 - Ihr Nutten")
        self.artist("Die Sekte","Verschiedene Interpreten","2009",
                    "Die Sekte/2009 - Die Sekte")
        self.artist("Einblick","Die Sekte","2001","Die Sekte/2001 - Einblick")
        self.artist("Sekten Hits","Alles ist die Sekte","2003",
                    "Die Sekte/2003 - Sekten Hits")
        self.artist("Aggro Ansage Nr. 3","Die Sekte","2003",
                    "Die Sekte/2003 - Aggro Ansage Nr. 3")

    def test_aggro_ansage_various_not_blindly_recredited(self):
        md={"album":"Aggro Ansage Nr. 1","date":"2002",
            "albumartist":"Various Artists",
            "_secondaryreleasetype":"compilation"}
        for route in (bmax.classify_bmax,preset.route_preset3):
            result=route(md)
            review=result.requires_review if hasattr(result,"requires_review") else result.review
            self.assertTrue(review,result)
        self.assertEqual(md["albumartist"],"Various Artists")

    def test_frank_zander_2022_compilation_all_tracks_one_album(self):
        for title in ("Meine coolsten Hits","Frank Zander - Meine Coolsten Hits",
                      "Meine coolsten Hits CD 1", "Meine coolsten Hits CD 2"):
            for performer in ("Frank Zander","Curry Sauce feat. She-Raw",
                              "Frank Schöbel & Frank Zander"):
                with self.subTest(title=title,performer=performer):
                    self.artist(title,"Various Artists","2022",
                                "Frank Zander/2022 - Meine coolsten Hits",
                                artist=performer,totaldiscs="2")

    def test_reject_wrong_frank_zander_year(self):
        out=bmax.classify_bmax({"album":"Meine coolsten Hits",
                               "albumartist":"Various Artists","date":"2010"})
        self.assertTrue(out.requires_review)
        self.assertEqual(out.relative_folder,"")

    def test_wwe_anthology_three_discs_remain_together(self):
        for album in ("WWE Anthology","WWE Anthology CD 1",
                      "WWE Anthology CD 2","WWE Anthology Disc 3"):
            md={"album":album,"albumartist":"Various Artists",
                "date":"2002","_secondaryreleasetype":"compilation"}
            for route in (bmax.classify_bmax,preset.route_preset3):
                result=route(md)
                actual=result.relative_folder if hasattr(result,"relative_folder") else result.folder
                self.assertEqual(actual,
                    VA+"/WWE Anthology/2002 - WWE Anthology")
        self.assertTrue(bmax.classify_bmax({"album":"WWE Anthology",
            "albumartist":"Various Artists","date":"2019"}).requires_review)

    def test_wwe_entrance_themes_cd_names_share_album_folder(self):
        for album in ("WWE Entrance Themes","WWE Entrance Themes CD 1",
                      "WWE Entrance Themes Disc 2","WWF Entrance Themes CD 3"):
            md={"album":album,"albumartist":"Various Artists","date":"2004"}
            for route in (bmax.classify_bmax,preset.route_preset3):
                result=route(md)
                actual=result.relative_folder if hasattr(result,"relative_folder") else result.folder
                self.assertEqual(actual,
                    VA+"/WWE Entrance Themes/2004 - WWE Entrance Themes")

    def test_wwe_the_music_original_volume_still_has_own_series_folder(self):
        result=bmax.classify_bmax({"album":"ThemeAddict: WWE The Music, Vol. 6",
                                   "albumartist":"Various Artists","date":"2004"})
        self.assertEqual(result.relative_folder,
            VA+"/WWE The Music/2004 - WWE The Music Volume 6")

    def test_track_artist_not_release_credit_and_cannot_create_false_collab(self):
        out=bmax.classify_bmax({"album":"A Normal Studio Compilation",
             "albumartist":"Frank Zander","artist":"Rapper featuring Frank Zander",
             "date":"2022","_secondaryreleasetype":"compilation"})
        self.assertEqual(out.relative_folder,
            "Frank Zander/2022 - A Normal Studio Compilation")

    def test_unknown_va_compilation_is_not_recredited_from_one_track(self):
        out=policy.release_artist_scope({
            "album":"Unknown Sampler","albumartist":"Various Artists",
            "artist":"Die Sekte"},"2003")
        self.assertIsNone(out)

    def test_wrapper_preserves_both_cd_names_and_original_file_leaf(self):
        original=(" [--1--MUSiKz------------]/"+VA+
                  "/2022 - Meine Coolsten Hits/01 - Intro.flac").strip()
        for disc in (1,2):
            with self.subTest(disc=disc):
                actual=bmax.picard_bmax_fullpath(
                    None,original,"Meine coolsten Hits",
                    "Various Artists","2022", discnumber=str(disc),
                    totaldiscs="2")
                self.assertEqual(actual,
                    "[--1--MUSiKz------------]/Frank Zander/"
                    f"2022 - Meine coolsten Hits/CD {disc:02d}/01 - Intro.flac")

    def test_wrapper_preserves_existing_cd_directory_without_double_nesting(self):
        old=VA+"/2022 - Meine coolsten Hits/CD 02/07 - Track.flac"
        actual=bmax.picard_bmax_fullpath(None,old,
            "Meine coolsten Hits","Various Artists",date="2022",
            discnumber="2",totaldiscs="2")
        self.assertEqual(actual,
            "Frank Zander/2022 - Meine coolsten Hits/CD 02/07 - Track.flac")

    def test_wrapper_requires_authoritative_totaldisc_for_new_subfolder(self):
        old=VA+"/2022 - Meine coolsten Hits/07 - Intro.flac"
        for d,n in (("2",""),("0","2"),("3","2"),("2","1"),("","2")):
            with self.subTest(d=d,n=n):
                actual=bmax.picard_bmax_fullpath(
                    None,old,"Meine coolsten Hits","Various Artists",
                    date="2022",discnumber=d,totaldiscs=n)
                self.assertEqual(actual,
                    "Frank Zander/2022 - Meine coolsten Hits/07 - Intro.flac")

    def test_full_preset3_wrapper_passes_disc_numbers_without_losing_script(self):
        scripts={"a":{"title":"Preset 3","script":"$noop(old)%artist%/%album%/01 - %title%"},
                 "b":{"title":"Other","script":"%title%"}}
        updated,receipt=migrate.prepare_active_preset3(scripts,"a")
        self.assertEqual(updated["b"],scripts["b"])
        self.assertEqual(scripts["a"]["script"],
                         "$noop(old)%artist%/%album%/01 - %title%")
        self.assertIn("%discnumber%,%totaldiscs%",updated["a"]["script"])
        self.assertTrue(updated["a"]["script"].endswith(
            "%discnumber%,%totaldiscs%)"))

if __name__=="__main__":
    unittest.main()
