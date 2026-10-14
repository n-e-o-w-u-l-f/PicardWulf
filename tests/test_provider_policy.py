"""S2 failure/capability regressions using synthetic requests only."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from urllib.error import HTTPError
from email.utils import formatdate
from unittest.mock import patch

ROOT=Path(__file__).parents[1]
pkg=types.ModuleType('s2_test');pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules['s2_test']=pkg
engine=importlib.import_module('s2_test.universal_engine')
adapters=importlib.import_module('s2_test.universal_adapters')
Q={'artist':'Synthetic','title':'Track','album':'Album'}


class ProviderPolicyTests(unittest.TestCase):
    def test_itunes_javascript_mime_is_parsed_as_json_without_execution(self):
        import io
        class Response(io.BytesIO):
            status=200
            headers={'Content-Type':'text/javascript; charset=utf-8'}
        client=engine.HTTPClient()
        with patch.object(client._opener,'open',return_value=Response(b'{"results":[]}')):
            self.assertEqual(client.request('itunes','https://itunes.apple.com/search',{}),{'results':[]})
        for source,url,body in (('itunes','https://itunes.apple.com/search',b'callback({"results":[]})'),
                                ('deezer','https://api.deezer.com/search',b'{"data":[]}')):
            client=engine.HTTPClient()
            with patch.object(client._opener,'open',return_value=Response(body)):
                with self.assertRaises(engine.ProviderError):client.request(source,url,{})

    def test_soundcloud_auth_quota_defers_before_consumed_marker(self):
        policy=importlib.import_module('s2_test.provider_policy')
        credentials={'soundcloud_client_id':'id','soundcloud_client_secret':'secret',
                     'soundcloud_refresh_token':'old','soundcloud_token_until':'1','soundcloud_token':'expired'}
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(Path(directory)/'queue.db')
            store.reserve_provider('soundcloud_auth',time.time(),900,4)
            managed=policy.PolicyClient(store,None,credentials,{}, {'soundcloud_auth':0})
            with patch.object(adapters,'persist_soundcloud') as persist:
                with self.assertRaises(engine.ProviderError) as caught:
                    adapters.soundcloud(Q,managed.request,credentials)
            self.assertEqual(caught.exception.state,'QUOTA_WAIT')
            persist.assert_not_called()
            self.assertFalse(credentials.get('soundcloud_refresh_pending'))

    def test_credential_update_merges_latest_vault_on_worker(self):
        import threading
        owner=threading.get_ident();writes=[]
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(Path(directory)/'queue.db')
            runner=engine.UniversalAggregator(store=store,credentials={'soundcloud_token':'stale'},paused=True)
            self.assertTrue(runner.wait_ready())
            vault=importlib.import_module('s2_test.credentials')
            def save(values):
                self.assertNotEqual(threading.get_ident(),owner)
                writes.append(dict(values))
            try:
                with patch.object(engine,'load_credentials',return_value={'soundcloud_token':'latest-rotated'}), \
                        patch.object(vault,'save',side_effect=save):
                    receipt=runner.update_credentials({'lastfm_api_key':'synthetic'},persist=True)
                    self.assertTrue(receipt.result(5)['saved'])
                self.assertEqual(writes[0]['soundcloud_token'],'latest-rotated')
                self.assertEqual(runner.credentials['soundcloud_token'],'latest-rotated')
            finally:
                runner.stop();self.assertTrue(runner.wait_stopped())

    def test_managed_soundcloud_refresh_can_use_its_reserved_single_use_token(self):
        policy=importlib.import_module('s2_test.provider_policy')
        credentials={'soundcloud_client_id':'id','soundcloud_client_secret':'secret',
                     'soundcloud_refresh_token':'old','soundcloud_token_until':'1','soundcloud_token':'expired'}
        calls=[]
        class Transport:
            def request(self,source,*args,**kwargs):
                calls.append(source)
                if source=='soundcloud_auth':return {'access_token':'new','refresh_token':'rotated','expires_in':3600}
                return {'collection':[]}
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(Path(directory)/'queue.db')
            managed=policy.PolicyClient(store,Transport(),credentials,{}, {'soundcloud_auth':0,'soundcloud':0})
            with patch.object(adapters,'persist_soundcloud',return_value=None):
                adapters.soundcloud(Q,managed.request,credentials)
            self.assertEqual(calls,['soundcloud_auth','soundcloud'])
            self.assertEqual(credentials['soundcloud_refresh_token'],'rotated')
            self.assertFalse(credentials.get('soundcloud_refresh_pending'))

    def test_nonzero_budget_paces_musicbrainz_lookup_after_search(self):
        policy=importlib.import_module('s2_test.provider_policy')
        calls=[]
        recording='12345678-1234-4234-8234-123456789012'
        class Transport:
            def request(self,source,*args,**kwargs):
                calls.append(source)
                row={'id':recording,'title':'Track','artist-credit':[{'name':'Synthetic'}]}
                if source=='musicbrainz':return {'recordings':[row]}
                return {**row,'releases':[{'id':'12345678-1234-4234-8234-123456789013','title':'Album'}]}
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(Path(directory)/'queue.db')
            managed=policy.PolicyClient(store,Transport(),{}, {},{'musicbrainz':.5})
            result=adapters.musicbrainz(Q,managed.request,{})
            self.assertTrue(result)
            self.assertEqual(calls,['musicbrainz','musicbrainz_lookup'])

    def test_complete_sibling_album_pool_does_not_bypass_pending_provider(self):
        q=engine.clean_track({**Q,'duration':100000,'isrc':'USAAA2600001'})
        candidate=adapters.item('musicbrainz','Track','Synthetic','Album',100000,'USAAA2600001',
                               release_mbid='12345678-1234-4234-8234-123456789013')
        policy=importlib.import_module('s2_test.provider_policy')
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(Path(directory)/'queue.db')
            runner=engine.UniversalAggregator(store=store,credentials={},paused=True,
                                             provider_options={'disabled':['itunes']})
            try:
                self.assertTrue(runner.wait_ready())
                key=engine.query_key(q);store.enqueue(key,q)
                _,_,_,revision=store.claim_jobs(1)[0]
                store.checkpoint(key,revision,'musicbrainz',[candidate],'COMPLETE')
                store.checkpoint(key,revision,'deezer',None,'QUOTA_WAIT',1,time.time()+7200)
                store.save_response(policy.album_cache_key(q),[candidate])
                result,_=runner._work(key,q,False,revision)
                self.assertEqual(result['completion'],'PENDING')
                self.assertEqual(result['auto']['state'],'pending_providers')
            finally:
                runner.stop();self.assertTrue(runner.wait_stopped())

    def test_strong_musicbrainz_search_does_not_hide_better_deezer_release(self):
        calls=[]
        q={**Q,'duration':100000,'isrc':'USAAA2600001'}
        class Transport:
            def request(self,source,*args,**kwargs):
                calls.append(source)
                if source=='musicbrainz':return {'recordings':[{'id':'12345678-1234-4234-8234-123456789012',
                    'title':'Track','length':116000,'artist-credit':[{'name':'Synthetic'}],
                    'releases':[{'id':'12345678-1234-4234-8234-123456789013','title':'Album'}]}]}
                if source=='deezer':return {'data':[{'title':'Track','duration':100,'isrc':'USAAA2600001',
                    'artist':{'name':'Synthetic'},'album':{'title':'Album','id':42}}]}
                return {'results':[]}
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(Path(directory)/'queue.db')
            runner=engine.UniversalAggregator(store=store,transport=Transport(),credentials={},
                provider_delays={s:0 for s in adapters.SOURCES})
            try:
                runner.schedule_async(q)
                key=engine.query_key(engine.clean_track(q))
                deadline=time.monotonic()+5
                while store.get_result(key) is None and time.monotonic()<deadline:time.sleep(.01)
                result=store.get_result(key)['payload']
                self.assertIn('deezer',calls)
                self.assertEqual(result['candidates'][0]['source'],'deezer')
                self.assertEqual(result['auto']['candidate']['source'],'deezer')
            finally:
                runner.stop();self.assertTrue(runner.wait_stopped())

    def test_every_source_has_explicit_capability_and_can_be_disabled(self):
        policy=importlib.import_module('s2_test.provider_policy')
        for source in adapters.SOURCES:
            with self.subTest(source=source):
                result=policy.capability(source,{}, {})
                self.assertIn(result['state'],policy.STATES)
                self.assertFalse(result['observed'])
                self.assertEqual(policy.capability(source,{}, {'disabled':[source]})['state'],'DISABLED')

    def test_http_error_matrix_retry_after_and_no_secret_exception_text(self):
        policy=importlib.import_module('s2_test.provider_policy')
        for status,state in ((401,'CREDENTIALS_REQUIRED'),(403,'RESTRICTED'),
                             (429,'QUOTA_WAIT'),(503,'TEMPORARY_ERROR')):
            client=engine.HTTPClient()
            error=HTTPError('https://example.invalid/secret-token',status,'private-secret',
                            {'Retry-After':'7200'},None)
            with patch.object(client._opener,'open',side_effect=error):
                with self.assertRaises(engine.ProviderError) as caught:
                    client.request('deezer','https://api.deezer.com/search',{})
            self.assertEqual(caught.exception.state,state)
            self.assertNotIn('secret',str(caught.exception))
            if status in (429,503):self.assertGreaterEqual(caught.exception.retry_after,7200)
        self.assertAlmostEqual(policy.retry_delay(formatdate(130,usegmt=True),100),30)
        self.assertIsNone(engine.NoRedirect().redirect_request(None,None,None,None,None,None))

    def test_invalid_json_body_schema_and_response_size_are_errors(self):
        import io
        class Response(io.BytesIO):
            status=200
            headers={'Content-Type':'application/json'}
        for body in (b'not-json',b'0',b'x'*(engine.MAX_BODY+1)):
            client=engine.HTTPClient()
            with patch.object(client._opener,'open',return_value=Response(body)):
                if body==b'0':
                    # The policy layer rejects valid JSON scalars as well.
                    with tempfile.TemporaryDirectory() as directory:
                        store=engine.ResultStore(Path(directory)/'queue.db')
                        policy=importlib.import_module('s2_test.provider_policy')
                        managed=policy.PolicyClient(store,client,{}, {},{'deezer':0})
                        with self.assertRaises(engine.ProviderError):
                            managed.request('deezer','https://api.deezer.com/search',{})
                else:
                    with self.assertRaises(engine.ProviderError):
                        client.request('deezer','https://api.deezer.com/search',{})

    def test_deezer_never_caches_artwork_and_known_album_skips_lastfm_enrichment(self):
        result=adapters.deezer(Q,lambda *a,**k:{'data':[{'title':'Track','artist':{'name':'Synthetic'},
            'album':{'title':'Album','cover':'https://private.invalid/image'},'duration':'123'}]}, {})
        self.assertNotIn('image',repr(result))
        self.assertEqual(result[0]['duration_ms'],123000)
        calls=[]
        def request(*args,**kwargs):
            calls.append(args[2]['method'])
            return {'results':{'trackmatches':{'track':[{'name':'Track','artist':'Synthetic'}]}}}
        adapters.lastfm(Q,request,{'lastfm_api_key':'synthetic-key'})
        self.assertEqual(calls,['track.search'])

    def test_uncertain_refresh_is_never_reused_or_persisted_plaintext(self):
        credentials={'soundcloud_client_id':'id','soundcloud_client_secret':'secret',
                     'soundcloud_refresh_token':'old','soundcloud_token_until':'1','soundcloud_token':'expired'}
        requests=[]
        def failed_request(*args,**kwargs):
            requests.append(args[0]);raise engine.ProviderError('network_loss')
        with patch.object(adapters,'persist_soundcloud',return_value=None):
            with self.assertRaises(engine.ProviderError):adapters.soundcloud(Q,failed_request,credentials)
            with self.assertRaises(engine.ProviderError):adapters.soundcloud(Q,failed_request,credentials)
        self.assertEqual(requests,['soundcloud_auth'])
        self.assertTrue(credentials['soundcloud_refresh_pending'])

    def test_rate_limit_keeps_job_and_partial_result_ineligible_for_auto_apply(self):
        class Transport:
            def request(self,source,*args,**kwargs):
                if source=='deezer':raise engine.ProviderError('HTTP_429',retry_after=30)
                return {'recordings':[]} if source=='musicbrainz' else {'results':[]}
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(Path(directory)/'queue.db')
            runner=engine.UniversalAggregator(store=store,transport=Transport(),credentials={},
                provider_delays={s:0 for s in adapters.SOURCES})
            try:
                runner.schedule_async(Q)
                deadline=time.monotonic()+5
                while store.state_counts()['retry']==0 and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(store.state_counts()['retry'],1)
                result=store.get_result(engine.query_key(engine.clean_track(Q)))
                self.assertEqual(result['payload']['auto']['state'],'pending_providers')
                self.assertEqual(result['payload']['capabilities']['deezer']['state'],'QUOTA_WAIT')
            finally:
                runner.stop();self.assertTrue(runner.wait_stopped())

    def test_persistent_token_bucket_and_circuit_breaker(self):
        policy=importlib.import_module('s2_test.provider_policy')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'queue.db'
            store=engine.ResultStore(path)
            self.assertEqual(store.reserve_provider('deezer',100.,1.,100)['wait'],0)
            fresh=engine.ResultStore(path)
            self.assertGreater(fresh.reserve_provider('deezer',100.,1.,100)['wait'],0)
            fresh.provider_failure('deezer','TEMPORARY_ERROR','network_loss',105.,3)
            self.assertGreater(store.reserve_provider('deezer',101.,1.,100)['wait'],0)
            self.assertEqual(policy.capability('spotify',{'spotify_client_id':'id',
                'spotify_client_secret':'secret'},{} )['state'],'RESTRICTED')
            self.assertEqual(policy.capability('soundcloud',{},{} )['state'],'CREDENTIALS_REQUIRED')
            self.assertEqual(policy.capability('deezer',{}, {'disabled':['deezer']})['state'],'DISABLED')

    def test_malformed_parser_data_and_invalid_token_are_not_empty_success(self):
        with self.assertRaises(ValueError):
            adapters.deezer(Q,lambda *a,**k:{'unexpected':'shape'}, {})
        with self.assertRaises(ValueError):
            adapters.spotify(Q,lambda *a,**k:{}, {'spotify_client_id':'id','spotify_client_secret':'secret'})
        for source in adapters.SOURCES:
            creds={'spotify_access_token':'synthetic','soundcloud_token':'synthetic','lastfm_api_key':'synthetic'}
            with self.subTest(source=source), self.assertRaises(ValueError):
                adapters.ADAPTERS[source](Q,lambda *a,**k:{'unrecognized':'shape'},creds)

    def test_soundcloud_rotates_single_use_refresh_and_persists_before_use(self):
        events=[]
        credentials={'soundcloud_client_id':'id','soundcloud_client_secret':'secret',
                     'soundcloud_refresh_token':'old','soundcloud_token_until':'1',
                     'soundcloud_token':'expired'}
        def persist(values):events.append(('persist',dict(values)))
        def request(source,*args,**kwargs):
            if source=='soundcloud_auth':
                events.append(('request',dict(kwargs['form'])))
                return {'access_token':'new-access','refresh_token':'new-refresh','expires_in':3600}
            return {'collection':[]}
        with patch.object(adapters,'persist_soundcloud',persist):
            adapters.soundcloud(Q,request,credentials)
        self.assertEqual([e[0] for e in events],['persist','request','persist'])
        self.assertEqual(credentials['soundcloud_refresh_token'],'new-refresh')
        self.assertEqual(events[1][1]['refresh_token'],'old')
        self.assertIn('soundcloud_refresh_pending',events[0][1])


if __name__=='__main__':unittest.main()
