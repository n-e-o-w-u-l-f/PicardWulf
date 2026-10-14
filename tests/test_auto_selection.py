"""Cross-source release ranking and safe auto-apply regression coverage."""
from pathlib import Path
import importlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
pk=types.ModuleType('picardwulf_auto_test')
pk.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules['picardwulf_auto_test']=pk
agg=importlib.import_module('picardwulf_auto_test.universal_engine')
ad=importlib.import_module('picardwulf_auto_test.universal_adapters')
auto=importlib.import_module('picardwulf_auto_test.auto_apply')
nw=importlib.import_module('picardwulf_auto_test.native_workflow')

Q={'title':'Mockingbird','artist':'Eminem','album':'Encore',
   'albumartist':'Eminem','isrc':'USIR10400624','duration_ms':250000,
   'recording_mbid':''}

def entry(source,album='Encore',artist='Eminem',title='Mockingbird',ms=250000):
    return ad.item(source,title,artist,album,ms,'USIR10400624',
                   albumartist='Eminem' if source in ('musicbrainz','itunes') else '')

class TestSourceNeutralRanking(unittest.TestCase):
    def test_deezer_beats_musicbrainz_if_album_is_more_accurate(self):
        result=agg.aggregate(Q,{'musicbrainz':[entry('musicbrainz','Curtain Call 2')],
                                  'deezer':[entry('deezer')]})
        self.assertEqual(result['auto']['state'],'ready')
        self.assertEqual(result['auto']['source'],'deezer')
        self.assertEqual(result['candidates'][0]['source'],'deezer')

    def test_spotify_can_win_without_musicbrainz_bonus(self):
        result=agg.aggregate(Q,{'spotify':[entry('spotify')],
            'musicbrainz':[entry('musicbrainz','Greatest Hits')]})
        self.assertEqual(result['auto']['source'],'spotify')

    def test_corroboration_is_release_specific(self):
        r=agg.aggregate(Q,{'spotify':[entry('spotify')],
                           'deezer':[entry('deezer','The Eminem Show')],
                           'musicbrainz':[entry('musicbrainz','Encore')]})
        by={v['source']:v for v in r['candidates']}
        self.assertEqual(by['spotify']['source_support'],2)
        self.assertEqual(by['deezer']['source_support'],1)

    def test_wrong_artist_gets_zero(self):
        result=agg.aggregate(Q,{'musicbrainz':[entry('musicbrainz')],
                                'deezer':[entry('deezer',artist='Madonna')]})
        self.assertEqual(next(v for v in result['candidates'] if v['source']=='deezer')['score'],0)

    def test_apple_music_not_albumartist(self):
        broken=entry('itunes');broken['albumartist']='Apple Music'
        result=agg.aggregate(Q,{'itunes':[broken],'deezer':[entry('deezer')]})
        self.assertEqual(result['auto']['source'],'deezer')

    def test_filename_inference_needs_review(self):
        result=agg.aggregate({**Q,'inferred_filename':True},{'deezer':[entry('deezer')]})
        self.assertNotEqual(result['auto']['state'],'ready')

    def test_ambiguous_releases_are_never_autoselected(self):
        q={**Q,'album':'','albumartist':''}
        x=agg.aggregate(q,{'deezer':[entry('deezer','Encore')],
                           'spotify':[entry('spotify','Greatest Hits')]})
        self.assertEqual(x['auto']['state'],'ambiguous')

    def test_compilation_does_not_imply_various(self):
        q={**Q,'_secondaryreleasetype':'compilation'}
        result=agg.aggregate(q,{'deezer':[entry('deezer')]})
        self.assertEqual(result['auto']['source'],'deezer')

    def test_invalid_source_has_no_credit(self):
        broken=entry('deezer',artist='Apple Music')
        x=agg.aggregate(Q,{'deezer':[broken]})
        self.assertNotEqual(x['auto']['state'],'ready')

    def test_cache_key_invalidated_for_new_model(self):
        self.assertNotEqual(agg.query_key(Q),__import__('hashlib').sha256(
            '|'.join(agg.norm(Q.get(k,'')) for k in
            ('title','artist','album','isrc','recording_mbid')).encode()).hexdigest())

class DummyMetadata(dict):
    def copy(self,other):
        self.clear()
        self.update(other)

class DummyFile:
    def __init__(self):
        self.filename='test.flac'
        self.metadata=DummyMetadata({'title':'Mockingbird','artist':'Eminem','album':'Encore'})
        self.updates=0
        self.saves=0
    def update(self):self.updates+=1
    def save(self):self.saves+=1

