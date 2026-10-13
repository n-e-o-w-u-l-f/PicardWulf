import importlib
import pathlib
import sys
import tempfile
import time
import types
import unittest
import sqlite3
import hashlib

ROOT=pathlib.Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
if 'neowulf_picard_repair' not in sys.modules:
    package=types.ModuleType('neowulf_picard_repair')
    package.__path__=[str(ROOT/'neowulf_picard_repair')]
    sys.modules['neowulf_picard_repair']=package
engine=importlib.import_module('neowulf_picard_repair.universal_engine')

class TestQueue(unittest.TestCase):
    def test_persistent_jobs_resume_and_complete(self):
        class FastTransport:
            def request(self,source,url,params,headers=None,form=None):
                if source=='musicbrainz':return {'recordings':[]}
                if source=='deezer':return {'data':[]}
                if source=='itunes':return {'results':[]}
                self.fail('unconfigured adapter called')
        with tempfile.TemporaryDirectory() as temp:
            p=pathlib.Path(temp)/'queue.sqlite3'
            s=engine.ResultStore(p)
            for i in range(115):
                q={'artist':'Eminem','title':f'Test Track {i}','album':'Album',
                   'isrc':'','recording_mbid':'','duration_ms':0,'albumartist':'Eminem'}
                self.assertTrue(s.enqueue(engine.query_key(q),q))
            self.assertEqual(s.job_count(),115)
            e=engine.UniversalAggregator(store=engine.ResultStore(p),transport=FastTransport(),credentials={})
            try:
                for _ in range(300):
                    if s.job_count()==0:break
                    time.sleep(.025)
                self.assertEqual(s.job_count(),0,'persistent jobs not drained')
                self.assertEqual(len(s.recent(200)),115)
                self.assertEqual(e.status()['failed'],0)
            finally:e.stop()

    def test_schema_upgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            p=pathlib.Path(temp)/'old.sqlite3'
            conn=sqlite3.connect(p)
            conn.execute('CREATE TABLE jobs(k TEXT PRIMARY KEY, queued REAL, query TEXT, force INTEGER)')
            conn.commit();conn.close()
            s=engine.ResultStore(p)
            self.assertEqual(s.job_count(),0)
            self.assertTrue(s.enqueue('abc',{'title':'Foo'},force=True))
            self.assertEqual(s.next_jobs(set())[0][0],'abc')

    def test_failed_job_not_retried_in_loop(self):
        with tempfile.TemporaryDirectory() as temp:
            s=engine.ResultStore(pathlib.Path(temp)/'queue.sqlite3')
            s.enqueue('fail',{'artist':'A','title':'B'})
            s.fail_job('fail')
            self.assertEqual(s.next_jobs(set()),[])
            self.assertEqual(s.job_count(),0)
            self.assertFalse(s.enqueue('fail',{'artist':'A','title':'B'}))
            self.assertEqual(s.next_jobs(set()),[])
            s.enqueue('fail',{'artist':'A','title':'B'},force=True)
            self.assertEqual(s.next_jobs(set())[0][0],'fail')

class TestUpgradeContract(unittest.TestCase):
    def test_original_v2_hashes(self):
        original=ROOT.parent/'NEOWULF-Picard3-Reparatur-v2'/'neowulf_picard_repair'
        for file,digest in {
            '__init__.py':'05e430377c0ec180bf8f9e2890d6798e747c767af3d274f3eee8655c24461241',
            'MANIFEST.toml':'5b4f668da6d9f533d81312cb3fb1ac2536f83d24bc941dbd3972a010810f60c6',
            'repair_logic.py':'f8afa38ca6a176166faefbe73808934b406bcc89d66c0db16839e2cf1dd6eab5',
        }.items():
            if (original / file).is_file():
                self.assertEqual(hashlib.sha256((original / file).read_bytes()).hexdigest(), digest)
            else:
                # Published source checkout is self-contained: validate the exact
                # audited v2 pins even when the separate historical v2 tree is absent.
                installer = (ROOT / 'Install-NEOWULF.ps1').read_text(encoding='utf8')
                self.assertIn(digest.upper(), installer)

    def test_installer_preserves_rollback(self):
        s=(ROOT/'Install-NEOWULF.ps1').read_text(encoding='utf8')
        self.assertIn('Matches-Known-V2',s)
        self.assertIn("'.picardwulf-backup-' + $mode",s)
        self.assertIn('Matches-Known-V3',s)
        self.assertIn('Move-Item -LiteralPath $backup -Destination $target',s)
        self.assertNotIn('picard-cli.exe --yes',s)
    def test_all_modules_staged(self):
        s=(ROOT/'Install-NEOWULF.ps1').read_text(encoding='utf8')
        for f in ('universal_engine.py','universal_adapters.py','credentials.py'):
            self.assertIn(f,s)
            self.assertTrue((ROOT/'neowulf_picard_repair'/f).is_file())

if __name__=='__main__':unittest.main()
