"""Real BMAX routing mistakes must never regress, even without PyQt6."""
import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType("_picardwulf_bmax_test")
pkg.__path__=[str(ROOT/"neowulf_picard_repair")]
sys.modules[pkg.__name__]=pkg
router=importlib.import_module(pkg.__name__+".bmax_naming")
migrate=importlib.import_module(pkg.__name__+".preset3_migration")

VA="![-1.2-VARiOUS-ARTiSTz-]!"
CO="![-1.1-COLLABORATiVEz--]!"
ST="[--3--SOUNTRACKz--]"


class RealBmaxCorrections(unittest.TestCase):
    def check(self,md,kind,path):
        result=router.classify_bmax(md)
        self.assertEqual(result.category,kind,result)
        self.assertEqual(result.relative_folder,path,result)
        self.assertFalse(result.requires_review,result)

    def test_w_and_w_axmo_andre_schnura_featured_credit_is_collaboration(self):
        self.check({"album":"Danza Kuduro","date":"2024-10-25",
          "albumartist":"W&W X AXMO X André Schnura feat. Lucenzo & Don Omar"},
          "COLLABORATION",
          CO+"/W&W X AXMO X André Schnura feat. Lucenzo & Don Omar/2024 - Danza Kuduro")

    def test_collaboration_with_x_labels_detected_before_solo_route(self):
        self.check({"album":"Joint Track","albumartist":"Alpha x Beta x Gamma","date":"2022"},
            "COLLABORATION",CO+"/Alpha x Beta x Gamma/2022 - Joint Track")

    def test_simon_garfunkel_remains_single_band(self):
        self.check({"album":"Greatest Hits","albumartist":"Simon & Garfunkel",
                    "date":"2001","_secondaryreleasetype":"compilation"},
                   "ARTIST","Simon & Garfunkel/2001 - Greatest Hits")

    def test_rolfs_liederkalender_name_and_user_year(self):
        for title in ("Rolfs Liederkalender _ Die Jahresuhr",
                      "Rolfs Liederkalender / Die Jahresuhr",
                      "Die Jahresuhr"):
            with self.subTest(title=title):
                self.check({"album":title,"albumartist":"Verschiedene Interpreten",
                            "originaldate":"1992-01-01","date":"2001"},
                    "ARTIST","Rolf Zuckowski/2001 - Die Jahresuhr")

    def test_so_klingt_weihnachten_is_not_a_new_artist(self):
        self.check({"album":"So klingt Weihnachten!","date":"2005",
                    "albumartist":"So klingt Weihnachten!"},
                   "ARTIST","Rolf Zuckowski/2005 - So klingt Weihnachten!")
        self.assertTrue(router.classify_bmax(
            {"album":"So klingt Weihnachten!","albumartist":"So klingt Weihnachten!"}
        ).requires_review)

    def test_dr_dre_friends_is_dr_dre_not_va_and_not_collab(self):
        self.check({"album":"Dr. Dre & Friends","albumartist":"Verschiedene Interpreten",
                    "date":"2003","_secondaryreleasetype":"compilation"},
                   "ARTIST","Dr. Dre/2003 - Dr. Dre & Friends")

    def test_disney_aladdin_soundtrack_is_separate_user_category(self):
        self.check({"album":"Aladdin (Deutscher Original Film-Soundtrack)",
                    "albumartist":"Verschiedene Interpreten","date":"1992"},
                   "SOUNDTRACK",
                   ST+"/1993 - Aladdin (Deutscher Original Film-Soundtrack)")

    def test_generic_original_soundtrack_type(self):
        self.check({"album":"Original Movie Score","albumartist":"Various Artists",
                    "date":"2016","_primaryreleasetype":"soundtrack"},
                   "SOUNDTRACK",ST+"/2016 - Original Movie Score")

    def test_nordic_rave_unifies_unnumbered_and_2_and_3(self):
        for title,expected in (("Nordic Rave","Nordic Rave"),
                               ("Nordic Rave 2","Nordic Rave 2"),
                               ("Nordic Rave 3","Nordic Rave 3")):
            with self.subTest(title=title):
                for credit in ("Verschiedene Interpreten","Various Artists"):
                    self.check({"album":title,"albumartist":credit,"date":"1999"},
                        "SAMPLER",VA+"/Nordic Rave/1996 - "+expected)

    def test_enzyme_injection_part_two_and_part_three_series(self):
        self.check({"album":"Enzyme Injection Part 2",
                    "albumartist":"Verschiedene Interpreten","date":"2005"},
                   "SAMPLER",
                   VA+"/Enzyme Injection/2003 - Enzyme Injection Part 2")
        self.check({"album":"Enzyme Injection : Part 3",
                    "albumartist":"Various Artists","date":"2004"},
                   "SAMPLER",
                   VA+"/Enzyme Injection/2004 - Enzyme Injection Part 3")

    def test_various_artists_german_never_folder_v_ext(self):
        for title,year in (
            ("... Like A Raging Bull","2000"),
            ("A² Records Unleashed","2011"),
            ("Dawn Of Paranoia","2012"),
            ("Social Teknology 12","2013"),
            ("Necrochasm","2015")):
            with self.subTest(title=title):
                self.check({"album":title,"albumartist":"Verschiedene Interpreten",
                            "date":year}, "SAMPLER",
                            VA+"/"+year+" - "+title)

    def test_real_various_unknown_collection_goes_under_va_root_not_artist(self):
        self.check({"album":"A Compilation Without Volume",
                    "albumartist":"Verschiedene Interpreten","date":"2020"},
                  "SAMPLER",VA+"/2020 - A Compilation Without Volume")

    def test_verified_bravo_hits_and_wwe_still_use_series(self):
        self.check({"album":"Bravo Hits Vol. 38","albumartist":"Verschiedene Interpreten",
                    "date":"2002"}, "SAMPLER",
                   VA+"/Bravo Hits/2002 - Bravo Hits Vol. 38")
        self.check({"album":"Voices: WWE The Music, Vol. 9",
                    "albumartist":"Various Artists"},
                   "SAMPLER",VA+"/WWE The Music/2009 - WWE The Music Volume 9")

    def test_curtain_call_solo_compilation_not_va(self):
        self.check({"album":"Curtain Call 2","albumartist":"Eminem",
                    "date":"2022","_secondaryreleasetype":"compilation"},
                   "ARTIST","Eminem/2022 - Curtain Call 2")

    def test_livesets_policy_survives_real_custom_layout(self):
        self.check({"album":"Boiler Room Berlin DJ Set","albumartist":"DJ Example",
                    "date":"2025-10-11","_secondaryreleasetype":["live","dj-mix"]},
                   "LIVESET","LiveSets/DJ Example/2025-10-11 - Boiler Room Berlin DJ Set")

    def test_unknown_missing_year_refuses_route(self):
        out=router.classify_bmax({"album":"A random album","albumartist":"DJ X"})
        self.assertTrue(out.requires_review)
        self.assertEqual(out.relative_folder,"")

    def test_safe_legacy_leaf_preserved_and_only_album_directory_replaced(self):
        original=("Verschiedene Interpreten/2003 - Dr. Dre & Friends/"
                  "CD 01 - 01 - Intro.flac")
        result=router.picard_bmax_fullpath(None,original,
            "Dr. Dre & Friends","Verschiedene Interpreten","2003")
        self.assertEqual(result,"Dr. Dre/2003 - Dr. Dre & Friends/CD 01 - 01 - Intro.flac")

    def test_unknown_category_does_not_mutate_legacy_result(self):
        old="Artist/Untitled/01 - Track.flac"
        result=router.picard_bmax_fullpath(None,old,
                "Unverified Release","Unverified Artist")
        self.assertEqual(result,old)

    def test_refuses_legacy_traversal_and_empty_filename(self):
        for original in ("../../evil.flac","/absolute/path","folder/"):
            with self.subTest(original=original):
                self.assertEqual(router.picard_bmax_fullpath(None,original,
                    "Dr. Dre & Friends","Various Artists","2003"),"")


