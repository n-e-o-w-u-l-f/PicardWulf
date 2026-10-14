import importlib
import pathlib
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
# Load the standalone core without importing the Qt-dependent Picard plugin.
if 'neowulf_picard_repair' not in sys.modules:
    pkg=types.ModuleType('neowulf_picard_repair')
    pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
    sys.modules['neowulf_picard_repair']=pkg
mod=importlib.import_module('neowulf_picard_repair.universal_engine')
ad=importlib.import_module('neowulf_picard_repair.universal_adapters')
cr=importlib.import_module('neowulf_picard_repair.credentials')

Q={'artist':'Eminem','title':'Mockingbird','album':'Encore','albumartist':'Eminem',
   'duration_ms':250000,'isrc':'USIR10400624','recording_mbid':''}

class TestScoring(unittest.TestCase):
    def c(self,**changes):return dict(ad.item('deezer','Mockingbird','Eminem','Encore',250000),**changes)
    def test_exact(self):
        self.assertGreater(mod.score(Q,ad.item('deezer','Mockingbird','Eminem','Encore',250000))[0],.92)
    def test_title_conflict(self):
        self.assertEqual(mod.score(Q,ad.item('deezer','Stan','Eminem'))[0],0)
    def test_artist_conflict(self):
        self.assertEqual(mod.score(Q,ad.item('deezer','Mockingbird','Queen'))[0],0)
    def test_isrc_conflict(self):
        self.assertEqual(mod.score(Q,ad.item('deezer','Mockingbird','Eminem','Encore',250000,'DEZZZ0000001'))[0],0)
    def test_duration_conflict(self):
        self.assertEqual(mod.score(Q,ad.item('deezer','Mockingbird','Eminem','Encore',390000))[0],0)
    def test_albumartist_va_conflict(self):
        self.assertEqual(mod.score(Q,ad.item('itunes','Mockingbird','Eminem','Encore',250000,albumartist='Various Artists'))[0],0)
    def test_provider_name_is_never_used_as_artist(self):
        self.assertIsNone(mod.clean_track({'title':'Mockingbird','artist':'Apple Music'}))
    def test_compilation_does_not_create_va(self):
        q=mod.clean_track({**Q,'_secondaryreleasetype':'compilation'})
        self.assertEqual(q['albumartist'],'Eminem')
    def test_normalization(self):
        self.assertEqual(mod.norm('  Éminem,  LIVE!  '),'eminem live')
    def test_aggregate_converges_readonly(self):
        r=mod.aggregate(Q,{
            'musicbrainz':[ad.item('musicbrainz','Mockingbird','Eminem','Encore',250000)],
            'deezer':[ad.item('deezer','Mockingbird','Eminem','Encore',251000)],
            'itunes':[ad.item('itunes','Mockingbird','Apple Music','Encore')]})
        self.assertEqual(r['verdict'],'review_high_confidence')
        self.assertEqual(r['candidates'][0]['source_support'],2)
        self.assertTrue(any(v['score']==0 for v in r['candidates']))
    def test_different_release_not_mutated(self):
        q=dict(Q)
        mod.aggregate(q,{'deezer':[ad.item('deezer','Mockingbird','Eminem','Greatest Hits',250000)]})
        self.assertEqual(q,Q)

