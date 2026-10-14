"""PicardWulf v1.0: full metadata adapter and bidirectional ranking regressions.

All network payloads are synthetic, no credentials, GUI or music originals.
"""
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
package=types.ModuleType('full_metadata_test')
package.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules['full_metadata_test']=package
ad=importlib.import_module('full_metadata_test.universal_adapters')
eng=importlib.import_module('full_metadata_test.universal_engine')
nw=importlib.import_module('full_metadata_test.native_workflow')
auto=importlib.import_module('full_metadata_test.auto_apply')

Q={'artist':'Eminem','title':'Mockingbird','album':'Encore',
   'albumartist':'Eminem','isrc':'','recording_mbid':'',
   'duration_ms':250000}

class Metadata(dict):
    def copy(self, other):
        self.clear()
        self.update(other)

class Track:
    filename='synthetic.flac'
    can_save=True
    can_edit_tags=True
    def __init__(self):
        self.metadata=Metadata({'artist':'Eminem','title':'Mockingbird','album':'Encore'})
        self.saves=0
        self.updates=0
    def save(self):self.saves+=1
    def update(self):self.updates+=1

class FullMetadataTests(unittest.TestCase):
    def test_deezer_track_and_album_details_are_collected(self):
        calls=[]
        def transport(src,url,params):
            calls.append((src,url))
            if src=='deezer':
                return {'data':[{'id':1001,'title':'Mockingbird','artist':{'name':'Eminem'},
                    'album':{'id':2002,'title':'Encore','cover':'DO_NOT_CACHE'},'duration':250,
                    'link':'https://www.deezer.com/track/1001'}]}
            if src=='deezer_track':
                return {'title':'Mockingbird','artist':{'name':'Eminem'},'isrc':'USIR10400624',
                    'track_position':16,'disk_number':1,'album':{'id':2002,'title':'Encore'}}
            if src=='deezer_album':
                return {'title':'Encore','id':2002,'release_date':'2004-11-12','upc':'123456789012',
                    'nb_tracks':20,'label':'Aftermath / Interscope','artist':{'name':'Eminem'},
                    'cover':'DO_NOT_CACHE'}
            raise AssertionError(src)
        result=ad.deezer(Q,transport,{})
        self.assertEqual([s for s,_ in calls],['deezer','deezer_track','deezer_album'])
        found=result[0]
        for field,value in {'source':'deezer','isrc':'USIR10400624','tracknumber':'16',
                            'discnumber':'1','totaltracks':'20','albumartist':'Eminem',
                            'release_date':'2004-11-12','label':'Aftermath / Interscope',
                            'barcode':'123456789012','enrichment_status':'COMPLETE'}.items():
            self.assertEqual(found[field],value,(field,found))
        self.assertNotIn('DO_NOT_CACHE',repr(result))
        proposal=nw.tag_proposal(Q,found)
        for field,value in {'album':'Encore','artist':'Eminem','isrc':'USIR10400624',
                            'tracknumber':'16','discnumber':'1','totaltracks':'20',
                            'date':'2004-11-12','label':'Aftermath / Interscope',
                            'barcode':'123456789012'}.items():
            self.assertEqual(proposal[field],value)
        self.assertNotIn('musicbrainz_albumid',proposal)
        self.assertNotIn('musicbrainz_recordingid',proposal)

    def test_missing_deezer_ids_does_not_trigger_extra_queries(self):
        calls=[]
        def transport(src,url,params):
            calls.append(src)
            return {'data':[{'title':'Mockingbird','artist':{'name':'Eminem'},
                             'album':{'title':'Encore'},'duration':250}]}
        self.assertEqual(ad.deezer(Q,transport,{})[0]['title'],'Mockingbird')
        self.assertEqual(calls,['deezer'])

    def test_deezer_detail_conflict_forbids_auto_selection(self):
        def transport(src,url,params):
            if src=='deezer':
                return {'data':[{'id':1001,'title':'Mockingbird','artist':{'name':'Eminem'},
                                  'album':{'title':'Encore','id':2002},'duration':250}]}
            return {'title':'Mockingbird','artist':{'name':'Wrong Artist'},'album':{'title':'Encore'}}
        candidate=ad.deezer(Q,transport,{})[0]
        self.assertEqual(candidate['enrichment_status'],'CONFLICT')
        self.assertEqual(eng.aggregate(Q,{'deezer':[candidate]})['auto']['state'],'no_match')
        with self.assertRaises(nw.UnsafeCandidate):
            nw.tag_proposal(Q,candidate)

    def test_itunes_complete_fields_are_available_in_picard_proposal(self):
        def transport(src,url,params):
            return {'results':[{'trackName':'Mockingbird','artistName':'Eminem',
                'collectionName':'Encore','collectionArtistName':'Eminem',
                'trackTimeMillis':250000,'trackNumber':16,'discNumber':1,
                'trackCount':20,'discCount':2,'primaryGenreName':'Hip-Hop/Rap',
                'composerName':'M. Mathers','releaseDate':'2004-11-12T08:00:00Z'}]}
        found=ad.itunes(Q,transport,{})[0]
        self.assertEqual(found['tracknumber'],'16')
        self.assertEqual(found['totaldiscs'],'2')
        self.assertEqual(found['genre'],'Hip-Hop/Rap')
        # Timestamp is not silently converted to a wrong local date.
        self.assertNotIn('date',nw.tag_proposal(Q,found))
        self.assertEqual(nw.tag_proposal(Q,found)['composer'],'M. Mathers')

    def test_soundcloud_publisher_metadata_not_username(self):
        def transport(src,url,params,headers=None):
            return {'collection':[{'id':123,'title':'Mockingbird','duration':250000,
                'publisher_metadata':{'artist':'Eminem','album_title':'Encore',
                    'isrc':'USIR10400624','album_id':898,'label_name':'Aftermath'},
                'user':{'username':'Fan Uploader'},'genre':'Hip-hop'}]}
        found=ad.soundcloud(Q,transport,{'soundcloud_token':'valid_test_token'})[0]
        self.assertEqual(found['artist'],'Eminem')
        self.assertEqual(found['genre'],'Hip-hop')
        self.assertEqual(found['label'],'Aftermath')
        self.assertEqual(found['provider_album_id'],'898')
        self.assertEqual(nw.tag_proposal(Q,found)['isrc'],'USIR10400624')

    def test_musicbrainz_beats_deezer_if_musicbrainz_evidence_stronger(self):
        mb=ad.item('musicbrainz','Mockingbird','Eminem','Encore',250000,'USIR10400624',
                   albumartist='Eminem')
        deezer=ad.item('deezer','Mockingbird','Eminem','Encore',230000)
        result=eng.aggregate(Q,{'deezer':[deezer],'musicbrainz':[mb]})
        self.assertEqual(result['candidates'][0]['source'],'musicbrainz')

    def test_deezer_beats_musicbrainz_if_deezer_evidence_stronger(self):
        mb=ad.item('musicbrainz','Mockingbird','Eminem','Curtain Call 2',240000)
        deezer=ad.item('deezer','Mockingbird','Eminem','Encore',250000,'USIR10400624')
        result=eng.aggregate(Q,{'musicbrainz':[mb],'deezer':[deezer]})
        self.assertEqual(result['candidates'][0]['source'],'deezer')
        self.assertEqual(result['auto']['source'],'deezer')

    def test_in_memory_apply_uses_full_metadata_without_saving_audio(self):
        song=Track()
        q={**Q,'albumartist':'Eminem'}
        found=ad.item('deezer','Mockingbird','Eminem','Encore',250000,'USIR10400624',
                      albumartist='Eminem',tracknumber=16,discnumber=1,totaltracks=20,
                      release_date='2004-11-12',label='Interscope',genre='Hip-Hop/Rap')
        result=eng.aggregate(q,{'deezer':[found]})
        self.assertEqual(result['auto']['state'],'ready')
        fake=types.ModuleType('picard.plugin3.api')
        fake.Metadata=Metadata
        with patch.dict(sys.modules,{'picard.plugin3.api':fake}):
            auto.apply_best_to_file(song,q,result)
        self.assertEqual(song.saves,0)
        self.assertEqual(song.metadata['tracknumber'],'16')
        self.assertEqual(song.metadata['totaltracks'],'20')
        self.assertEqual(song.metadata['date'],'2004-11-12')
        self.assertEqual(song.metadata['label'],'Interscope')
        self.assertEqual(song.metadata['genre'],'Hip-Hop/Rap')
        self.assertEqual(song.metadata['~picardwulf_source'],'deezer')
        self.assertNotIn('musicbrainz_albumid',song.metadata)

    def test_external_album_artist_fills_missing_original_without_implicit_various(self):
        q={**Q,'albumartist':''}
        good=ad.item('deezer','Mockingbird','Eminem','Encore',250000,albumartist='Eminem')
        self.assertEqual(nw.tag_proposal(q,good)['albumartist'],'Eminem')
        risky=ad.item('deezer','Mockingbird','Eminem','Encore',250000,albumartist='Various Artists')
        self.assertNotIn('albumartist',nw.tag_proposal(q,risky))

    def test_existing_artist_credit_is_not_replaced_by_external_compilation(self):
        q={**Q,'albumartist':'Eminem'}
        risky=ad.item('deezer','Mockingbird','Eminem','Curtain Call 2',250000,
                      albumartist='Various Artists')
        with self.assertRaises(nw.UnsafeCandidate):nw.tag_proposal(q,risky)

    def test_deezer_details_share_public_search_hourly_budget(self):
        import tempfile
        requests=[]
        class Transport:
            def request(self,source,*args,**kwargs):
                requests.append(source)
                return {'data':[]}
        with tempfile.TemporaryDirectory() as directory:
            store=eng.ResultStore(Path(directory)/'queue.db')
            provider=importlib.import_module('full_metadata_test.provider_policy')
            managed=provider.PolicyClient(store,Transport(),{},
                {'requests_per_hour':1},{'deezer':0,'deezer_track':0,'deezer_album':0})
            managed.request('deezer','https://api.deezer.com/search',{'q':'synthetic'})
            with self.assertRaises(provider.ProviderError) as caught:
                managed.request('deezer_track','https://api.deezer.com/track/123',{})
            self.assertEqual(caught.exception.state,'QUOTA_WAIT')
            self.assertFalse(caught.exception.attempted)
            self.assertEqual(requests,['deezer'])

    def test_deezer_detail_host_path_allowlist(self):
        client=eng.HTTPClient()
        for url in ('https://api.deezer.com/album/1/../../admin',
                    'https://evil.invalid/track/123',
                    'http://api.deezer.com/track/123',
                    'https://api.deezer.com/track/bad'):
            with self.subTest(url=url),self.assertRaises(ValueError):
                client.request('deezer_track',url,{})

if __name__=='__main__':unittest.main()
