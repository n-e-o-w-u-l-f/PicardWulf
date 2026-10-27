"""Folder policy: releases, not track credits; metadata only, never writes."""
import importlib
import pathlib
import sys
import types
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
NAME="picardwulf_four_way_tests"
pkg=types.ModuleType(NAME)
pkg.__path__=[str(ROOT/"neowulf_picard_repair")]
sys.modules[NAME]=pkg
routing=importlib.import_module(NAME+".album_routing")
live=importlib.import_module(NAME+".liveset_sources")


class AlbumRoutingTests(unittest.TestCase):
    def test_samplers_collections_and_volume_without_repeating_suffix(self):
        for title,collection,year in (
            ("Bravo Hits Vol. 38","Bravo Hits","2002"),
            ("Masters of Hardcore Volume 31","Masters of Hardcore","2011"),
            ("Now That's What I Call Music Vol 90","Now That's What I Call Music","2015"),
        ):
            with self.subTest(title=title):
                result=routing.route_album({"album":title,
                    "albumartist":"Various Artists","date":year,
                    "_secondaryreleasetype":"compilation"})
                self.assertEqual(result.kind,"SAMPLER")
                self.assertEqual(result.folder,
                    f"Various Artists/{collection}/{year} - {collection} Vol. "+
                    title.rsplit(" ",1)[-1].lstrip("0"))
                self.assertFalse(result.review)

    def test_explicit_sampler_collection_and_volume(self):
        r=routing.route_album({"album":"Summer Compilation",
            "albumartist":"Various Artists", "date":"2021",
            "sampler_collection":"Beach Series","sampler_volume":"3"})
        self.assertEqual(r.folder,
            "Various Artists/Beach Series/2021 - Summer Compilation Vol. 3")

    def test_ambiguous_va_without_collection_remains_review(self):
        out=routing.route_album({"album":"90s Party","albumartist":"Various Artists",
                                 "date":"1999","_secondaryreleasetype":"compilation"})
        self.assertEqual(out.kind,"REVIEW")
        self.assertEqual(out.folder,"")

    def test_wwe_original_release_year_without_date_metadata(self):
        result=routing.route_album({"album":"Voices: WWE The Music Vol. 9",
                                    "albumartist":"Various Artists"})
        self.assertEqual(result.folder,
            "Various Artists/WWE The Music/2009 - WWE The Music Volume 9")

    def test_three_artists_have_last_ampersand_and_credits_order(self):
        result=routing.route_album({"album":"Joint Project","date":"2024",
            "albumartist":"Alpha, Beta & Gamma",
            "albumartists":["Alpha","Beta","Gamma"]})
        self.assertEqual(result.kind,"COLLABORATION")
        self.assertEqual(result.folder,
            "Collaborations/Alpha, Beta & Gamma/2024 - Joint Project")

    def test_solo_named_ampersand_group_is_not_collaboration(self):
        for name in ("Simon & Garfunkel","Earth, Wind & Fire","Hall & Oates"):
            result=routing.route_album({"album":"Best of", "date":"2000",
                                       "albumartist":name,
                                       "_secondaryreleasetype":"compilation"})
            self.assertEqual(result.kind,"ARTIST")
            self.assertEqual(result.folder,f"{name}/2000 - Best of")

    def test_track_feature_is_not_album_collaboration(self):
        out=routing.route_album({"album":"Curtain Call 2","date":"2022",
            "albumartist":"Eminem","artist":"Eminem feat. Snoop Dogg",
            "artists":["Eminem","Snoop Dogg"],
            "_secondaryreleasetype":"compilation"})
        self.assertEqual(out.folder,"Eminem/2022 - Curtain Call 2")

    def test_live_dj_set_and_normal_live_album_separated(self):
        live_data={"album":"Boiler Room Berlin DJ Set","date":"2025-07-19",
                   "albumartist":"DJ Example",
                   "_secondaryreleasetype":["live","dj-mix"]}
        out=routing.route_album(live_data)
        self.assertEqual(out.kind,"LIVESET")
        self.assertEqual(out.folder,
            "LiveSets/DJ Example/2025-07-19 - Boiler Room Berlin DJ Set")
        normal=routing.route_album({"album":"Live at Wembley",
            "date":"2000","albumartist":"Artist",
            "_secondaryreleasetype":"live"})
        self.assertEqual(normal.folder,"Artist/2000 - Live at Wembley")
        self.assertEqual(normal.kind,"ARTIST")

    def test_dj_mix_alone_not_all_live_recordings(self):
        result=routing.route_album({"album":"Studio DJ Mix", "date":"2020",
            "albumartist":"DJ", "_secondaryreleasetype":"dj-mix"})
        self.assertEqual(result.kind,"ARTIST")
        explicit=routing.route_album({"album":"Sunday Residency","event_date":"2020-01-02",
            "date":"2021","albumartist":"DJ", "set_type":"radio-set"})
        self.assertEqual(explicit.folder,"LiveSets/DJ/2020-01-02 - Sunday Residency")

    def test_missing_year_and_collab_ambiguity_are_review_only(self):
        self.assertTrue(routing.route_album({"album":"Untitled",
            "albumartist":"Artist"}).review)
        self.assertTrue(routing.route_album({"album":"A","date":"2000",
            "albumartist":"Alpha & Beta",
            "albumartists":["Alpha","Alpha"]}).review)

    def test_unsafe_windows_components_stay_under_library(self):
        for artist in ("../traversal","CON","LPT1", "AUX"):
            with self.subTest(artist=artist):
                route=routing.route_album({"album":"Title","date":"2020",
                                           "albumartist":artist})
                self.assertTrue(route.review or (".." not in route.folder and
                    "/" not in route.folder.split("/")[0]))
        safe=routing.route_album({"album":"Title: Disc/1?","date":"2020",
                                   "albumartist":"Alpha"})
        self.assertEqual(safe.folder,"Alpha/2020 - Title_ Disc_1_")

    def test_native_picard_script_returns_blank_on_review(self):
        self.assertEqual(routing.picard_album_folder(None,"Album","",date="2020"),"")
        self.assertEqual(routing.picard_album_folder(
            None,"Project","Alpha, Beta & Gamma","2023","","","Alpha;Beta;Gamma"),
            "Collaborations/Alpha, Beta & Gamma/2023 - Project")