class TestProviders(unittest.TestCase):
    def test_musicbrainz_isrc_search_and_parse(self):
        calls=[]
        def req(*args,**kwargs):
            calls.append((args,kwargs));return {'recordings':[{'id':'mb123','title':'Mockingbird','length':250000,
                     'artist-credit':[{'name':'Eminem'}], 'releases':[{'title':'Encore'}]}]}
        x=ad.musicbrainz(Q,req,{})
        self.assertIn('isrc:',calls[0][0][2]['query'])
        self.assertEqual(x[0]['recording_mbid'],'mb123')
    def test_deezer_parse(self):
        def req(*args,**kwargs):return {'data':[{'title':'Mockingbird','artist':{'name':'Eminem'},
                  'album':{'title':'Encore'},'duration':250,'link':'https://www.deezer.com/track/33'}]}
        self.assertEqual(ad.deezer(Q,req,{})[0]['duration_ms'],250000)
    def test_itunes_albums_separate(self):
        def req(*args,**kwargs):return {'results':[{'trackName':'Mockingbird','artistName':'Eminem',
                                  'collectionArtistName':'Eminem','collectionName':'Encore'}]}
        self.assertEqual(ad.itunes(Q,req,{})[0]['albumartist'],'Eminem')
    def test_spotify_without_credentials(self):
        self.assertIsNone(ad.spotify(Q,lambda *a,**kw:1,{}))
    def test_spotify_token_grant(self):
        seen=[]
        def req(source,url,p,headers=None,form=None):
            seen.append((source,headers,form))
            if source=='spotify_auth':return {'access_token':'fake','expires_in':3600}
            return {'tracks':{'items':[{'name':'Mockingbird','artists':[{'name':'Eminem'}],
                    'album':{'name':'Encore'},'duration_ms':250000,'external_ids':{'isrc':'USIR10400624'}}]}}
        cred={'spotify_client_id':'id','spotify_client_secret':'secret'}
        r=ad.spotify(Q,req,cred)
        self.assertEqual(r[0]['isrc'],'USIR10400624')
        self.assertEqual(seen[1][1]['Authorization'],'Bearer fake')
        self.assertNotIn('secret',str(r))
    def test_soundcloud_requires_oauth(self):
        self.assertIsNone(ad.soundcloud(Q,lambda *a,**kw:1,{}))
    def test_soundcloud_shape(self):
        def req(*a,**kw):return {'collection':[{'title':'Mockingbird','user':{'username':'Eminem'},'duration':250000}]}
        self.assertEqual(ad.soundcloud(Q,req,{'soundcloud_token':'t'})[0]['source'],'soundcloud')
    def test_lastfm_key_required(self):
        self.assertIsNone(ad.lastfm(Q,lambda *a,**kw:1,{}))
    def test_lastfm_parse(self):
        def req(*a,**kw):return {'results':{'trackmatches':{'track':{'name':'Mockingbird','artist':'Eminem'}}}}
        self.assertEqual(len(ad.lastfm(Q,req,{'lastfm_api_key':'k'})),1)
    def test_endpoint_whitelist(self):
        client=mod.HTTPClient()
        with self.assertRaises(ValueError):client.request('spotify','http://api.spotify.com/v1/search',{})
        with self.assertRaises(ValueError):client.request('spotify','https://evil.test/v1/search',{})
        with self.assertRaises(ValueError):client.request('spotify','https://api.spotify.com/v1/users',{})

class TestStoreAndRunner(unittest.TestCase):
    def test_sqlite_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            s=mod.ResultStore(pathlib.Path(d)/'cache.db')
            s.save_response('abc',{'results':[1]})
            self.assertEqual(s.get_response('abc'),{'results':[1]})
            s.save_result('f',Q,{'status':{'deezer':'ok'}})
            self.assertEqual(s.recent()[0]['payload']['status']['deezer'],'ok')
    def test_result_cache_skips_duplicate_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            s=mod.ResultStore(pathlib.Path(d)/'cache.db')
            s.save_result(mod.query_key(Q),Q,{'status':{}})
            eng=mod.UniversalAggregator(store=s,credentials={})
            try:self.assertFalse(eng.schedule(Q))
            finally:
                eng.stop()
                self.assertTrue(eng.wait_stopped(10))
    def test_automatic_sources_and_missing_auth(self):
        calls=[]
        def fake(source,url,query,headers=None,form=None):
            calls.append(source)
            if source=='musicbrainz':return {'recordings':[{'title':'Mockingbird','artist-credit':[{'name':'Eminem'}],
                                                             'length':250000}]}
            if source=='deezer':return {'data':[{'title':'Mockingbird','artist':{'name':'Eminem'},
                                     'album':{'title':'Encore'},'duration':250}]}
            if source=='itunes':return {'results':[]}
            raise AssertionError('Unconfigured providers MUST NOT call network')
        class Transport:request=staticmethod(fake)
        with tempfile.TemporaryDirectory() as d:
            s=mod.ResultStore(pathlib.Path(d)/'cache.db')
            eng=mod.UniversalAggregator(store=s,transport=Transport(),credentials={},
                provider_delays={source:0 for source in ad.SOURCES})
            try:
                self.assertTrue(eng.schedule(Q))
                for _ in range(100):
                    x=s.get_result(mod.query_key(Q))
                    if x:break
                    time.sleep(.01)
                self.assertIsNotNone(x)
                status=x['payload']['status']
                self.assertEqual(status['spotify'],'CREDENTIALS_REQUIRED')
                self.assertEqual(status['soundcloud'],'CREDENTIALS_REQUIRED')
                self.assertEqual(status['lastfm'],'CREDENTIALS_REQUIRED')
                self.assertEqual(set(calls),{'musicbrainz','deezer','itunes'})
                self.assertEqual(x['query']['albumartist'],'Eminem')
            finally:
                eng.stop()
                self.assertTrue(eng.wait_stopped(10))
    def test_no_plaintext_vault_fallback(self):
        if cr.os.name!='nt':
            with self.assertRaises(RuntimeError):cr.save({'lastfm_api_key':'foo'})

if __name__=='__main__':unittest.main()
