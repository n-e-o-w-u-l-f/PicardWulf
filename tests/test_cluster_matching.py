"""No-network album group search ranking/selection with 75% cutoff."""
import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('cluster_75_test')
pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+'.cluster_matching')
ad=importlib.import_module(pkg.__name__+'.universal_adapters')


def query(n):
    return {'title':'Track %02d'%n, 'artist':'Artist', 'album':'Album',
            'albumartist':'Artist','duration_ms':100000,'isrc':''}

def hit(n,source,album='Album',duration=100000,**extra):
    return ad.item(source,'Track %02d'%n,'Artist',album,duration,
                   albumartist='Artist',**extra)

def input_rows(source,cover=4,album='Album',duration=100000,**extra):
    rows=[]
    for n in range(1,5):
        rows.append({'candidates':[hit(n,source,album,duration,**extra)]
                     if n<=cover else []})
    return rows

class ClusterTests(unittest.TestCase):
    def setUp(self):self.queries=[query(n) for n in range(1,5)]

    def test_selected_cluster_files_are_bounded_deduplicated_and_safe(self):
        ui=importlib.import_module(pkg.__name__+'.cluster_ui')
        class File:
            def __init__(self,n):self.metadata={'title':str(n)}
        class Cluster:
            def __init__(self,files):self.files=files
        files=[File(1),File(2)]
        result=ui.selected_group_files([Cluster([files[0],files[1]]),
                                        Cluster([files[1]])])
        self.assertEqual(result,files)
        with self.assertRaises(Exception):
            ui.selected_group_files([Cluster([File(i) for i in range(201)])])
        self.assertEqual(files[0].metadata,{'title':'1'})

    def test_selected_deezer_release_preserved_in_followup_review(self):
        native=importlib.import_module(pkg.__name__+'.native_ui')
        chosen=hit(1,'deezer',provider_album_id='44')
        self.assertTrue(native.same_provider_track_selection(chosen,dict(chosen,score=.6)))
        self.assertFalse(native.same_provider_track_selection(
            chosen,hit(1,'deezer',provider_album_id='55')))
        self.assertFalse(native.same_provider_track_selection(
            chosen,hit(1,'musicbrainz',release_mbid='12345678-1234-4234-8234-123456789012')))
        self.assertFalse(native.same_provider_track_selection(
            chosen,hit(2,'deezer',provider_album_id='44')))

    def test_deezer_can_win_over_musicbrainz_without_provider_preference(self):
        rows=[]
        for n,q in enumerate(self.queries,1):
            rows.append({'candidates':[hit(n,'musicbrainz',duration=97000,
                release_mbid='12345678-1234-4234-8234-123456789012'),
                hit(n,'deezer',provider_album_id='444',duration=100000)]})
        result=m.find_similar_albums(self.queries,rows)
        self.assertGreaterEqual(len(result),2)
        self.assertEqual(result[0]['source'],'deezer')
        self.assertGreaterEqual(result[0]['confidence'],.75)
        self.assertEqual(result[0]['matched_tracks'],4)

    def test_musicbrainz_can_win_over_deezer(self):
        rows=[]
        for n,q in enumerate(self.queries,1):
            rows.append({'candidates':[hit(n,'musicbrainz',duration=100000,
                release_mbid='12345678-1234-4234-8234-123456789012'),
                hit(n,'deezer',duration=98000,provider_album_id='444')]})
        self.assertEqual(m.find_similar_albums(self.queries,rows)[0]['source'],'musicbrainz')

    def test_sparse_detail_metadata_for_one_release_id_still_groups_tracks(self):
        # A single official album ID is common even when only one adapter
        # result carries enriched release_date/barcode/totaltracks.
        rows=[]
        for n in range(1,5):
            extras={'provider_album_id':'422'}
            if n==1:
                extras.update(release_date='2004-11-12',barcode='123456789012',
                              totaltracks='12')
            rows.append({'candidates':[hit(n,'deezer',**extras)]})
        matches=m.find_similar_albums(self.queries,rows)
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]['matched_tracks'],4)
        self.assertEqual(matches[0]['release_id'],'422')

    def test_conflicting_official_details_for_same_id_abstains(self):
        rows=[]
        for n in range(1,5):
            rows.append({'candidates':[hit(n,'deezer',provider_album_id='422',
                release_date='2004' if n<=2 else '2014')]})
        self.assertEqual(m.find_similar_albums(self.queries,rows),[])

    def test_different_ids_and_releases_are_not_merged_when_metadata_sparse(self):
        rows=[]
        for n in range(1,5):
            rows.append({'candidates':[hit(n,'itunes',
                provider_album_id='100' if n<=2 else '200')]})
        self.assertEqual(m.find_similar_albums(self.queries,rows),[])

    def test_200_track_group_has_bounded_release_comparisons(self):
        from unittest.mock import patch
        queries=[query(n) for n in range(1,201)]
        rows=[{'candidates':[hit(n,'deezer',provider_album_id='same-id',
              release_date='2004' if n==1 else '')]}
              for n in range(1,201)]
        with patch.object(m,'edition_conflicts',wraps=m.edition_conflicts) as checks:
            found=m.find_similar_albums(queries,rows)
        self.assertEqual(found[0]['matched_tracks'],200)
        self.assertLessEqual(checks.call_count,650,
                             '200-track UI must not compare every track with every other')

    def test_three_of_four_tracks_supporting_release_can_be_offered(self):
        rows=input_rows('soundcloud',cover=3,provider_album_id='888')
        result=m.find_similar_albums(self.queries,rows)
        self.assertEqual(result[0]['matched_tracks'],3)
        self.assertEqual(result[0]['coverage'],.75)
        self.assertGreaterEqual(result[0]['confidence'],.75)

    def test_two_of_four_tracks_never_count_as_album_match(self):
        rows=input_rows('deezer',cover=2,provider_album_id='888')
        self.assertEqual(m.find_similar_albums(self.queries,rows),[])

    def test_wrong_editions_and_other_album_rejected(self):
        rows=input_rows('deezer',album='Other Album',provider_album_id='888')
        self.assertEqual(m.find_similar_albums(self.queries,rows),[])

    def test_same_album_but_distinct_deezer_releases_not_merged(self):
        rows=[]
        for n in range(1,5):
            rows.append({'candidates':[hit(n,'deezer',provider_album_id=str(11 if n%2 else 22))]})
        self.assertEqual(m.find_similar_albums(self.queries,rows),[])

    def test_duplicate_hits_from_one_track_do_not_count_as_multiple(self):
        rows=[{'candidates':[hit(1,'deezer',provider_album_id='77'),
                            hit(1,'deezer',provider_album_id='77')]}]+[None]*3
        self.assertEqual(m.find_similar_albums(self.queries,rows),[])

    def test_threshold_applied_to_track_score_and_releases(self):
        rows=input_rows('itunes',duration=120000)
        self.assertTrue(all(r['confidence']>=.75 for r in m.find_similar_albums(self.queries,rows,threshold=.75)))
        self.assertEqual(m.find_similar_albums(self.queries,rows,threshold=.99),[])

    def test_disabled_unavailable_provider_creates_no_fake_match(self):
        rows=[{'status':{'soundcloud':'CREDENTIALS_REQUIRED'},'candidates':[]} for _ in self.queries]
        self.assertEqual(m.find_similar_albums(self.queries,rows),[])

    def test_reject_unbounded_album_group(self):
        self.assertEqual(m.find_similar_albums([query(1)]*201,[None]*201),[])

if __name__=='__main__':unittest.main()
