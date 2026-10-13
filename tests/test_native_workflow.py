"""PicardWulf native workflow invariants; no Qt/Picard process required."""
import hashlib
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
# Import standalone pure modules under an isolated test package, so Qt plugin
# contract tests can import the actual package after injecting mocked PyQt.
import types
pkg=types.ModuleType('standalone_native_test')
pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules['standalone_native_test']=pkg
nw=importlib.import_module('standalone_native_test.native_workflow')
item=importlib.import_module('standalone_native_test.universal_adapters').item

RG='9f497f21-c32e-42cb-bc3f-7022f43d1b4d'
REC='27759a11-4140-4ab8-a900-8584f5a716ab'
Q={'artist':'Eminem','title':'Mockingbird','album':'Encore','albumartist':'Eminem',
   'isrc':'USIR10400624','recording_mbid':'','duration_ms':250000}

def result(source='musicbrainz',**mods):
    x=item(source,'Mockingbird','Eminem','Encore',250000,'USIR10400624',REC,
           albumartist='Eminem',release_mbid=RG)
    x.update(mods)
    return x

class TestNativeRelease(unittest.TestCase):
    def test_actual_musicbrainz_pair(self):
        self.assertEqual(nw.native_release_target(Q,result()),(RG,REC))
    def test_deezer_cannot_mint_native_album(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result('deezer'))
    def test_spotify_cannot_mint_native_album(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result('spotify'))
    def test_release_uuid_required(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result(release_mbid=''))
    def test_recording_uuid_required(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result(recording_mbid=''))
    def test_invalid_uuid_does_not_pass(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result(release_mbid='ffffffffffffffff'))
    def test_artist_mismatch(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result(artist='Madonna'))
    def test_recording_id_conflict(self):
        q={**Q,'recording_mbid':'ca755bae-87ba-4b6c-a41f-c74b22c32a08'}
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(q,result())
    def test_untrusted_source_as_artist(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result(artist='Apple Music'))
    def test_albumartist_various_not_allowed_for_eminem(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result(albumartist='Various Artists'))
    def test_isrc_conflict(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.native_release_target(Q,result(isrc='DEZZZ9900001'))

class TestOverwrite(unittest.TestCase):
    def test_tag_proposal_uses_verified_mbid(self):
        x=nw.tag_proposal(Q,result())
        self.assertEqual(x['artist'],'Eminem')
        self.assertEqual(x['albumartist'],'Eminem')
        self.assertEqual(x['musicbrainz_albumid'],RG)
        self.assertEqual(x['musicbrainz_recordingid'],REC)
    def test_no_external_provider_mbid_mapping(self):
        x=nw.tag_proposal(Q,result('spotify'))
        self.assertNotIn('musicbrainz_albumid',x)
        self.assertNotIn('musicbrainz_recordingid',x)
        self.assertEqual(x['artist'],'Eminem')
    def test_source_name_not_credited(self):
        with self.assertRaises(nw.UnsafeCandidate):nw.tag_proposal(Q,result(artist='Deezer'))
    def test_changes_only_deltas(self):
        self.assertEqual(nw.changes_for({'artist':'Eminem','title':'Mockingbird'},
                            {'artist':'Eminem','title':'Mockingbird','album':'Encore'}),
                            {'album':('', 'Encore')})
    def test_no_untrusted_albumartist_override(self):
        with self.assertRaises(nw.UnsafeCandidate):
            nw.tag_proposal(Q,result('itunes',albumartist='Apple Music'))
    def test_backup_exact_bytes_hash_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            source=folder/'some_song.flac'
            source.write_bytes(os.urandom(32768))
            destroot=folder/'private-backups'
            with patch.object(nw.shutil,'disk_usage',return_value=type('usage',(),{'free':1000000000})()):
                target=nw.media_backup(source,destroot)
                second=nw.media_backup(source,destroot)
            self.assertNotEqual(target,second)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),
                             hashlib.sha256(target.read_bytes()).digest())
            self.assertEqual(target.read_bytes(),source.read_bytes())
    def test_not_enough_disk_space_must_abort(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'a.mp3';src.write_bytes(b'audio')
            with patch.object(nw.shutil,'disk_usage',return_value=type('usage',(),{'free':3})()):
                with self.assertRaises(nw.UnsafeCandidate):nw.media_backup(src,Path(d)/'backups')
    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'a.mp3';src.write_bytes(b'audio')
            symlink=Path(d)/'link.mp3'
            try:symlink.symlink_to(src)
            except (PermissionError,OSError):self.skipTest('symlink unavailable')
            with self.assertRaises(nw.UnsafeCandidate):nw.media_backup(symlink,Path(d)/'backups')

if __name__=='__main__':unittest.main()
