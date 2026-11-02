"""BMAX Preset 3 artist-compilation and WWE-disc regression acceptance.

No media, live Picard.ini, running Picard app, or network access.
"""
import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]/"neowulf_picard_repair"
NAME="_pw_artist_compilation_20261102"
pkg=types.ModuleType(NAME)
pkg.__path__=[str(ROOT)]
sys.modules[NAME]=pkg
scope=importlib.import_module(NAME+".release_scope")
preset=importlib.import_module(NAME+".preset3_corrections")
bmax=importlib.import_module(NAME+".bmax_naming")

VA="![-1.2-VARiOUS-ARTiSTz-]!"


class ArtistCompilations(unittest.TestCase):
    def classify(self,album,albumartist="Various Artists",year="2022",**extra):
        record=dict(album=album,albumartist=albumartist,artist="A single guest",
                    originaldate=year,date=year,_secondaryreleasetype="compilation")
        record.update(extra)
        return preset.route_preset3(record)

    def test_frank_zander_two_disc_40_tracks_not_various_artists(self):
        album_names=("Meine coolsten Hits","Frank Zander - Meine coolsten Hits",
                     "Meine coolsten Hits CD 1","Meine coolsten Hits CD 2")
        for name in album_names:
            for guest in ("Curry Sauce","Frank Zander","Frank Schöbel",
                          "Fred Sonnenschein & seine Freunde"):
                with self.subTest(name=name,guest=guest):
                    result=self.classify(name,"Verschiedene Interpreten","2022",artist=guest,
                         discnumber="1",totaldiscs="2")
                    self.assertEqual(result.kind,"ARTIST")
                    self.assertFalse(result.review)
                    self.assertEqual(result.folder,"Frank Zander/2022 - Meine coolsten Hits")
        self.assertEqual(bmax.classify_bmax({
            "album":"Meine coolsten Hits","albumartist":"Various Artists",
            "discnumber":"2","totaldiscs":"2","date":"2022"}).relative_folder,
            "Frank Zander/2022 - Meine coolsten Hits")

    def test_frank_nonexistent_third_cd_must_stop_not_assemble(self):
        for title in ("Meine coolsten Hits CD 3","Meine coolsten Hits"):
            with self.subTest(title=title):
                data={"album":title,"albumartist":"Various Artists",
                      "date":"2022","discnumber":"3","totaldiscs":"3"}
                out=preset.route_preset3(data)
                self.assertTrue(out.review)
                self.assertFalse(out.folder)
                self.assertNotIn("VARiOUS",out.folder)

    def test_frank_conflicting_release_year_is_review_not_multirelease_merge(self):
        out=self.classify("Meine coolsten Hits","Various Artists","2019")
        self.assertTrue(out.review)
        self.assertEqual(out.folder,"")

    def test_frank_safely_separates_disc_one_and_disc_two(self):
        record={"album":"Meine coolsten Hits","albumartist":"Frank Zander",
                "originaldate":"2022","totaldiscs":"2","discnumber":"1"}
        scoped=scope.release_artist_scope(record,"2022")
        self.assertTrue(scoped.coherent_discs)
        self.assertEqual(scope.disc_subfolder(
            "oldfolder/01 - Track.flac","1","2",allowed=scoped.coherent_discs),
            "CD 01/01 - Track.flac")
        record["discnumber"]="2"
        second=scope.release_artist_scope(record,"2022")
        self.assertTrue(second.coherent_discs)
        self.assertEqual(scope.disc_subfolder(
            "oldfolder/01 - Track.flac","2","2",allowed=second.coherent_discs),
            "CD 02/01 - Track.flac")
        record.pop("discnumber")
        self.assertFalse(scope.release_artist_scope(record,"2022").coherent_discs)

    def test_die_sekte_real_group_and_compilation_keeps_group(self):
        for title,year in (("Ihr Nutten","2001"),("Die Sekte","2009"),
                           ("Alles ist die Sekte","2002")):
            with self.subTest(title=title):
                md={"album":title,"albumartist":"Die Sekte","date":year,
                    "_secondaryreleasetype":"compilation",
                    "artist":"Sido feat. B-Tight"}
                result=preset.route_preset3(md)
                self.assertEqual(result.kind,"ARTIST")
                self.assertFalse(result.review)
                self.assertEqual(result.folder,f"Die Sekte/{year} - {title}")

    def test_aggro_ansage_user_folder_without_mutating_official_artist_tags(self):
        releases=((1,"2002"),(2,"2003"),(3,"2003"),(4,"2004"),(5,"2005"))
        for number,year in releases:
            for credit in ("Various Artists","Verschiedene Interpreten"):
                with self.subTest(number=number,credit=credit):
                    md={"album":f"Aggro Ansage Nr. {number}",
                        "albumartist":credit,"date":year,"artist":"Sido",
                        "_secondaryreleasetype":"compilation"}
                    before=dict(md)
                    result=preset.route_preset3(md)
                    self.assertEqual(result.kind,"ARTIST")
                    self.assertEqual(result.folder,
                        f"Die Sekte/{year} - Aggro Ansage Nr. {number}")
                    self.assertEqual(md,before)
                    self.assertEqual(bmax.classify_bmax(md).relative_folder,result.folder)
                    self.assertEqual(scope.release_artist_scope(md,year).reason,
                        "explicit_user_local_archive_override_not_artist_retag")

    def test_aggro_censored_reissue_kept_separate(self):
        out=self.classify("Aggro Ansage Nr. 3x","Verschiedene Interpreten","2006")
        self.assertEqual(out.kind,"ARTIST")
        self.assertEqual(out.folder,"Die Sekte/2006 - Aggro Ansage Nr. 3x")

    def test_aggro_impossible_year_and_unverified_family_refused(self):
        out=self.classify("Aggro Ansage Nr. 3","Various Artists","2014")
        self.assertTrue(out.review)
        self.assertFalse(out.folder)
        out=preset.route_preset3({"album":"Aggro Ansage","albumartist":"Various Artists"})
        self.assertTrue(out.review)

    def test_track_artist_alone_must_not_reclassify_other_va_sampler(self):
        out=self.classify("Bravo Hits 2022","Various Artists","2022",artist="Die Sekte")
        self.assertNotEqual(out.folder,"Die Sekte/2022 - Bravo Hits 2022")

    def test_generic_solo_compilation_not_forced_various(self):
        for artist,title,year in (("Eminem","Curtain Call 2","2022"),
                                  ("Nena","Greatest Hits","2011"),
                                  ("Dr. Dre","Dr. Dre & Friends","2003")):
            with self.subTest(artist=artist):
                out=self.classify(title,artist,year)
                self.assertEqual(out.kind,"ARTIST")
                self.assertTrue(out.folder.startswith(artist+"/"))


