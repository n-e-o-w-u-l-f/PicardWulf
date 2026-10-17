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


if __name__=='__main__':
    unittest.main()
