"""Regression: cached single-source releases may not suppress eligible providers.

No credentials, user files, network activity, or Picard GUI are involved.
"""
import importlib
import pathlib
import sys
import tempfile
import types
import unittest

ROOT=pathlib.Path(__file__).parents[1]
pkg=types.ModuleType('provider_completeness')
pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules[pkg.__name__]=pkg
engine=importlib.import_module(pkg.__name__+'.universal_engine')
adapters=importlib.import_module(pkg.__name__+'.universal_adapters')
policy=importlib.import_module(pkg.__name__+'.provider_policy')

QUERY={'artist':'Synthetic','title':'Track','album':'Album','albumartist':'Synthetic',
       'duration_ms':100000,'isrc':'','recording_mbid':''}
DISABLED=['itunes','spotify','soundcloud','lastfm']

class SourceCompletenessTests(unittest.TestCase):
    def test_album_pool_must_not_skip_musicbrainz_and_deezer_comparison(self):
        calls=[]
        class Transport:
            def request(self,source,*args,**kwargs):
                calls.append(source)
                if source=='musicbrainz':return {'recordings':[]}
                if source=='deezer':return {'data':[]}
                raise AssertionError('unavailable provider network call: '+source)
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(pathlib.Path(directory)/'jobs.db')
            # Album-local pool from a sibling track is not provider completeness
            # proof for the newly imported file.
            store.save_response(policy.album_cache_key(QUERY),[
                adapters.item('deezer','Track','Synthetic','Album',100000,
                              albumartist='Synthetic',provider_album_id='42')])
            runner=engine.UniversalAggregator(store=store,transport=Transport(),
                credentials={},paused=True,provider_options={'disabled':DISABLED},
                provider_delays={name:0 for name in adapters.SOURCES})
            try:
                self.assertTrue(runner.wait_ready())
                key=engine.query_key(QUERY)
                store.enqueue(key,QUERY)
                _,_,_,revision=store.claim_jobs(1)[0]
                payload,_=runner._work(key,QUERY,False,revision)
                self.assertEqual(calls,['musicbrainz','deezer'])
                self.assertEqual(payload['completion'],'COMPLETE')
                self.assertEqual(payload['status']['musicbrainz'],'ok')
                self.assertEqual(payload['status']['deezer'],'ok')
                self.assertNotEqual(payload['completion'],'LOCAL_CACHE')
            finally:
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))

    def test_registered_soundcloud_competes_bidirectionally_with_deezer_and_mb(self):
        # A valid previously issued token must cause an actual catalog
        # request, even if an album-pool hit for a sibling is already ready.
        calls=[]
        class Transport:
            def request(self,source,*args,**kwargs):
                calls.append(source)
                if source=='musicbrainz':return {'recordings':[]}
                if source=='deezer':return {'data':[{'title':'Track',
                    'artist':{'name':'Synthetic'},'album':{'title':'Album'},
                    'duration':112}]}
                if source=='soundcloud':return {'collection':[{'title':'Track',
                    'publisher_metadata':{'artist':'Synthetic','album_title':'Album',
                                          'isrc':'USAAA2600001'},
                    'user':{'username':'Not Artist'},'duration':100000}]}
                raise AssertionError('unconfigured source called '+source)
        disabled=['itunes','spotify','lastfm']
        q=dict(QUERY)
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(pathlib.Path(directory)/'jobs.db')
            store.save_response(policy.album_cache_key(q),[
                adapters.item('deezer','Track','Synthetic','Album',100000,
                              albumartist='Synthetic')])
            runner=engine.UniversalAggregator(store=store,transport=Transport(),
                    credentials={'soundcloud_token':'synthetic-test-only'},
                    paused=True,provider_options={'disabled':disabled},
                    provider_delays={name:0 for name in adapters.SOURCES})
            try:
                self.assertTrue(runner.wait_ready())
                key=engine.query_key(q)
                store.enqueue(key,q)
                _,_,_,revision=store.claim_jobs(1)[0]
                result,_=runner._work(key,q,False,revision)
                self.assertEqual(calls,['musicbrainz','deezer','soundcloud'])
                self.assertEqual(result['status']['soundcloud'],'ok')
                self.assertEqual(result['status']['deezer'],'ok')
                self.assertEqual(result['completion'],'COMPLETE')
                self.assertEqual(result['candidates'][0]['source'],'soundcloud')
                self.assertNotIn('musicbrainz_albumid',result['candidates'][0])
            finally:
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))

    def test_completed_provider_checkpoint_avoids_extra_request_but_queries_missing_source(self):
        calls=[]
        class Transport:
            def request(self,source,*args,**kwargs):
                calls.append(source)
                if source=='deezer':return {'data':[]}
                raise AssertionError('completed provider must not refetch')
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(pathlib.Path(directory)/'jobs.db')
            runner=engine.UniversalAggregator(store=store,transport=Transport(),
                    credentials={},paused=True,provider_options={'disabled':DISABLED},
                    provider_delays={name:0 for name in adapters.SOURCES})
            try:
                self.assertTrue(runner.wait_ready())
                key=engine.query_key(QUERY)
                store.enqueue(key,QUERY)
                _,_,_,revision=store.claim_jobs(1)[0]
                cached=adapters.item('musicbrainz','Track','Synthetic','Album',100000,
                                    albumartist='Synthetic')
                self.assertTrue(store.checkpoint(key,revision,'musicbrainz',[cached],'COMPLETE'))
                result,_=runner._work(key,QUERY,False,revision)
                self.assertEqual(calls,['deezer'])
                self.assertEqual(result['completion'],'COMPLETE')
                self.assertEqual(result['status']['musicbrainz'],'COMPLETE')
                self.assertEqual(result['status']['deezer'],'ok')
            finally:
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))

    def test_enabled_lastfm_must_not_be_silently_skipped_after_mb_match(self):
        calls=[]
        release='12345678-1234-4234-8234-123456789013'
        recording='12345678-1234-4234-8234-123456789012'
        class Transport:
            def request(self,source,*args,**kwargs):
                calls.append(source)
                if source=='musicbrainz':
                    return {'recordings':[{'id':recording,'title':'Track','length':100000,
                        'artist-credit':[{'name':'Synthetic'}],
                        'releases':[{'id':release,'title':'Album','artist-credit':[{'name':'Synthetic'}]}]}]}
                if source=='lastfm':
                    return {'results':{'trackmatches':{'track':[]},
                                       'opensearch:totalResults':'0'}}
                raise AssertionError('unexpected '+source)
        disabled=['deezer','itunes','spotify','soundcloud']
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(pathlib.Path(directory)/'jobs.db')
            runner=engine.UniversalAggregator(store=store,transport=Transport(),
                credentials={'lastfm_api_key':'synthetic-test'},paused=True,
                provider_options={'disabled':disabled},
                provider_delays={name:0 for name in adapters.SOURCES})
            try:
                self.assertTrue(runner.wait_ready())
                key=engine.query_key(QUERY)
                store.enqueue(key,QUERY)
                _,_,_,revision=store.claim_jobs(1)[0]
                payload,_=runner._work(key,QUERY,False,revision)
                self.assertIn('lastfm',calls)
                self.assertEqual(payload['status']['lastfm'],'ok')
                self.assertEqual(payload['completion'],'COMPLETE')
            finally:
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))

if __name__=='__main__':unittest.main()
