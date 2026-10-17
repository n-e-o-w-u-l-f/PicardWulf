"""PicardWulf Picard 3 collision-preflight source tests, no original audio writes."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


ROOT=Path(__file__).resolve().parents[1]
package=types.ModuleType('picardwulf_collision_test')
package.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules[package.__name__]=package
preview=importlib.import_module(package.__name__+'.collision_preview')


def fake_audio(path):
    path=Path(path)
    return {"path":path,"extension":path.suffix.casefold(),
            "size":path.stat().st_size,"identity":("artist","title","album","1","1"),
            "seconds":155.0}


class NativePicardFile:
    def __init__(self,source,target):
        self.filename=str(source)
        self.metadata={'title':'Title'}
        self.target=str(target)
        self.calls=[]
    def make_filename(self, filename, metadata, settings):
        self.calls.append((filename,metadata,settings))
        return self.target


class CollisionPreviewTests(unittest.TestCase):
    def generate(self,root, old=60, incoming=100):
        folder=Path(root)
        src=folder/'incoming.flac'
        dest=folder/'catalogue.flac'
        src.write_bytes(b'I'*incoming)
        dest.write_bytes(b'D'*old)
        return src,dest

    def test_larger_flac_advisory_no_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            before=(src.read_bytes(),dst.read_bytes())
            result=preview.inspect_collision(src,dst,inspect=fake_audio)
            self.assertEqual(result['state'],'WOULD_REPLACE')
            self.assertEqual((src.read_bytes(),dst.read_bytes()),before)

    def test_existing_larger_or_equal_advisory(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp,old=100,incoming=20)
            self.assertEqual(preview.inspect_collision(src,dst,inspect=fake_audio)['state'],
                             'WOULD_KEEP_EXISTING')
            dst.write_bytes(b'D'*20)
            self.assertEqual(preview.inspect_collision(src,dst,inspect=fake_audio)['state'],
                             'WOULD_KEEP_EXISTING')

    def test_different_track_abstains(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            def mismatch(path):
                data=fake_audio(path)
                if Path(path)==dst:
                    data['identity']=('different','song','album','1','2')
                return data
            self.assertEqual(preview.inspect_collision(src,dst,inspect=mismatch)['state'],'REVIEW')

    def test_native_overwrite_warning_even_if_size_prefers_existing(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp,old=100,incoming=20)
            result=preview.inspect_collision(src,dst,native_overwrite=True,inspect=fake_audio)
            self.assertEqual(result['state'],'NATIVE_OVERWRITE_RISK')
            self.assertEqual(result['advice'],'SKIP')

    def test_native_overwrite_warning_for_new_larger_file(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            result=preview.inspect_collision(src,dst,native_overwrite=True,inspect=fake_audio)
            self.assertEqual(result['state'],'NATIVE_OVERWRITE_RISK')
            self.assertEqual(result['advice'],'REPLACE')

    def test_free_destination_is_no_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            dst.unlink()
            self.assertEqual(preview.inspect_collision(src,dst)['state'],'FREE_TARGET')

    def test_same_file_has_no_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            src,_=self.generate(temp)
            self.assertEqual(preview.inspect_collision(src,src)['state'],'SAME_FILE')

    def test_hardlink_is_treated_as_same_file(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            dst.unlink()
            try:
                os.link(src,dst)
            except OSError:
                self.skipTest('Hard links unavailable on test filesystem')
            self.assertEqual(preview.inspect_collision(src,dst)['state'],'SAME_FILE')

    def test_symlink_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            sym=Path(temp)/'link.flac'
            try:
                sym.symlink_to(src)
            except OSError:
                self.skipTest('Symlinks unavailable')
            self.assertEqual(preview.inspect_collision(sym,dst)['state'],'REVIEW')

    def test_mp3_source_is_not_flac_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            mp3=src.with_suffix('.mp3')
            mp3.write_bytes(b'Test'*80)
            self.assertEqual(preview.inspect_collision(mp3,dst)['state'],'REVIEW')

    def test_uses_exact_picard_v3_filename_calculation(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            settings={'rename_files':True,'move_files':True,
                      'move_overwrite_existing_files':False}
            f=NativePicardFile(src,dst)
            rows=preview.capture_native_targets((f,),settings)
            self.assertEqual(rows,((str(src),str(dst),False),))
            self.assertEqual(f.calls,[(str(src),f.metadata,settings)])
            result=preview.analyze_native_targets(rows,inspect=fake_audio)
            self.assertEqual(result[0]['state'],'WOULD_REPLACE')

    def test_never_changes_active_preset_or_override(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            settings={'rename_files':True,'move_files':True,
                      'move_overwrite_existing_files':True,
                      'active_file_naming_script_id':'Preset 3'}
            f=NativePicardFile(src,dst)
            preview.capture_native_targets((f,),settings)
            self.assertEqual(settings['active_file_naming_script_id'],'Preset 3')
            self.assertTrue(settings['move_overwrite_existing_files'])

    def test_disabled_naming_does_not_invoke_private_rename(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            settings={'rename_files':False,'move_files':False,
                      'move_overwrite_existing_files':False}
            f=NativePicardFile(src,dst)
            rows=preview.capture_native_targets((f,),settings)
            self.assertEqual(rows,((str(src),str(src),False),))
            self.assertEqual(f.calls,[])

    def test_missing_settings_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            f=NativePicardFile(src,dst)
            self.assertEqual(preview.capture_native_targets((f,),{}),())

    def test_bounded_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=self.generate(temp)
            settings={'rename_files':True,'move_files':True,
                      'move_overwrite_existing_files':False}
            files=[NativePicardFile(src,dst) for _ in range(50)]
            rows=preview.capture_native_targets(files,settings,limit=20)
            self.assertEqual(len(rows),20)
            self.assertEqual(sum(len(f.calls) for f in files),20)


if __name__=='__main__':
    unittest.main()
