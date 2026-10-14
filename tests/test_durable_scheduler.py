"""S1 regressions: no network or personal media used."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile
import threading
import time
import types
import subprocess
import json
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parents[1]
pkg = 'picardwulf_s1_test'
module = types.ModuleType(pkg)
module.__path__ = [str(ROOT / 'neowulf_picard_repair')]
sys.modules[pkg] = module
engine = importlib.import_module(pkg + '.universal_engine')


def wait_for(check, timeout=10):
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() >= deadline:
            raise AssertionError('background operation did not finish')
        time.sleep(.01)


class DurableSchedulerTests(unittest.TestCase):
    def test_large_existing_backlog_warns_without_unrequested_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(pathlib.Path(directory)/'queue.db')
            store.enqueue_many([(str(i), {'artist':'Synthetic','title':str(i)}, False)
                                for i in range(2001)])
            adapters=importlib.import_module('picardwulf_s1_test.universal_adapters')
            class NoNetwork:
                def request(self,*a,**k):
                    raise AssertionError('all sources disabled')
            runner=engine.UniversalAggregator(store=store,credentials={},paused=False,
                      transport=NoNetwork(),provider_options={'disabled':list(adapters.SOURCES)})
            try:
                self.assertTrue(runner.wait_ready())
                self.assertTrue(runner.status()['large_backlog_detected'])
                self.assertFalse(runner.status()['paused'])
            finally:
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))

    def test_manually_paused_large_backlog_stays_paused(self):
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(pathlib.Path(directory)/'queue.db')
            store.enqueue_many([(str(i), {'artist':'Synthetic','title':str(i)}, False)
                                for i in range(2001)])
            runner=engine.UniversalAggregator(store=store,credentials={},paused=True)
            try:
                self.assertTrue(runner.wait_ready())
                self.assertTrue(runner.status()['large_backlog_detected'])
                self.assertTrue(runner.status()['paused'])
                self.assertEqual(runner.status()['pending'],0)
            finally:
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))

    def test_real_sqlite_full_never_acknowledges_uncommitted_rows(self):
        class LimitedStore(engine.ResultStore):
            def open_writer(self):
                super().open_writer()
                count=self._writer_connection.execute('PRAGMA page_count').fetchone()[0]
                self._writer_connection.execute(f'PRAGMA max_page_count={count}')
            def release_limit(self):
                self._writer_connection.execute('PRAGMA max_page_count=1000000')
        with tempfile.TemporaryDirectory() as directory:
            store=LimitedStore(pathlib.Path(directory)/'queue.db')
            runner=engine.UniversalAggregator(store=store,credentials={},paused=True,capacity=8,batch_size=4)
            self.assertTrue(runner.wait_ready())
            accepted=0
            try:
                deadline=time.monotonic()+10
                while not runner.status()['db_error']:
                    if runner.schedule_async({'artist':'Synthetic'*20,'title':str(accepted)+'x'*200,
                                              'album':'Album'*40}):accepted+=1
                    else:time.sleep(.005)
                    self.assertLess(time.monotonic(),deadline)
                self.assertGreater(runner.status()['staging'],0)
                self.assertLess(runner.status()['committed'],accepted)
                self.assertLessEqual(runner.status()['staging'],8)
                runner.store.release_limit()
            finally:
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))
            self.assertEqual(store.job_count(),accepted)

    def test_failed_startup_with_no_staged_work_does_not_poison_next_enable(self):
        with tempfile.TemporaryDirectory() as directory:
            store=engine.ResultStore(pathlib.Path(directory)/'queue.db')
            with patch.object(store,'begin_session',side_effect=sqlite3.OperationalError('busy')):
                previous=engine.UniversalAggregator(store=store,credentials={},paused=True)
                self.assertFalse(previous.wait_ready())
                self.assertTrue(previous.wait_stopped(5))
                self.assertFalse(previous.schedule_async({'artist':'A','title':'late'}))
            fresh=engine.UniversalAggregator(store=store,credentials={},paused=True,predecessor=previous)
            try:self.assertTrue(fresh.wait_ready())
            finally:
                fresh.stop()
                self.assertTrue(fresh.wait_stopped())

    def test_real_busy_keeps_staging_and_clean_disable_enable_waits_for_flush(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'queue.db'
            store=engine.ResultStore(path)
            runner=engine.UniversalAggregator(store=store,credentials={},paused=True)
            self.assertTrue(runner.wait_ready())
            locker=sqlite3.connect(path,timeout=.25)
            locker.execute('BEGIN IMMEDIATE')
            try:
                runner.schedule_async({'artist':'A','title':'busy'})
                wait_for(lambda: runner.status()['db_error'])
                self.assertEqual(runner.status()['staging'],1)
                self.assertEqual(runner.status()['committed'],0)
                runner.stop()
                self.assertFalse(runner.wait_stopped(.05))
            finally:
                locker.rollback()
                locker.close()
            fresh=engine.UniversalAggregator(store=store,credentials={},paused=True,predecessor=runner)
            try:
                self.assertTrue(fresh.wait_ready())
                self.assertTrue(runner.wait_stopped(5))
                self.assertEqual(fresh.status()['backlog'],1)
            finally:
                fresh.stop()
                self.assertTrue(fresh.wait_stopped())

    def test_future_schema_and_corrupt_database_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'queue.db'
            db=sqlite3.connect(path)
            db.execute('PRAGMA user_version=99')
            db.close()
            before=path.read_bytes()
            with self.assertRaises(sqlite3.DatabaseError):engine.ResultStore(path)
            self.assertEqual(path.read_bytes(),before)
            path.write_bytes(b'not a SQLite database')
            with self.assertRaises(sqlite3.DatabaseError):engine.ResultStore(path)
            self.assertEqual(path.read_bytes(),b'not a SQLite database')

    def test_39000_identities_survive_abrupt_worker_process_termination(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'queue.db'
            store=engine.ResultStore(path)
            for start in range(0,29000,256):
                store.enqueue_many([(str(i),{'artist':'Old','title':str(i)},False)
                                    for i in range(start,min(29000,start+256))])
            script='''import sys,types,importlib,pathlib,time,json
pkg=types.ModuleType('crash_test');pkg.__path__=[sys.argv[1]];sys.modules['crash_test']=pkg
mod=importlib.import_module('crash_test.universal_engine')
store=mod.ResultStore(pathlib.Path(sys.argv[2]))
runner=mod.UniversalAggregator(store=store,credentials={},paused=True)
for i in range(10000):
    while not runner.schedule_async({'artist':'New','title':str(i)}):time.sleep(.002)
while runner.status()['staging']:time.sleep(.005)
print(json.dumps(runner.status()),flush=True)
time.sleep(120)
'''
            process=subprocess.Popen([sys.executable,'-c',script,str(ROOT/'neowulf_picard_repair'),str(path)],
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                # A background wait prevents an indefinite read on a failed child.
                receipt={}
                reader=threading.Thread(target=lambda: receipt.update(line=process.stdout.readline()),daemon=True)
                reader.start();reader.join(40)
                self.assertFalse(reader.is_alive(),'39k load timed out')
                self.assertTrue(receipt['line'])
                status=json.loads(receipt['line'])
                self.assertEqual(status['committed'],10000)
                self.assertLessEqual(status['staging'],2048)
                process.kill();process.wait(5)
            finally:
                if process.poll() is None:process.kill();process.wait(5)
                process.stdout.close();process.stderr.close()
            recovered=engine.ResultStore(path)
            self.assertEqual(recovered.job_count(),39000)
            with recovered._db() as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')

    def test_capacity_includes_uncommitted_batch_and_error_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            store = engine.ResultStore(pathlib.Path(directory) / 'queue.db')
            blocked = threading.Event()
            release = threading.Event()
            original = store.enqueue_many

            def busy(entries):
                blocked.set()
                release.wait(5)
                raise sqlite3.OperationalError('disk full')

            with patch.object(store, 'enqueue_many', busy):
                runner = engine.UniversalAggregator(store=store, credentials={}, paused=True,
                                                    capacity=8, batch_size=4)
                try:
                    for i in range(8):
                        self.assertTrue(runner.schedule_async({'artist': 'A', 'title': str(i)}))
                    self.assertTrue(blocked.wait(2))
                    self.assertFalse(runner.schedule_async({'artist': 'A', 'title': 'overflow'}))
                    self.assertEqual(runner.status()['staging'], 8)
                    self.assertEqual(runner.status()['committed'], 0)
                    release.set()
                    wait_for(lambda: runner.status()['db_error'])
                    self.assertTrue(runner.status()['paused'])
                finally:
                    release.set()
                    store.enqueue_many = original
                    runner.resume()
                    runner.stop()
                    self.assertTrue(runner.wait_stopped(10))
                self.assertEqual(store.job_count(), 8)

    def test_gui_entry_points_do_not_connect_even_with_locked_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'queue.db'
            store = engine.ResultStore(path)
            owner = threading.get_ident()
            real_connect = sqlite3.connect
            def connect(*args, **kwargs):
                self.assertNotEqual(threading.get_ident(), owner, 'SQLite called on GUI')
                return real_connect(*args, **kwargs)
            with patch.object(engine.sqlite3, 'connect', connect):
                runner = engine.UniversalAggregator(store=store, credentials={}, paused=True)
                runner.schedule_async({'artist': 'A', 'title': 'B'})
                runner.status()
                runner.pause()
                runner.resume()
                runner.request_results(['missing'])
                runner.request_recent()
                runner.stop()
                self.assertTrue(runner.wait_stopped(10))

    def test_revision_prevents_obsolete_completion_and_new_jobs_are_fair(self):
        with tempfile.TemporaryDirectory() as directory:
            store = engine.ResultStore(pathlib.Path(directory) / 'queue.db')
            store.enqueue_many([(str(i), {'artist': 'A', 'title': str(i)}, False)
                                for i in range(100)])
            store.begin_session()
            store.enqueue_many([('new', {'artist': 'A', 'title': 'new'}, False)])
            jobs = store.claim_jobs(2)
            self.assertIn('new', [row[0] for row in jobs])
            key, q, force, revision = jobs[0]
            store.enqueue_many([(key, q, True)])
            self.assertFalse(store.finish_job(key, revision, q, {'obsolete': True}))
            self.assertIsNone(store.get_result(key))
            self.assertEqual(store.state_counts()['queued'], 100)

    def test_migration_backup_integrity_and_running_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'queue.db'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE jobs(k TEXT PRIMARY KEY, queued REAL, query TEXT, force INTEGER)')
            db.execute("INSERT INTO jobs VALUES('old', 0, '{}', 0)")
            db.commit()
            db.close()
            store = engine.ResultStore(path)
            self.assertTrue(store.migration_backup.is_file())
            job = store.claim_jobs(1)[0]
            store.checkpoint(job[0], job[3], 'musicbrainz', [], 'ok')
            store.begin_session()
            self.assertEqual(store.state_counts()['running'], 0)
            self.assertEqual(store.provider_progress('old', job[3])['musicbrainz']['status'], 'ok')
            db = sqlite3.connect(store.migration_backup)
            try:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