class ActivePreset3Migration(unittest.TestCase):
    def setup_scripts(self):
        return {
            "preset3": {"title":"Preset 3","script":
                "$noop(NEOWULF_UNMATCHED_FALLBACK)$if(%albumartist%,"
                "$replace(%albumartist%,:, -)/%album%/track,empty)"},
            "other":{"title":"Private","script":"%artist%/%album%"}
        }

    def test_wraps_only_active_script_preserves_every_original_character(self):
        before=self.setup_scripts()
        after,receipt=migrate.prepare_active_preset3(before,"preset3")
        self.assertEqual(before["preset3"]["script"],
                         self.setup_scripts()["preset3"]["script"])
        wrapped=after["preset3"]["script"]
        self.assertTrue(wrapped.startswith(migrate.PREFIX))
        self.assertEqual(wrapped[len(migrate.PREFIX):-len(migrate.SUFFIX)],
                         before["preset3"]["script"])
        self.assertEqual(after["other"],before["other"])
        self.assertEqual(receipt["active_id"],"preset3")
        self.assertEqual(len(receipt["original_sha256"]),64)

    def test_reject_unselected_preset_or_wrong_name(self):
        with self.assertRaises(migrate.PresetMigrationRefused):
            migrate.prepare_active_preset3(self.setup_scripts(),"other")

    def test_repeated_application_is_refused(self):
        after,_=migrate.prepare_active_preset3(self.setup_scripts(),"preset3")
        with self.assertRaises(migrate.PresetMigrationRefused):
            migrate.prepare_active_preset3(after,"preset3")

    def test_unknown_active_id_refuses_without_edits(self):
        before=self.setup_scripts()
        with self.assertRaises(migrate.PresetMigrationRefused):
            migrate.prepare_active_preset3(before,"bogus")
        self.assertEqual(before,self.setup_scripts())


if __name__=="__main__":
    unittest.main()
