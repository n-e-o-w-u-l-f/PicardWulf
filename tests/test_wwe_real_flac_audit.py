"""Genuine FLAC tags proving read-only WWE inventory across actual codec files."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

from mutagen.flac import FLAC

ROOT = Path(__file__).resolve().parents[1]
mod_name="wwe_real_audio_audit_tests"
spec=importlib.util.spec_from_file_location(mod_name,ROOT/"tools"/"audit_wwe_music.py")
audit=importlib.util.module_from_spec(spec)
sys.modules[mod_name]=audit
spec.loader.exec_module(audit)


class WweRealFlacInventory(unittest.TestCase):
    def test_discovers_misrouted_original_flac_using_real_embedded_tags(self):
        if not shutil.which("flac"):
            self.skipTest("External FLAC encoder not installed")
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/"library"
            folder=lib/"Various Artists"/"Unrecognized samplers"
            folder.mkdir(parents=True)
            wav=Path(tmp)/"synthetic.wav"
            with wave.open(str(wav),"wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(22050)
                stream.writeframes(b"\x00\x00"*22050)
            audio_path=folder/"07 - My Time.flac"
            subprocess.run(["flac","-f","--silent","-o",str(audio_path),str(wav)],
                           check=True,capture_output=True)
            tags=FLAC(str(audio_path))
            tags["album"]="WWF The Music, Volume 2"
            tags["artist"]="Jim Johnston"
            tags["albumartist"]="Various Artists"
            tags["date"]="1997"
            tags.save()
            old_bytes=audio_path.read_bytes()
            report=audit.scan_library([lib])
            entry=report["by_volume"]["2"]
            self.assertEqual(report["audio_files_scanned"],1)
            self.assertEqual(entry["misplaced_candidates"],1)
            self.assertEqual(entry["audio_files"],1)
            self.assertEqual(entry["examples"][0]["expected_album_folder"],
                str(lib/"Various Artists"/"WWE The Music"/"1997 - WWE The Music Volume 2"))
            self.assertEqual(report["status"],"READ_ONLY_NO_MOVES")
            self.assertEqual(audio_path.read_bytes(),old_bytes)


    def test_corrupt_fake_flac_reports_incomplete_instead_of_missing_albums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"music"
            root.mkdir()
            path=root/"broken.flac"
            data=b"not a valid encoded FLAC stream"
            path.write_bytes(data)
            report=audit.scan_library([root])
            self.assertEqual(report["status"],"READ_ONLY_INCOMPLETE")
            self.assertEqual(report["unreadable_metadata"],1)
            self.assertEqual(report["unreadable_examples"],[str(path)])
            self.assertEqual(report["audio_without_album_tag"],0)
            self.assertTrue(report["volume_absence_is_not_proven"])
            self.assertEqual(path.read_bytes(),data)


if __name__=="__main__":
    unittest.main()
