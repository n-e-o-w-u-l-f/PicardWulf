"""S4 synthetic lifecycle and real byte-for-byte restore tests.

No Picard process, real music tracks, network account or paid services.
"""
import hashlib
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parents[1]
pkg=types.ModuleType('s4_save_test')
pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules[pkg.__name__]=pkg
tracking=importlib.import_module(pkg.__name__+'.save_tracking')
workflow=importlib.import_module(pkg.__name__+'.native_workflow')

def wait_state(tracker, desired, deadline=5):
    until=time.monotonic()+deadline
    while time.monotonic()<until:
        state=tracker.status()
        if state['recent'] and state['recent'][-1]['state']==desired:
            return state['recent'][-1]
        time.sleep(.01)
    raise AssertionError((desired,tracker.status()))

class FakeFile:
    def __init__(self,path):
        self.filename=str(path)

class FakeAudio:
    def __init__(self,tags):
        self.tags=tags


class SaveTrackingTests(unittest.TestCase):
    def receipt(self,root):
        source=Path(root)/'original.flac'
        source.write_bytes(b'disposable-not-real-audio'*100)
        with patch.dict(os.environ,{'LOCALAPPDATA':str(root)}):
            rec=workflow.backup_envelope(str(source))
        return source,rec

    def test_pre_save_worker_accepts_only_verified_unchanged_source(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            self.assertTrue(tracking.verify_pre_save_identity(rec,str(src)))

    def test_pre_save_rejects_same_size_and_same_mtime_with_changed_content(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            original=src.read_bytes()
            stamp=src.stat()
            src.write_bytes(b'X'+original[1:])
            os.utime(src,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            self.assertEqual(src.stat().st_size,rec['size'])
            self.assertEqual(src.stat().st_mtime_ns,rec['mtime_ns'])
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.verify_pre_save_identity(rec,str(src))
            self.assertEqual(Path(rec['backup']).read_bytes(),original)

    def test_pre_save_rejects_swapped_inode_even_if_content_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            old=src.with_suffix('.old')
            src.rename(old)
            src.write_bytes(old.read_bytes())
            os.utime(src,ns=(old.stat().st_atime_ns,rec['mtime_ns']))
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.verify_pre_save_identity(rec,str(src))

    def test_pre_save_rejects_corrupted_backup_without_touching_original(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            pristine=src.read_bytes()
            Path(rec['backup']).write_bytes(b'broken')
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.verify_pre_save_identity(rec,str(src))
            self.assertEqual(src.read_bytes(),pristine)

    def test_pre_save_rejects_unverified_identity_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            unverified=dict(rec)
            unverified.pop('inode')
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.verify_pre_save_identity(unverified,str(src))

    def test_backup_produces_real_sha_and_full_original_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            self.assertTrue(tracking.check_backup_receipt(rec,str(src)))
            self.assertEqual(tracking._sha256(rec['backup']),rec['sha256'])
            self.assertEqual(Path(rec['backup']).read_bytes(),src.read_bytes())
            self.assertEqual(src.stat().st_size,rec['size'])
            self.assertGreaterEqual(rec['mtime_ns'],0)

    def test_receipt_for_different_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.check_backup_receipt(rec,str(src)+'2')

    def test_no_post_save_event_is_not_successful(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            tr=tracking.SaveTracker()
            try:
                tr.register(FakeFile(src),rec,{'title':'New'})
                # Weak references of temporary Python objects may go dead,
                # but registration must not imply a successful save.
                self.assertEqual(tr.status()['pending'],1)
                self.assertFalse(any(x['state']=='VERIFIED' for x in tr.status()['recent']))
            finally:tr.close()

    def test_post_save_and_real_background_readback_can_be_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            f=FakeFile(src)
            tr=tracking.SaveTracker()
            mock=types.ModuleType('mutagen')
            mock.File=lambda *a,**k:FakeAudio({'title':['New title'],'artist':['Synthetic'],
                                              'album':['Album'], 'tracknumber':['3/12']})
            try:
                tr.register(f,rec,{'title':'New title','artist':'Synthetic',
                                   'album':'Album','tracknumber':'3'})
                self.assertEqual(tr.status()['pending'],1)
                with patch.dict(sys.modules,{'mutagen':mock}):
                    self.assertTrue(tr.post_save(f))
                    result=wait_state(tr,'VERIFIED')
                self.assertEqual(result['verified_fields'],4)
                self.assertEqual(tr.status()['pending'],0)
            finally:tr.close()

    def test_wrong_tags_report_mismatch_and_keep_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            f=FakeFile(src);tr=tracking.SaveTracker()
            mock=types.ModuleType('mutagen')
            mock.File=lambda *a,**k:FakeAudio({'title':['Another title'],'artist':['Synthetic']})
            try:
                tr.register(f,rec,{'title':'Correct title','artist':'Synthetic'})
                with patch.dict(sys.modules,{'mutagen':mock}):
                    self.assertTrue(tr.post_save(f))
                    result=wait_state(tr,'MISMATCH')
                self.assertEqual(result['fields'],['title'])
                self.assertTrue(Path(rec['backup']).exists())
            finally:tr.close()

    def test_inaccessible_tag_is_unverified_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            f=FakeFile(src);tr=tracking.SaveTracker()
            mock=types.ModuleType('mutagen')
            mock.File=lambda *a,**k:FakeAudio({'artist':['Synthetic']})
            try:
                tr.register(f,rec,{'title':'Missing field','artist':'Synthetic'})
                with patch.dict(sys.modules,{'mutagen':mock}):
                    self.assertTrue(tr.post_save(f))
                    self.assertEqual(wait_state(tr,'UNVERIFIED')['reason'],
                                     'tags_not_exposed_by_format')
            finally:tr.close()

    def test_aborted_file_save_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            f=FakeFile(src);tr=tracking.SaveTracker()
            try:
                token=tr.register(f,rec,{'title':'Candidate'})
                tr.abort(f,token)
                self.assertEqual(tr.status()['pending'],0)
                self.assertEqual(tr.status()['recent'][-1]['state'],'START_FAILED')
                self.assertFalse(tr.post_save(f))
            finally:tr.close()

    def test_pending_save_times_out_as_unknown_without_deleting_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            f=FakeFile(src);tr=tracking.SaveTracker(save_timeout=-1)
            try:
                tr.register(f,rec,{'title':'Candidate'})
                self.assertEqual(tr.status()['pending'],0)
                self.assertEqual(tr.status()['recent'][-1]['state'],'UNKNOWN_TIMEOUT')
                self.assertTrue(Path(rec['backup']).exists())
            finally:tr.close()

    def test_verified_restore_only_creates_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            dest=Path(directory)/'restored-copy.flac'
            output=tracking.restore_backup_copy(rec,dest)
            self.assertEqual(output['state'],'RESTORED_COPY')
            self.assertEqual(dest.read_bytes(),src.read_bytes())
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.restore_backup_copy(rec,dest)
            self.assertEqual(dest.read_bytes(),src.read_bytes())
            self.assertTrue(Path(rec['backup']).exists())

    def test_modified_backup_cannot_be_restored_or_reported_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            Path(rec['backup']).write_bytes(b'corrupted')
            destination=Path(directory)/'recovered.flac'
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.restore_backup_copy(rec,destination)
            self.assertFalse(destination.exists())
            response=tracking.verify_saved_tags(str(src),{'title':'Anything'},rec)
            self.assertEqual(response['state'],'BACKUP_INVALID')

    def test_backup_manifest_survives_process_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            manifest=Path(rec['manifest'])
            self.assertTrue(manifest.is_file())
            reloaded=tracking.load_backup_manifest(manifest)
            self.assertEqual(reloaded['sha256'],rec['sha256'])
            self.assertEqual(reloaded['path'],str(src))
            destination=Path(directory)/'from-manifest.flac'
            restored=tracking.restore_from_manifest(manifest,destination)
            self.assertEqual(restored['state'],'RESTORED_COPY')
            self.assertEqual(destination.read_bytes(),src.read_bytes())

    def test_tampered_manifest_cannot_select_different_backup_path(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            manifest=Path(rec['manifest'])
            fields=json.loads(manifest.read_text())
            fields['backup']=str(src)
            manifest.write_text(json.dumps(fields))
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.load_backup_manifest(manifest)

    def test_async_restore_queue_reports_only_real_copy_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            target=Path(directory)/'recovered-via-worker.flac'
            tr=tracking.SaveTracker()
            try:
                self.assertTrue(tr.request_restore(rec['manifest'],target))
                completed=wait_state(tr,'RESTORED_COPY')
                self.assertEqual(completed['path'],str(target))
                self.assertEqual(target.read_bytes(),src.read_bytes())
                self.assertEqual(tr.status()['restoring'],0)
            finally:tr.close()

    def test_async_restore_rejects_existing_target_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            before=src.read_bytes()
            tr=tracking.SaveTracker()
            try:
                tr.request_restore(rec['manifest'],str(src))
                self.assertEqual(wait_state(tr,'RESTORE_REJECTED')['state'],'RESTORE_REJECTED')
                self.assertEqual(src.read_bytes(),before)
            finally:tr.close()

    def test_post_save_renamed_target_is_read_from_actual_picard_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            destination=Path(directory)/'renamed-output.flac'
            destination.write_bytes(src.read_bytes())
            f=FakeFile(src)
            tr=tracking.SaveTracker()
            mock=types.ModuleType('mutagen')
            observed=[]
            def reader(path,easy=True):
                observed.append(path)
                return FakeAudio({'title':['Renamed']})
            mock.File=reader
            try:
                tr.register(f,rec,{'title':'Renamed'})
                f.filename=str(destination)
                with patch.dict(sys.modules,{'mutagen':mock}):
                    tr.post_save(f)
                    self.assertEqual(wait_state(tr,'VERIFIED')['verified_fields'],1)
                self.assertEqual(observed,[str(destination)])
            finally:tr.close()

    def test_no_overwrite_even_if_destination_is_original(self):
        with tempfile.TemporaryDirectory() as directory:
            src,rec=self.receipt(directory)
            before=src.read_bytes()
            with self.assertRaises(workflow.UnsafeCandidate):
                tracking.restore_backup_copy(rec,src)
            self.assertEqual(src.read_bytes(),before)

if __name__=='__main__':unittest.main()
