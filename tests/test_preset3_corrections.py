"""Regression catalogue for BMAX's exact user-specified Preset 3 folder errors."""
import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]/"neowulf_picard_repair"
MODULE="preset3_fix_test"
package=types.ModuleType(MODULE)
package.__path__=[str(ROOT)]
sys.modules[MODULE]=package
mod=importlib.import_module(MODULE+".preset3_corrections")

class UserNamedCorrections(unittest.TestCase):
    def route(self,album,albumartist,year,**kwargs):
        return mod.route_preset3(dict(album=album,albumartist=albumartist,date=year,**kwargs))

    def test_w_and_w_exact_credit_is_collaborative_not_artist(self):
        credit="W&W X AXMO X André Schnura feat. Lucenzo & Don Omar"
        r=self.route("Festival Anthem",credit,"2026")
        self.assertEqual(r.kind,"COLLABORATION")
        self.assertEqual(r.folder,
            "![-1.1-COLLABORATiVEz--]!/"+credit+"/2026 - Festival Anthem")

    def test_rolf_is_album_artist_not_so_klingt_weihnachten(self):
        r=self.route("So klingt Weihnachten!","So klingt Weihnachten!","2002",
                     artist="Rolf Zuckowski")
        self.assertEqual(r.kind,"ARTIST")
        self.assertEqual(r.folder,
                         "Rolf Zuckowski/2002 - So klingt Weihnachten!")

    def test_rolf_jahresuhr_bad_va_title_is_repaired(self):
        for title in ("Rolfs Liederkalender _ Die Jahresuhr",
                      "Rolfs Liederkalender / Die Jahresuhr",
                      "Rolfs Liederkalender: Die Jahresuhr"):
            with self.subTest(title=title):
                out=self.route(title,"Verschiedene Interpreten","2001")
                self.assertEqual(out.kind,"ARTIST")
                self.assertEqual(out.folder,"Rolf Zuckowski/2001 - Die Jahresuhr")

    def test_dr_dre_friends_is_dr_dre(self):
        out=self.route("Dr. Dre & Friends","Various Artists","2003")
        self.assertEqual(out.folder,"Dr. Dre/2003 - Dr. Dre & Friends")
        self.assertEqual(out.kind,"ARTIST")

    def test_aladdin_german_ost_is_soundtrack(self):
        out=self.route("Aladdin (Deutscher Original Film-Soundtrack)",
                       "Verschiedene Interpreten","1993")
        self.assertEqual(out.kind,"SOUNDTRACK")
        self.assertEqual(out.folder,
          "[--3--SOUNTRACKz--]/1993 - Aladdin (Deutscher Original Film-Soundtrack)")

    def test_nordic_rave_1_2_3_share_series(self):
        for title,expect in (
            ("Nordic Rave","1996 - Nordic Rave"),
            ("Nordic Rave 2","1996 - Nordic Rave 2"),
            ("Nordic Rave 3","1996 - Nordic Rave 3"),
        ):
            with self.subTest(title=title):
                r=self.route(title,"Verschiedene Interpreten","1996")
                self.assertEqual(r.folder,
                    "![-1.2-VARiOUS-ARTiSTz-]!/Nordic Rave/"+expect)

    def test_enzyme_injection_part_two_series(self):
        r=self.route("Enzyme Injection Part 2","Verschiedene Interpreten","2003")
        self.assertEqual(r.kind,"SAMPLER")
        self.assertEqual(r.folder,
          "![-1.2-VARiOUS-ARTiSTz-]!/Enzyme Injection/2003 - Enzyme Injection Part 2")

    def test_known_misc_samplers_as_german_va(self):
        cases=[("... Like A Raging Bull","2000"),
               ("A² Records Unleashed","2011"),
               ("Dawn Of Paranoia","2012"),
               ("Social Teknology 12","2013"),
               ("Necrochasm","2015")]
        for title,year in cases:
            with self.subTest(title=title):
                r=self.route(title,"Verschiedene Interpreten",year)
                self.assertEqual(r.folder,
                    f"![-1.2-VARiOUS-ARTiSTz-]!/{year} - {title}")
                self.assertEqual(r.kind,"SAMPLER")

    def test_generic_german_va_uses_va_category_not_solo(self):
        r=self.route("Other Album","Verschiedene Interpreten","2010")
        self.assertEqual(r.folder,
            "![-1.2-VARiOUS-ARTiSTz-]!/2010 - Other Album")

    def test_existing_wwe_uses_user_va_prefix(self):
        r=self.route("Voices: WWE The Music Vol. 9","Various Artists","2009")
        self.assertEqual(r.folder,
            "![-1.2-VARiOUS-ARTiSTz-]!/WWE The Music/2009 - WWE The Music Volume 9")

    def test_generic_collaboration_uses_user_prefix(self):
        r=self.route("Joint Record","Alpha, Beta & Gamma","2024",
                     albumartists=["Alpha","Beta","Gamma"])
        self.assertEqual(r.folder,
            "![-1.1-COLLABORATiVEz--]!/Alpha, Beta & Gamma/2024 - Joint Record")

    def test_non_matching_va_and_fake_artist_dont_get_special_override(self):
        out=self.route("Dr. Dre Greatest Hits","Various Artists","2003")
        self.assertTrue(out.review)
        out=self.route("So klingt Weihnachten!","So klingt Weihnachten!","2002",
                       artist="Another Artist")
        self.assertEqual(out.kind,"ARTIST")
        self.assertEqual(out.folder,"So klingt Weihnachten!/2002 - So klingt Weihnachten!")
        out=self.route("Aladdin","Various Artists","1993")
        self.assertTrue(out.review)

    def test_no_year_refuses_guessing_or_mutating_other_metadata(self):
        data={"album":"Nordic Rave 2","albumartist":"Verschiedene Interpreten"}
        snapshot=dict(data)
        self.assertIsNone(mod.classify(data,""))
        out=mod.route_preset3(data)
        self.assertTrue(out.review)
        self.assertEqual(data,snapshot)

    def test_script_function_is_an_album_folder_only(self):
        p=mod.picard_preset3_folder(
            None, "Enzyme Injection Part 2","Verschiedene Interpreten",
            date="2003")
        self.assertEqual(p,
          "![-1.2-VARiOUS-ARTiSTz-]!/Enzyme Injection/2003 - Enzyme Injection Part 2")

if __name__=="__main__":
    unittest.main()
