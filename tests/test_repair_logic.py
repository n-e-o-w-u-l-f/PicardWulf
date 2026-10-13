import importlib.util
import pathlib
import unittest

root = pathlib.Path(__file__).parents[1] / 'neowulf_picard_repair'
spec = importlib.util.spec_from_file_location('repair_logic', root / 'repair_logic.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestRepair(unittest.TestCase):
    def setUp(self):
        self.script = '$noop(NEOWULF_UNMATCHED_FALLBACK)$if(' + mod.OLD + ',bad,good)'
        self.scripts = {'custom': {'title': 'NEOWULF', 'script': self.script, 'other': 123},
                        'unrelated': {'title': 'Something', 'script': '%album%'}}
    def test_predicate_only(self):
        result, ident = mod.prepare_update(self.scripts)
        self.assertEqual(ident,'custom')
        self.assertEqual(result[ident]['script'],self.script.replace(mod.OLD,mod.NEW))
        self.assertEqual(self.scripts['custom']['script'],self.script)
    def test_unrelated_script_unchanged(self):
        result,_=mod.prepare_update(self.scripts)
        self.assertEqual(result['unrelated'],self.scripts['unrelated'])
    def test_extra_keys_unchanged(self):
        result,_=mod.prepare_update(self.scripts)
        self.assertEqual(result['custom']['other'],123)
    def test_multiple_candidates_rejected(self):
        self.scripts['other'] = {'title':'NEOWULF-Alt','script':self.script}
        with self.assertRaises(mod.RepairNotPossible):mod.prepare_update(self.scripts)
    def test_no_neowulf_marker_rejected(self):
        self.scripts['custom']['title']='Other'
        self.scripts['custom']['script']=mod.OLD
        with self.assertRaises(mod.RepairNotPossible):mod.prepare_update(self.scripts)
    def test_duplicate_predicate_rejected(self):
        self.scripts['custom']['script']+=mod.OLD
        with self.assertRaises(mod.RepairNotPossible):mod.prepare_update(self.scripts)
    def test_already_patched_rejected(self):
        self.scripts['custom']['script']=self.script.replace(mod.OLD,mod.NEW)
        with self.assertRaises(mod.RepairNotPossible):mod.prepare_update(self.scripts)
    def test_partial_patch_rejected(self):
        self.scripts['custom']['script']+=mod.NEW
        with self.assertRaises(mod.RepairNotPossible):mod.prepare_update(self.scripts)
    def test_invalid_map_rejected(self):
        with self.assertRaises(mod.RepairNotPossible):mod.prepare_update([])
    def test_album_artist_exact_mbid(self):
        m={'musicbrainz_releasegroupid':mod.RGID,'albumartist':'Various Artists','_secondaryreleasetype':'compilation'}
        self.assertTrue(mod.correct_curtain_call_metadata(m))
        self.assertEqual(m['albumartist'],'Eminem')
        self.assertEqual(m['_secondaryreleasetype'],'compilation')
    def test_apple_music_provider_fix_for_specific_album(self):
        m={'musicbrainz_releasegroupid':mod.RGID,'albumartist':'Apple Music'}
        self.assertTrue(mod.correct_curtain_call_metadata(m))
        self.assertEqual(m['albumartist'],'Eminem')
    def test_other_album_unchanged(self):
        m={'musicbrainz_releasegroupid':'not-that','albumartist':'Various Artists'}
        self.assertFalse(mod.correct_curtain_call_metadata(m))
        self.assertEqual(m['albumartist'],'Various Artists')
    def test_metadata_without_mbid_unchanged(self):
        m={'album':'Curtain Call 2','albumartist':'Various Artists'}
        self.assertFalse(mod.correct_curtain_call_metadata(m))
    def test_idempotent_meta(self):
        m={'musicbrainz_releasegroupid':mod.RGID,'albumartist':'Eminem'}
        self.assertFalse(mod.correct_curtain_call_metadata(m))
    def test_mbid_list(self):
        m={'musicbrainz_releasegroupid':[mod.RGID],'albumartist':'Various Artists'}
        self.assertTrue(mod.correct_curtain_call_metadata(m))
if __name__=='__main__':unittest.main()
