"""Dry-run evidence: scattered artist compilations remain intact and auditable."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "_pw_artist_audit_test",ROOT/"tools"/"audit_artist_compilations.py")
AUDIT=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=AUDIT
SPEC.loader.exec_module(AUDIT)


class ArtistLibraryAuditTests(unittest.TestCase):
    def test_frank_zander_three_false_groups_collapse_only_in_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            tags={}
            for index in range(1,4):
                file=root/f"Various Artists/Compilation {index}"/f"0{index}.flac"
                file.parent.mkdir(parents=True)
                file.write_bytes(b"unchanged audio data " + bytes([index]))
                tags[file]={
                    "album":"Meine coolsten Hits",
                    "albumartist":"Various Artists",
                    "artist":"Featured performer",
                    "date":"2022","discnumber":str((index%2)+1),
                    "totaldiscs":"2",
                    "musicbrainz_albumid":f"different-release-{index}"}
            saved={p:p.read_bytes() for p in tags}
            result=AUDIT.audit_library([root],read=lambda p:tags[p])
            self.assertEqual(result["status"],"READ_ONLY_NO_MOVES")
            self.assertEqual(result["audio_scanned"],3)
            self.assertEqual(len(result["groups"]),1)
            item=result["groups"][0]
            self.assertEqual(item["target"],"Frank Zander/2022 - Meine coolsten Hits")
            self.assertEqual(item["tracks"],3)
            self.assertEqual(len(item["observed_directories"]),3)
            self.assertTrue(item["multiple_picard_release_ids"])
            self.assertTrue(item["split_across_directories"])
            self.assertFalse(item["automatic_move_allowed"])
            self.assertEqual({p:p.read_bytes() for p in saved},saved)

    def test_aggro_va_review_not_misrepresented_as_die_sekte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            file=root/"Aggro Ansage 1.flac"
            file.write_bytes(b"no mutation")
            result=AUDIT.audit_library([root],read=lambda p:{
                "album":"Aggro Ansage Nr. 1","albumartist":"Various Artists",
                "date":"2002"})
            self.assertEqual(len(result["groups"]),1)
            item=result["groups"][0]
            self.assertTrue(item["review"])
            self.assertTrue(item["target"].startswith("REVIEW_ONLY:"))
            self.assertNotIn("Die Sekte",item["target"])
            self.assertEqual(file.read_bytes(),b"no mutation")

    def test_wwe_multidisc_groups_together_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data={}
            for disc in range(1,4):
                f=root/f"Old WWE Disc {disc}"/f"intro{disc}.flac"
                f.parent.mkdir()
                f.write_bytes(b"fake codec " + bytes([disc]))
                data[f]={"album":f"WWE Anthology CD {disc}",
                         "albumartist":"Various Artists",
                         "date":"2002","discnumber":str(disc)}
            out=AUDIT.audit_library([root],read=lambda p:data[p])
            self.assertEqual(len(out["groups"]),1)
            item=out["groups"][0]
            self.assertEqual(item["target"],
                "![-1.2-VARiOUS-ARTiSTz-]!/WWE Anthology/2002 - WWE Anthology")
            self.assertEqual(item["disc_numbers"],["1","2","3"])
            self.assertEqual(item["tracks"],3)

    def test_corrupt_tag_does_not_claim_full_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            f=root/"corrupt.flac";f.write_bytes(b"not flac")
            out=AUDIT.audit_library([root],read=lambda p:None)
            self.assertEqual(out["status"],"READ_ONLY_INCOMPLETE")
            self.assertEqual(out["audio_scanned"],1)
            self.assertEqual(out["unreadable_metadata"],1)
            self.assertEqual(f.read_bytes(),b"not flac")

    def test_reject_overlap_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            child=root/"music";child.mkdir()
            with self.assertRaises(ValueError):
                AUDIT.audit_library([root,child],read=lambda p:{})


if __name__=="__main__":
    unittest.main()