class TestAutomaticWriting(unittest.TestCase):
    def result(self):
        return agg.aggregate(Q,{'deezer':[entry('deezer')]})

    def with_fake_api(self):
        fake=types.ModuleType('picard.plugin3.api')
        fake.Metadata=DummyMetadata
        return patch.dict(sys.modules,{'picard.plugin3.api':fake})

    def test_apply_in_memory_only_by_default(self):
        f=DummyFile()
        with self.with_fake_api():
            result=auto.apply_best_to_file(f,Q,self.result())
        self.assertEqual(result['source'],'deezer')
        self.assertEqual(f.saves,0)
        self.assertEqual(f.metadata['~picardwulf_source'],'deezer')
        self.assertEqual(f.updates,1)

    def test_opt_in_save_backups_first(self):
        f=DummyFile()
        events=[]
        events.append('backup')
        f.save=lambda:events.append('save')
        with self.with_fake_api():
            result=auto.apply_best_to_file(f,Q,self.result(),save=True,
                verified_backup={'path':f.filename,'backup':'saved-audio.flac'})
        self.assertEqual(events,['backup','save'])
        self.assertEqual(result['backup'],'saved-audio.flac')

    def test_backup_failure_does_not_mutate_tags(self):
        f=DummyFile()
        before=dict(f.metadata)
        with self.with_fake_api():
            with self.assertRaises(nw.UnsafeCandidate):
                auto.apply_best_to_file(f,Q,self.result(),save=True)
        self.assertEqual(f.metadata,before)
        self.assertEqual(f.saves,0)

    def test_ambiguous_does_not_touch_file(self):
        f=DummyFile();before=dict(f.metadata)
        with self.with_fake_api():
            with self.assertRaises(nw.UnsafeCandidate):
                auto.apply_best_to_file(f,Q,{'auto':{'state':'ambiguous','reason':'conflict'}})
        self.assertEqual(f.metadata,before)

    def test_existing_mbid_not_rebranded_as_external(self):
        q={**Q,'recording_mbid':'27759a11-4140-4ab8-a900-8584f5a716ab'}
        self.assertEqual(agg.aggregate(q,{'deezer':[entry('deezer')]} )['auto']['state'],'ready')
        with self.assertRaises(nw.UnsafeCandidate):
            auto.proposal_for_auto(q,agg.aggregate(q,{'deezer':[entry('deezer')]} ))



class TestReleaseIdentityAndRace(unittest.TestCase):
    def test_two_musicbrainz_editions_with_same_title_are_ambiguous(self):
        a=entry('musicbrainz')
        b=entry('musicbrainz')
        a['release_mbid']='9f497f21-c32e-42cb-bc3f-7022f43d1b4d'
        b['release_mbid']='9f497f21-c32e-42cb-bc3f-7022f43d1b4e'
        x=agg.aggregate(Q,{'musicbrainz':[a,b]})
        self.assertEqual(x['auto']['state'],'ambiguous')

    def test_deezer_album_identity_is_kept(self):
        seen=[]
        def request(source,url,params):
            return {'data':[{'title':'Mockingbird','artist':{'name':'Eminem'},
                             'album':{'title':'Encore','id':12345},'duration':250}]}
        result=ad.deezer(Q,request,{})
        self.assertEqual(result[0]['provider_album_id'],'12345')

    def test_spotify_album_identity_is_kept(self):
        q=dict(Q)
        def request(source,url,params,headers=None,form=None):
            if source=='spotify_auth':return {'access_token':'token','expires_in':3600}
            return {'tracks':{'items':[{'name':'Mockingbird',
                      'artists':[{'name':'Eminem'}], 'duration_ms':250000,
                      'album':{'name':'Encore','id':'spotify-album-123',
                               'artists':[{'name':'Eminem'}]}}]}}
        result=ad.spotify(q,request,{'spotify_client_id':'id','spotify_client_secret':'secret'})
        self.assertEqual(result[0]['provider_album_id'],'spotify-album-123')

    def test_lastfm_album_enrichment(self):
        seen=[]
        def request(source,url,params):
            seen.append(params['method'])
            if params['method']=='track.search':
                return {'results':{'trackmatches':{'track':[{'name':'Mockingbird','artist':'Eminem'}]}}}
            return {'track':{'album':{'title':'Encore','artist':'Eminem','mbid':'external-release-id'}}}
        result=ad.lastfm(Q,request,{'lastfm_api_key':'test'})
        self.assertEqual(result[0]['album'],'Encore')
        self.assertEqual(result[0]['provider_album_id'],'external-release-id')
        self.assertEqual(seen,['track.search','track.getInfo'])

    def test_picard_native_auto_assignment_can_be_superseded_safely(self):
        f=DummyFile()
        f.metadata=DummyMetadata({'title':'Mockingbird','artist':'Eminem','album':'Encore',
                       'albumartist':'Eminem','isrc':'USIR10400624','~length':250000})
        initial=dict(f.metadata)
        q=agg.clean_track(initial)
        result=agg.aggregate(q,{'deezer':[entry('deezer')]})
        self.assertEqual(result['auto']['state'],'ready')
        f.metadata['musicbrainz_recordingid']='27759a11-4140-4ab8-a900-8584f5a716ab'
        f.metadata['musicbrainz_albumid']='9f497f21-c32e-42cb-bc3f-7022f43d1b4d'
        with self._fake_api():
            out=auto.apply_best_to_file(f,q,result)
        self.assertEqual(out['source'],'deezer')
        self.assertNotIn('musicbrainz_albumid',f.metadata)
        self.assertNotIn('musicbrainz_recordingid',f.metadata)
        self.assertEqual(f.saves,0)

    @staticmethod
    def _fake_api():
        fake=types.ModuleType('picard.plugin3.api')
        fake.Metadata=DummyMetadata
        return patch.dict(sys.modules,{'picard.plugin3.api':fake})

if __name__=='__main__':unittest.main()