class MixcloudLookupTests(unittest.TestCase):
    def test_exact_public_match_returns_suggestion_and_provenance(self):
        def fetch(query):
            self.assertEqual(query['type'],'cloudcast')
            self.assertEqual(query['limit'],'5')
            return {"data":[{"name":"Boiler Room Berlin Live Set",
                             "user":{"name":"DJ Example"},
                             "created_time":"2025-08-18T10:00:00Z",
                             "url":"https://www.mixcloud.com/example/boiler-room/",
                             "audio_length":3600}]}
        result=live.lookup_mixcloud("DJ Example","Boiler Room Berlin Live Set",
                                    fetch=fetch)
        self.assertEqual(result["status"],"SUGGESTION_ONLY")
        one=result["matches"][0]
        self.assertEqual(one["source"],"mixcloud")
        self.assertTrue(one["requires_confirmation"])
        self.assertEqual(one["duration_seconds"],3600)
        self.assertEqual(result["automatic_tagging"],False)

    def test_wrong_artist_or_show_abstains_not_auto_tag(self):
        for fake_artist,fake_title in [
            ("Someone Else","Boiler Room Berlin Live Set"),
            ("DJ Example","Completely Different Show")]:
            with self.subTest(artist=fake_artist,title=fake_title):
                found=live.lookup_mixcloud("DJ Example",
                    "Boiler Room Berlin Live Set",fetch=lambda _:{"data":[{
                        "name":fake_title,"user":{"name":fake_artist},
                        "url":"https://www.mixcloud.com/dj/show/"}]})
                self.assertEqual(found["status"],"ABSTAIN")

    def test_ambiguous_two_almost_identical_shows_require_review(self):
        show={"name":"My DJ Live Set","user":{"name":"DJ X"},
              "created_time":"2025-01-01",
              "url":"https://www.mixcloud.com/dj/show1/"}
        alt=dict(show,url="https://www.mixcloud.com/dj/show2/")
        result=live.lookup_mixcloud("DJ X","My DJ Live Set",
                                    fetch=lambda _:{"data":[show,alt]})
        self.assertEqual(result["status"],"REVIEW")
        self.assertEqual(result["reason"],"multiple_matching_shows")

    def test_invalid_response_or_url_not_trusted(self):
        self.assertEqual(live.lookup_mixcloud("DJ","Set",fetch=lambda _:{"data":[
            {"name":"Set","user":{"name":"DJ"},
             "url":"https://evil.example.com/show"}]} )["status"],"ABSTAIN")
        with self.assertRaises(ValueError):
            live.lookup_mixcloud("DJ","Set",fetch=lambda _:{"error":"unauthorized"})


if __name__=="__main__":
    unittest.main()
