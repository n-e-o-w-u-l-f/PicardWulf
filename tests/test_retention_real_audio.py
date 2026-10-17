"""Disposable real-stream integration: never reads or changes personal music.

Skip when local FLAC encoder, ffmpeg, or Mutagen is not available.
"""
import hashlib
import importlib.util
import math
import shutil
import struct
import subprocess
from pathlib import Path
import tempfile
import unittest
import wave

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    'picardwulf_retention_real_audio',
    ROOT/'neowulf_picard_repair'/'retention_policy.py')
policy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
gold_spec=importlib.util.spec_from_file_location(
    'picardwulf_gold_real_audio',
    ROOT/'neowulf_picard_repair'/'gold_retirement.py')
gold=importlib.util.module_from_spec(gold_spec)
gold_spec.loader.exec_module(gold)


class RealAudioRetentionTests(unittest.TestCase):
    def test_real_flac_decoder_mp3_cleanup_and_atomic_backup(self):
        if not shutil.which('flac') or not shutil.which('ffmpeg'):
            self.skipTest('Disposable real-audio test requires flac and ffmpeg')
        try:
            from mutagen.flac import FLAC
            from mutagen.easyid3 import EasyID3
        except ImportError:
            self.skipTest('Mutagen not installed')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            wav=root/'sample.wav'
            with wave.open(str(wav),'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(44100)
                frames=b''.join(struct.pack('<h',
                    int(2000*math.sin(2*math.pi*440*i/44100))) for i in range(44100*3))
                audio.writeframes(frames)
            flac=root/'Track.flac'
            mp3=root/'Track.mp3'
            subprocess.run(['flac','--silent','-f','-o',str(flac),str(wav)],
                           check=True,capture_output=True)
            subprocess.run(['ffmpeg','-y','-v','error','-i',str(wav),
                            '-q:a','4',str(mp3)],check=True,capture_output=True)
            fields={'artist':'Synthetic Artist','title':'Synthetic Track',
                    'album':'Synthetic Album','discnumber':'1','tracknumber':'2'}
            tags=FLAC(str(flac))
            for key,value in fields.items():tags[key]=value
            tags.save()
            tags=EasyID3(str(mp3))
            for key,value in fields.items():tags[key]=value
            tags.save()
            gold_snapshot=('synthetic-album',((str(flac),tuple(fields.items())),))
            self.assertTrue(gold.verify_gold_files(gold_snapshot))
            wrong_snapshot=('synthetic-album',((str(flac),(('title','Not the stored title'),)),))
            self.assertFalse(gold.verify_gold_files(wrong_snapshot))
            self.assertEqual(policy.decide_mp3_removal(mp3,flac)['action'],'REMOVE')
            backup=root/'backup.mp3'
            shutil.copy2(mp3,backup)
            receipt={'path':str(mp3),'backup':str(backup),
                     'sha256':hashlib.sha256(backup.read_bytes()).hexdigest()}
            self.assertEqual(policy.remove_verified_mp3(mp3,flac,backup_receipt=receipt)
                             ['action'],'REMOVED')
            self.assertFalse(mp3.exists())
            self.assertTrue(flac.exists())
            self.assertTrue(backup.exists())
            old=root/'existing.flac'
            new=root/'incoming.flac'
            shutil.copy2(flac,old)
            shutil.copy2(flac,new)
            bigger=FLAC(str(new))
            bigger['comment']='Synthetic extended metadata '+('X'*65536)
            bigger.save()
            self.assertGreater(new.stat().st_size,old.stat().st_size)
            self.assertEqual(policy.decide_duplicate(old,new)['action'],'REPLACE')
            original=old.read_bytes()
            receipt=policy.replace_smaller_flac(old,new,root/'rollback')
            self.assertEqual(receipt['action'],'REPLACED')
            self.assertEqual(old.read_bytes(),new.read_bytes())
            self.assertEqual(Path(receipt['backup']).read_bytes(),original)



    def test_staged_import_with_real_flac_stream_and_rollback(self):
        if not shutil.which('flac'):
            self.skipTest('Real encoded FLAC test requires flac CLI')
        try:
            from mutagen.flac import FLAC
        except ImportError:
            self.skipTest('Mutagen not installed')
        import importlib
        import sys
        import types
        name='picardwulf_real_staged_import'
        pkg=types.ModuleType(name)
        pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
        sys.modules[name]=pkg
        importer=importlib.import_module(name+'.staged_flac_import')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            staging=root/'staging'
            library=root/'library'
            backup=root/'recovery'
            for path in (staging,library,backup):
                path.mkdir()
            wav=root/'tiny.wav'
            with wave.open(str(wav),'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(22050)
                audio.writeframes(b'\\x00\\x00'*22050)
            incoming=staging/'Synthetic.flac'
            canonical=library/'Synthetic.flac'
            subprocess.run(['flac','--silent','-f','-o',str(incoming),str(wav)],
                           check=True,capture_output=True)
            fields={'artist':'Synthetic Artist','title':'Track',
                    'album':'Release','discnumber':'1','tracknumber':'1'}
            tag=FLAC(str(incoming))
            for field,value in fields.items():
                tag[field]=value
            tag.save()
            shutil.copy2(incoming,canonical)
            bigger=FLAC(str(incoming))
            bigger['comment']='Larger file generated with metadata '+('Q'*65536)
            bigger.save()
            self.assertGreater(incoming.stat().st_size,canonical.stat().st_size)
            opts={'staging_root':staging,'library_root':library,'recovery_root':backup}
            preview=importer.import_staged_flac(incoming,canonical,**opts)
            self.assertEqual(preview['action'],'WOULD_REPLACE')
            original=canonical.read_bytes()
            # Mutagen editing of a *real* valid FLAC changes audio-file bytes
            # between the user's read-only review and actual confirmation.
            edited=FLAC(str(incoming))
            edited['comment']='Changed after preview '+('Y'*65536)
            edited.save()
            with self.assertRaises(importer.StagedImportRejected):
                importer.import_staged_flac(
                    incoming,canonical,apply=True,expected_preview=preview,**opts)
            self.assertEqual(canonical.read_bytes(),original)
            self.assertEqual(list(backup.iterdir()),[])
            preview=importer.import_staged_flac(incoming,canonical,**opts)
            result=importer.import_staged_flac(
                incoming,canonical,apply=True,expected_preview=preview,**opts)
            self.assertEqual(result['action'],'REPLACED')
            self.assertEqual(canonical.read_bytes(),incoming.read_bytes())
            self.assertEqual(Path(result['backup']).read_bytes(),original)
            self.assertTrue(incoming.exists())
            self.assertEqual(importer.import_staged_flac(incoming,canonical,apply=True,**opts)
                             ['action'],'SKIPPED')
            other=library/'New Track.flac'
            created=importer.import_staged_flac(incoming,other,apply=True,**opts)
            self.assertEqual(created['action'],'CREATED')
            self.assertEqual(other.read_bytes(),incoming.read_bytes())
            self.assertTrue(incoming.exists())

if __name__=='__main__':
    unittest.main()
