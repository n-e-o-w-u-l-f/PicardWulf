"""S3 adversarial release corpus; synthetic metadata, never personal media."""
import unittest
from test_auto_selection import agg, auto, Q, entry, DummyFile
import test_auto_selection as existing
import importlib
import json
from pathlib import Path

ranking = importlib.import_module('picardwulf_auto_test.auto_selection')

class ReleaseCorpus(unittest.TestCase):
    def test_ground_truth_corpus(self):
        corpus=json.loads((Path(__file__).parent/'fixtures/s3_release_corpus.json').read_text(encoding='utf8'))
        matrix={'safe_assigned':0,'safe_abstained':0,'unsafe_assigned':0,'unsafe_abstained':0}
        for case in corpus['cases']:
            with self.subTest(case=case['name']):
                result=agg.aggregate(case['query'],case['results'])
                assigned=result['auto']['state']=='ready'
                if assigned:
                    auto.proposal_for_auto(case['query'],result)
                    self.assertEqual(result['auto']['source'],case['expected_source'])
                    winner=result['auto']['candidate']
                    self.assertEqual(agg.norm(winner['album']),agg.norm(case['query']['album']))
                    self.assertNotIn(agg.norm(winner.get('albumartist')),ranking.EXTERNAL_PROVIDER_NAMES)
                matrix[('safe_' if case['safe'] else 'unsafe_')+('assigned' if assigned else 'abstained')]+=1
                self.assertEqual(assigned,case['safe'])
        print('S3 corpus '+json.dumps(matrix,sort_keys=True))
    def test_snapshot_normalization_is_idempotent(self):
        q=agg.clean_track({'artist':'Eminem','title':'Mockingbird','album':'Encore',
                          'date':'2004','releasecountry':'DE','releasecomment':'deluxe',
                          '~length':250000,'musicbrainz_recordingid':'recording'})
        self.assertEqual(agg.clean_track(q),q)

    def test_existing_release_mbid_requires_review_for_external_source(self):
        q=agg.clean_track({'artist':'Eminem','title':'Mockingbird','album':'Encore',
                          'musicbrainz_albumid':'9f497f21-c32e-42cb-bc3f-7022f43d1b4d',
                          '~length':250000})
        result=agg.aggregate(q,{'deezer':[entry('deezer')]})
        with self.assertRaises(auto.UnsafeCandidate):auto.proposal_for_auto(q,result)
    def test_edition_conflicts_abstain(self):
        for field, a, b in [('release_date','2004','2012'), ('discnumber','1','2'),
                             ('totaltracks','20','28'), ('country','DE','US'),
                             ('barcode','123','456'), ('edition','original','remaster')]:
            with self.subTest(field=field):
                c = {**entry('deezer'), field:b}
                result = agg.aggregate({**Q, field:a}, {'deezer':[c]})
                self.assertNotEqual(result['auto']['state'], 'ready')

    def test_live_remix_clean_remaster_never_hidden(self):
        for suffix in ['Live', 'Remix', 'Clean', 'Remastered', 'Instrumental', 'Acoustic']:
            with self.subTest(suffix=suffix):
                c = entry('deezer', title='Mockingbird ('+suffix+')')
                self.assertNotEqual(agg.aggregate(Q, {'deezer':[c]})['auto']['state'],'ready')

    def test_different_years_do_not_corroborate(self):
        a={**entry('deezer'),'release_date':'2004'}
        b={**entry('spotify'),'release_date':'2012'}
        result=agg.aggregate(Q,{'deezer':[a],'spotify':[b]})
        self.assertEqual(result['auto']['state'],'ambiguous')
        self.assertTrue(all(c['source_support']==1 for c in result['candidates']))

    def test_missing_album_cannot_assign_recording_to_edition(self):
        self.assertNotEqual(agg.aggregate({**Q,'album':''}, {'deezer':[entry('deezer')]})['auto']['state'],'ready')

    def test_full_alternatives_and_versioned_breakdown(self):
        result=agg.aggregate(Q, {'deezer':[entry('deezer') for _ in range(45)]})
        self.assertEqual(len(result['candidates']),45)
        self.assertEqual(result['auto']['ranking_state'],'SAFE_WINNER')
        self.assertIn('model',result['candidates'][0])
        self.assertIn('weights',result['candidates'][0])

    def test_cache_key_includes_edition(self):
        for key in ('discnumber','totaltracks','release_date','country','barcode','edition','albumartist'):
            self.assertNotEqual(agg.query_key(Q),agg.query_key({**Q,key:'different'}))

    def test_applied_winner_is_fixed(self):
        f=DummyFile()
        first=agg.aggregate(Q,{'deezer':[entry('deezer')]})
        second=agg.aggregate(Q,{'spotify':[entry('spotify')]})
        with existing.TestAutomaticWriting().with_fake_api():
            auto.apply_best_to_file(f,Q,first)
            before=dict(f.metadata)
            with self.assertRaises(auto.UnsafeCandidate):auto.apply_best_to_file(f,Q,second)
        self.assertEqual(f.metadata,before)

    def test_album_consensus_cannot_merge_greatest_hits(self):
        original={**entry('deezer'),'provider_album_id':'encore'}
        hits={**entry('deezer','Curtain Call 2'),'provider_album_id':'hits'}
        sibling={**original,'title':'Like Toy Soldiers','isrc':'OTHER'}
        result=agg.aggregate(Q,{'deezer':[original,hits]},album_evidence=[sibling])
        self.assertEqual(result['auto']['source'],'deezer')
        by={c['album']:c for c in result['candidates']}
        self.assertEqual(by['Encore']['album_support'],1)
        self.assertEqual(by['Curtain Call 2']['album_support'],0)

    def test_verified_siblings_resolve_same_source_edition_tie(self):
        a={**entry('deezer'),'provider_album_id':'encore-original'}
        b={**a,'provider_album_id':'encore-other'}
        self.assertEqual(agg.aggregate(Q,{'deezer':[a,b]})['auto']['state'],'ambiguous')
        siblings=[{**a,'title':title,'isrc':title} for title in ('Like Toy Soldiers','Yellow Brick Road')]
        result=agg.aggregate(Q,{'deezer':[a,b]},album_evidence=siblings)
        self.assertEqual(result['auto']['state'],'ready')
        self.assertEqual(result['auto']['candidate']['provider_album_id'],'encore-original')

    def test_missing_edition_evidence_is_incomplete(self):
        result=agg.aggregate({**Q,'discnumber':'2'}, {'deezer':[entry('deezer')]})
        self.assertEqual(result['auto']['ranking_state'],'INCOMPLETE')

    def test_va_cluster_uses_album_credit_and_distinct_recordings(self):
        q={**Q,'albumartist':'Various Artists','album':'Compilation'}
        other={**q,'artist':'Other Artist','title':'Other Song'}
        self.assertEqual(ranking.consensus_cache_key(q),ranking.consensus_cache_key(other))
        a={**entry('deezer','Compilation'),'albumartist':'Various Artists','provider_album_id':'va'}
        b={**a,'provider_album_id':'other-va'}
        siblings=[{**a,'artist':'Other Artist','title':title,'isrc':title} for title in ('Other Song','Third Song')]
        result=agg.aggregate(q,{'deezer':[a,b]},album_evidence=siblings)
        self.assertEqual(result['auto']['state'],'ready')
        self.assertTrue(result['auto']['album_consensus_resolved'])
        duplicates=[{**s,'isrc':a['isrc']} for s in siblings]
        self.assertEqual(agg.aggregate(q,{'deezer':[a,b]},album_evidence=duplicates)['auto']['state'],'ambiguous')

    def test_missing_album_credit_cannot_auto_choose_va_edition(self):
        q={**Q,'albumartist':''}
        candidate={**entry('itunes'),'albumartist':'Various Artists'}
        self.assertNotEqual(agg.aggregate(q,{'itunes':[candidate]})['auto']['state'],'ready')

if __name__=='__main__':unittest.main()