class WweAlbums(unittest.TestCase):
    def test_wwe_anthology_all_three_discs_stay_one_release(self):
        for number in (1,2,3):
            md={"album":"WWE Anthology","albumartist":"Various Artists",
                "date":"2002","discnumber":str(number),"totaldiscs":"3"}
            result=preset.route_preset3(md)
            self.assertEqual(result.folder,VA+"/WWE Anthology/2002 - WWE Anthology")
            s=scope.release_artist_scope(md,"2002")
            self.assertTrue(s.coherent_discs)
            self.assertEqual(scope.disc_subfolder(
                "other/01 - Intro.flac",str(number),"3",allowed=True),
                f"CD {number:02d}/01 - Intro.flac")

    def test_entrance_themes_two_discs_share_album_and_preserve_cd_path(self):
        for number in (1,2):
            md={"album":f"WWE Entrance Themes CD {number}",
                "albumartist":"Verschiedene Interpreten",
                "date":"2004","discnumber":str(number),"totaldiscs":"2"}
            result=preset.route_preset3(md)
            self.assertEqual(result.folder,
                VA+"/WWE Entrance Themes/2004 - WWE Entrance Themes")
            self.assertEqual(scope.disc_subfolder(
                "old/01 - Theme.flac",str(number),"2",allowed=True),
                f"CD {number:02d}/01 - Theme.flac")

    def test_wwe_music_volume_separate_from_anthology_and_entrance(self):
        album=preset.route_preset3({"album":"Voices: WWE The Music Vol. 9",
            "albumartist":"Various Artists","date":"2009"})
        self.assertEqual(album.folder,
            VA+"/WWE The Music/2009 - WWE The Music Volume 9")
        self.assertNotIn("Anthology",album.folder)
        self.assertNotIn("Entrance Themes",album.folder)


class PresetWrapper(unittest.TestCase):
    def test_keeps_original_preset_filename_and_cd_disc_folder(self):
        for disc in (1,2):
            old=(f"[--1--MUSiKz------------]/{VA}/Mein Compilation CD {disc}/"
                 f"CD {disc:02d}/01 - Guest song.flac")
            result=preset.retarget_original(old,"Meine coolsten Hits",
                "Various Artists","2022","2022","Guest", "compilation")
            self.assertEqual(result,
                f"[--1--MUSiKz------------]/Frank Zander/2022 - Meine coolsten Hits/"
                f"CD {disc:02d}/01 - Guest song.flac")

    def test_unchanged_file_name_for_sekte_and_aggro(self):
        result=preset.retarget_original(
            f"[--1--MUSiKz------------]/{VA}/2003 - Aggro Ansage Nr. 3/"
            "04 - Sido.flac",
            "Aggro Ansage Nr. 3","Various Artists","2003","2003","Sido")
        self.assertEqual(result,
            "[--1--MUSiKz------------]/Die Sekte/2003 - Aggro Ansage Nr. 3/"
            "04 - Sido.flac")


if __name__ == "__main__":
    unittest.main()
