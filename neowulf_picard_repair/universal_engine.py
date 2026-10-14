"""Threaded multi-source metadata aggregation for PicardWulf v1.0.

Network I/O stays off the Qt thread. Separate explicitly confirmed user
actions can link verified MusicBrainz releases and write backed-up tags.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import unicodedata
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, closing
from concurrent.futures import Future
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .universal_adapters import SOURCES, ADAPTERS, env_credentials, one
from .credentials import load as load_credentials

TTL = 72 * 3600
MAX_BODY = 900_000
_ALLOWED = {
    'musicbrainz': ('musicbrainz.org','/ws/2/recording/'),
    'musicbrainz_lookup': ('musicbrainz.org','/ws/2/recording/'),
    'deezer': ('api.deezer.com','/search'),
    'itunes': ('itunes.apple.com','/search'),
    'spotify_auth': ('accounts.spotify.com','/api/token'),
    'spotify': ('api.spotify.com','/v1/search'),
    'soundcloud': ('api.soundcloud.com','/tracks'),
    'lastfm': ('ws.audioscrobbler.com','/2.0/'),
}
MIN_DELAY = {'musicbrainz':1.15,'musicbrainz_lookup':1.15,'deezer':1.4,'itunes':3.2,'spotify_auth':1.,
             'spotify':1.0,'soundcloud':1.1,'lastfm':1.1}

def norm(text):
    text = unicodedata.normalize('NFKD', one(text)).casefold()
    return ' '.join(re.findall(r'\w+', ''.join(x for x in text if not unicodedata.combining(x))))


def similarity(a,b):
    a,b=norm(a),norm(b)
    return SequenceMatcher(a=a,b=b).ratio() if a and b else 0.0


def clean_track(metadata):
    g = metadata.get if hasattr(metadata,'get') else lambda k,d='':d
    title = one(g('title'))
    artist = one(g('artist')) or one(g('albumartist'))
    if not title or not artist or norm(artist) in ('various artists','apple music','spotify','deezer'):
        return None
    def dura():
        for k in ('length','~length','duration','_length'):
            v=one(g(k))
            try:
                if v:
                    n=float(v)
                    if 1 < n < 20000000: return int(n)
            except ValueError:pass
        return 0
    return {'title':title[:220], 'artist':artist[:220], 'album':one(g('album'))[:220],
            'albumartist':one(g('albumartist'))[:220], 'isrc':one(g('isrc')).upper(),
            'recording_mbid':one(g('musicbrainz_recordingid')).lower(),
            'duration_ms':dura(), 'inferred_filename':bool(one(g('inferred_filename')))}


def query_key(q):
    s='picardwulf-crosssource-v1|'+ '|'.join(norm(q.get(k,'')) for k in ('title','artist','album','isrc','recording_mbid'))
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def score(q,c):
    # Reject wrong artist, wrong track, conflicting exact identifiers; don't
    # mistake compilation classification or provenance for album-artist credit.
    if not c.get('title') or not c.get('artist'):return (0.,'missing required fields')
    ta,ar=similarity(q['title'],c['title']),similarity(q['artist'],c['artist'])
    if ta < .72:return (0.,'different title')
    if ar < .73:return (0.,'different artist')
    for k in ('isrc','recording_mbid'):
        if q.get(k) and c.get(k) and one(q[k]).casefold()!=one(c[k]).casefold():
            return (0.,f'conflicting {k}')
    if norm(c.get('albumartist'))=='various artists' and q.get('albumartist') and norm(q['albumartist']) != 'various artists':
        # Reject external release VA in favour of the source album artist;
        # avoid corrupting personal/artist compilations.
        return (0.,'VA albumartist conflict')
    v=.44*ta + .40*ar
    if q.get('album') and c.get('album'):
        v += .09*similarity(q['album'],c['album'])
    elif not q.get('album'):v+=.04
    duration_q=int(q.get('duration_ms') or 0)
    duration_c=int(c.get('duration_ms') or 0)
    if duration_q and duration_c:
        diff=abs(duration_q-duration_c)
        if diff>25000:return (0.,'duration mismatch >25s')
        v += .05 * max(0.,1.-diff/15000)
    if q.get('isrc') and c.get('isrc'):v+=.08
    if q.get('recording_mbid') and c.get('recording_mbid'):v+=.08
    if q.get('inferred_filename'):v=max(0.,v-.06)
    return (round(min(1.,v),4),'compatible')


def aggregate(q, results):
    """Rank releases across ALL sources without granting MusicBrainz priority."""
    from .auto_selection import rank_candidates, decide_auto

    rows = rank_candidates(q, results)
    decision = decide_auto(q, rows)
    if not any(x['score'] >= .84 for x in rows):
        verdict = 'no_safe_match'
    elif decision['state'] == 'ready':
        verdict = 'review_high_confidence'
    else:
        verdict = 'review'
    return {'verdict': verdict, 'candidates': rows[:40], 'auto': decision}


class HTTPClient:
    def __init__(self):
        self._lock=threading.Lock()
        self._last={}
        self._cooldown={}

    def request(self,source,url,params,headers=None,form=None):
        host,path=_ALLOWED[source]
        parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.hostname!=host:
            raise ValueError('provider endpoint not allowed')
        if source=='musicbrainz_lookup':
            if not re.fullmatch(r'/ws/2/recording/[0-9a-fA-F-]{36}',parsed.path):
                raise ValueError('provider lookup endpoint not allowed')
        elif parsed.path!=path:
            raise ValueError('provider endpoint not allowed')
        # Backoff per provider; bounded work; no repeated 429 retries.
        rate_bucket = 'musicbrainz' if source == 'musicbrainz_lookup' else source
        with self._lock:
            now=time.monotonic()
            start=max(now,self._last.get(rate_bucket,0)+MIN_DELAY[source],self._cooldown.get(rate_bucket,0))
            self._last[rate_bucket]=start
        wait=max(0,start-time.monotonic())
        if wait > 8:raise ProviderError('rate_limit_cooldown')
        if wait:time.sleep(wait)
        wire=url+'?'+urlencode(params) if params else url
        body=urlencode(form).encode('utf8') if form is not None else None
        h={'User-Agent':'PicardWulf/1.0 (https://github.com/n-e-o-w-u-l-f/PicardWulf)',
           'Accept':'application/json'}
        if headers:h.update(headers)
        req=Request(wire, data=body,headers=h,method='POST' if form is not None else 'GET')
        try:
            with urlopen(req,timeout=9) as resp:
                if int(resp.status)!=200:raise ValueError('unexpected status')
                data=resp.read(MAX_BODY+1)
                if len(data)>MAX_BODY:raise ValueError('response too large')
                result=json.loads(data.decode('utf-8'))
                if isinstance(result,dict) and result.get('error'):
                    raise ProviderError('service_rejected')
                return result
        except HTTPError as exc:
            if exc.code in (429,503):
                try:delay=max(8,min(int(exc.headers.get('Retry-After','45')),180))
                except ValueError:delay=45
                with self._lock:self._cooldown[rate_bucket]=time.monotonic()+delay
            raise ProviderError(f'HTTP_{exc.code}') from None
        except (URLError,OSError,TimeoutError) as exc:
            raise ProviderError(type(exc).__name__) from None
        except (ValueError, UnicodeError) as exc:
            raise ProviderError('response_invalid') from None


class ProviderError(Exception): pass


class ResultStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()
        self.session = str(time.time_ns())
        self._fair_new = True
        self._writer_connection = None
        self._writer_thread = None
        self.migration_backup = None
        with self._db() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('queue integrity check failed')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise sqlite3.DatabaseError('unsupported future queue schema')
            existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
            if existing and version < 2:
                self.migration_backup = self.path.with_name(self.path.name + '.schema-backup-' + self.session)
                with closing(sqlite3.connect(str(self.migration_backup))) as backup:
                    db.backup(backup)
                    if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise sqlite3.DatabaseError('migration backup integrity check failed')
            # WAL is deliberately opt-in for verified local disk paths.
            # Network mounts/UNC stay on rollback journal.
            if _local_disk(self.path):
                db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS results(k TEXT PRIMARY KEY, updated REAL, query TEXT, payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS responses(k TEXT PRIMARY KEY, updated REAL, payload TEXT)')
            db.execute("CREATE TABLE IF NOT EXISTS jobs(k TEXT PRIMARY KEY, queued REAL, query TEXT, force INTEGER, state TEXT DEFAULT 'queued')")
            cols={row[1] for row in db.execute('PRAGMA table_info(jobs)').fetchall()}
            if 'state' not in cols:
                db.execute("ALTER TABLE jobs ADD COLUMN state TEXT DEFAULT 'queued'")
            for name, definition in (('revision', 'INTEGER DEFAULT 1'),
                                     ('session', "TEXT DEFAULT ''"),
                                     ('attempts', 'INTEGER DEFAULT 0'),
                                     ('retry_at', 'REAL DEFAULT 0')):
                if name not in cols:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')
            db.execute('CREATE INDEX IF NOT EXISTS jobs_dispatch ON jobs(state, session, queued)')
            db.execute('CREATE TABLE IF NOT EXISTS provider_tasks(k TEXT, revision INTEGER, source TEXT, '
                       'status TEXT, payload TEXT, updated REAL, PRIMARY KEY(k,revision,source))')
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def _db(self):
        if self._writer_connection is not None and threading.get_ident() == self._writer_thread:
            with self._writer_connection:
                yield self._writer_connection
            return
        conn=sqlite3.connect(str(self.path),timeout=.25)
        try:
            with conn:yield conn
        finally:conn.close()

    def open_writer(self):
        self._writer_thread = threading.get_ident()
        self._writer_connection = sqlite3.connect(str(self.path), timeout=.25)
        self._writer_connection.execute('PRAGMA synchronous=FULL')

    def close_writer(self):
        if self._writer_connection is not None:
            self._writer_connection.close()
            self._writer_connection = None

    def get_response(self,key):
        with self._lock, self._db() as db:
            row=db.execute('SELECT updated,payload FROM responses WHERE k=?',(key,)).fetchone()
            if row and time.time()-row[0]<TTL:return json.loads(row[1])
        return None

    def save_response(self,key,result):
        with self._lock,self._db() as db:
            db.execute('INSERT OR REPLACE INTO responses VALUES (?,?,?)',
                       (key,time.time(),json.dumps(result,ensure_ascii=False)))
            db.execute('DELETE FROM responses WHERE updated<?',(time.time()-TTL*3,))

    def get_result(self,key):
        with self._lock,self._db() as db:
            row=db.execute('SELECT updated,query,payload FROM results WHERE k=?',(key,)).fetchone()
            if row and time.time()-row[0]<TTL:
                return {'updated':row[0],'query':json.loads(row[1]),'payload':json.loads(row[2])}
        return None

    def get_results(self, keys):
        """Read a bounded set of completed jobs with ONE SQLite connection."""
        keys = list(dict.fromkeys(keys))
        if not keys:
            return {}
        if len(keys)>400:
            raise ValueError('bounded batch must not exceed 400 keys')
        slots=','.join('?' for _ in keys)
        with self._lock, self._db() as db:
            rows=db.execute(
                f'SELECT k,updated,query,payload FROM results WHERE k IN ({slots})',
                keys).fetchall()
        now=time.time()
        return {k:{'updated':ts,'query':json.loads(q),'payload':json.loads(p)}
                for k,ts,q,p in rows if now-ts<TTL}

    def enqueue_many(self, entries):
        """Batch staging into one transaction, away from Picard's GUI thread.

        Existing completed results are skipped unless force=True.
        Duplicate queued jobs remain unique by key.
        """
        cutoff=time.time()-TTL
        accepted=0
        with self._lock, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            for key,q,force in entries:
                if not force and db.execute(
                        'SELECT 1 FROM results WHERE k=? AND updated>=?',
                        (key,cutoff)).fetchone():
                    continue
                cur=db.execute(
                    "INSERT OR IGNORE INTO jobs(k,queued,query,force,state,session) VALUES(?,?,?,?,'queued',?)",
                    (key,time.time(),json.dumps(q,ensure_ascii=False),int(bool(force)),self.session))
                if force and cur.rowcount==0:
                    db.execute("UPDATE jobs SET force=1,state='queued',revision=revision+1,query=?,"
                               "session=?,attempts=0,retry_at=0 WHERE k=?",
                               (json.dumps(q,ensure_ascii=False),self.session,key))
                if force:
                    db.execute('DELETE FROM results WHERE k=?', (key,))
                    db.execute('DELETE FROM provider_tasks WHERE k=?', (key,))
                accepted+=int(cur.rowcount>0)
        return accepted

    def save_result(self,key,q,payload):
        with self._lock,self._db() as db:
            db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?,?)',
                       (key,time.time(),json.dumps(q,ensure_ascii=False),
                        json.dumps(payload,ensure_ascii=False)))
            db.execute('DELETE FROM results WHERE updated<?',(time.time()-30*86400,))

    def enqueue(self,key,q,force=False):
        return bool(self.enqueue_many([(key,q,force)]))

    def begin_session(self):
        self.session = str(time.time_ns())
        with self._lock, self._db() as db:
            db.execute("UPDATE jobs SET state='queued' WHERE state='running'")

    def claim_jobs(self, limit=2, exclude=()):
        jobs = []
        exclude=tuple(exclude)
        excluded=(' AND k NOT IN ('+','.join('?' for _ in exclude)+')') if exclude else ''
        with self._lock, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE jobs SET state='queued' WHERE state='retry' AND retry_at<=?", (time.time(),))
            for _ in range(max(0, min(8, limit))):
                # Alternate new imports and historical backlog: neither can starve.
                operator = '=' if self._fair_new else '!='
                row = db.execute(f"SELECT k,query,force,revision FROM jobs WHERE state='queued' "
                                 f"AND session{operator}?{excluded} ORDER BY queued LIMIT 1",
                                 (self.session,*exclude)).fetchone()
                if row is None:
                    row = db.execute("SELECT k,query,force,revision FROM jobs WHERE state='queued' "
                                     +excluded+" ORDER BY queued LIMIT 1", exclude).fetchone()
                if row is None:
                    break
                db.execute("UPDATE jobs SET state='running' WHERE k=?", (row[0],))
                jobs.append((row[0], json.loads(row[1]), bool(row[2]), row[3]))
                self._fair_new = not self._fair_new
        return jobs

    def provider_progress(self, key, revision):
        with self._lock, self._db() as db:
            rows = db.execute('SELECT source,status,payload FROM provider_tasks WHERE k=? AND revision=?',
                              (key, revision)).fetchall()
        return {src: {'status': state, 'payload': json.loads(payload)} for src, state, payload in rows}

    def checkpoint(self, key, revision, source, candidates, status):
        with self._lock, self._db() as db:
            if db.execute("SELECT 1 FROM jobs WHERE k=? AND revision=? AND state='running'",
                          (key, revision)).fetchone() is None:
                return False
            db.execute('INSERT OR REPLACE INTO provider_tasks VALUES(?,?,?,?,?,?)',
                       (key, revision, source, status, json.dumps(candidates), time.time()))
        return True

    def finish_job(self, key, revision, q, payload):
        with self._lock, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE k=? AND revision=? AND state='running'",
                          (key, revision)).fetchone() is None:
                return False
            db.execute('INSERT OR REPLACE INTO results VALUES(?,?,?,?)',
                       (key,time.time(),json.dumps(q),json.dumps(payload)))
            db.execute('DELETE FROM jobs WHERE k=?', (key,))
            db.execute('DELETE FROM provider_tasks WHERE k=?', (key,))
        return True

    def retry_job(self, key, revision):
        with self._lock, self._db() as db:
            db.execute("UPDATE jobs SET state=CASE WHEN attempts>=2 THEN 'failed' ELSE 'retry' END, "
                       "attempts=attempts+1,retry_at=? WHERE k=? AND revision=?",
                       (time.time()+30, key, revision))

    def state_counts(self):
        with self._lock, self._db() as db:
            rows = db.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state').fetchall()
        return dict({'queued':0, 'running':0, 'retry':0, 'failed':0}, **dict(rows))

    def next_jobs(self,exclude,limit=8):
        with self._lock,self._db() as db:
            # The in-memory pending list is small; SQL selection is chronological.
            batch=db.execute("SELECT k,query,force FROM jobs WHERE state='queued' ORDER BY queued ASC LIMIT 100",()).fetchall()
        return [(k,json.loads(q),bool(force)) for k,q,force in batch
                if k not in exclude][:limit]

    def delete_job(self,key):
        with self._lock,self._db() as db:
            db.execute('DELETE FROM jobs WHERE k=?',(key,))

    def fail_job(self,key):
        with self._lock,self._db() as db:
            db.execute("UPDATE jobs SET state='failed' WHERE k=?",(key,))

    def job_count(self):
        with self._lock,self._db() as db:
            return db.execute("SELECT COUNT(*) FROM jobs WHERE state='queued'").fetchone()[0]

    def recent(self,limit=60):
        with self._lock,self._db() as db:
            rows=db.execute('SELECT updated,query,payload FROM results ORDER BY updated DESC LIMIT ?',
                            (max(1,min(200,limit)),)).fetchall()
        return [{'updated':ts,'query':json.loads(q),'payload':json.loads(p)} for ts,q,p in rows]


def _local_disk(path):
    if os.name == 'nt':
        import ctypes
        drive = Path(path).resolve().drive
        return bool(drive and not drive.startswith('\\\\') and
                    ctypes.windll.kernel32.GetDriveTypeW(drive + '\\') == 3)
    try:
        resolved = str(path.resolve())
        mounts = []
        for line in Path('/proc/mounts').read_text().splitlines():
            fields = line.split()
            mount = fields[1].replace('\\040', ' ')
            if resolved == mount or resolved.startswith(mount.rstrip('/') + '/'):
                mounts.append((len(mount), fields[2]))
        return bool(mounts and max(mounts)[1] in ('ext4','ext3','xfs','btrfs','tmpfs','overlay'))
    except (OSError, ValueError):
        return False


def private_cache_path():
    app=os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME')
    if not app:app=str(Path.home()/'.cache')
    return Path(app)/'NEOWULF'/'Picard3'/'metadata-cache.sqlite3'


class UniversalAggregator:
    """GUI methods stage immutable messages; only workers wait for SQLite.

    A False admission is backpressure, not durability. The GUI retains the
    file identity and retries it later. Stop returns immediately; the receipt
    is set only after staging is committed and all writer work has finished.
    """
    def __init__(self, store=None, transport=None, credentials=None, paused=False,
                 capacity=2048, batch_size=256, predecessor=None):
        from .background_io import DatabaseWorker
        self.capacity = max(1, min(2048, int(capacity)))
        self.batch_size = max(1, min(self.capacity, int(batch_size)))
        self.http = transport or HTTPClient()
        self.credentials = dict(credentials or {})
        self._load_credentials = credentials is None
        self._lock = threading.RLock()
        self._ingest_lock = self._lock
        self._ingest = deque()
        self._ingest_seen = set()
        self._requests = deque()
        self._completed = deque()
        self._ingest_event = threading.Event()
        self._stop_receipt = threading.Event()
        self._flush_receipt = threading.Event()
        self._ready = threading.Event()
        self.pending = set()
        self.stopped = False
        self.paused = bool(paused)
        self.auto_paused_backlog = False
        self.failed_count = self.queued_count = self.committed_count = 0
        self._counts = {'queued':0, 'running':0, 'retry':0, 'failed':0}
        self.db_error = ''
        self.backpressure = False
        self._rates = {}
        self._started = time.monotonic()
        self._pace = .1
        self._batch_seconds = None
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='NEOWULF-Metadata')
        path = store.path if store is not None else private_cache_path()
        self.store = DatabaseWorker(lambda: store if store is not None else ResultStore(path), path, predecessor)
        self._ingest_thread = threading.Thread(target=self._ingest_worker,
                                               name='PicardWulf-Scheduler', daemon=True)
        self._ingest_thread.start()

    def schedule(self, raw, force=False):
        # Compatibility for non-GUI callers. Picard hooks only use schedule_async.
        q = clean_track(raw)
        if q is None:
            return False
        if not force and self.store.get_result(query_key(q)) is not None:
            return False
        return self.schedule_async(q, force)

    def schedule_async(self, raw, force=False):
        q = clean_track(raw)
        if q is None:
            return False
        key = query_key(q)
        with self._lock:
            if self.stopped or self._stop_receipt.is_set():
                return False
            if key in self._ingest_seen:
                return not force
            if len(self._ingest_seen) >= self.capacity:
                self.backpressure = True
                return False
            # JSON detaches the envelope from mutable plugin/Qt metadata.
            self._ingest_seen.add(key)
            self._ingest.append((key, json.dumps(q), bool(force)))
        self._ingest_event.set()
        return True

    def request_results(self, keys):
        keys = tuple(dict.fromkeys(keys))
        if len(keys) > 400:
            raise ValueError('result request exceeds 400 keys')
        return self._request('get_results', keys)

    def request_recent(self):
        return self._request('recent', 80)

    def _request(self, method, argument):
        with self._lock:
            if self.stopped or len(self._requests) >= 4:
                return None
            receipt = Future()
            self._requests.append((method, argument, receipt))
        self._ingest_event.set()
        return receipt

    def _database_failure(self, exc):
        with self._lock:
            self.db_error = type(exc).__name__
            self.paused = True

    def _ingest_worker(self):
        try:
            if self._load_credentials:
                self.credentials.update(env_credentials())
                try:
                    self.credentials.update(load_credentials())
                except (OSError, ValueError, RuntimeError):
                    pass
            self.store.begin_session()
            self._counts = self.store.state_counts()
            self.auto_paused_backlog = sum(self._counts.values()) > 2000
            self.paused = self.paused or self.auto_paused_backlog
            self._ready.set()
            while True:
                self._ingest_event.wait(self._pace)
                self._ingest_event.clear()
                try:
                    with self._lock:
                        batch = list(self._ingest)[:self.batch_size]
                    if batch:
                        batch_started=time.monotonic()
                        try:
                            added = self.store.enqueue_many([(k,json.loads(q),f) for k,q,f in batch])
                        except (sqlite3.Error, OSError) as exc:
                            self._database_failure(exc)
                            # Preserve every staged envelope, including in-flight rows.
                            self._ingest_event.wait(.25)
                            continue
                        with self._lock:
                            for k, _, _ in batch:
                                self._ingest.popleft()
                                self._ingest_seen.discard(k)
                            self.committed_count += len(batch)
                            self.queued_count += added
                            self.backpressure = len(self._ingest_seen) >= self.capacity
                            self.db_error = ''
                            elapsed=time.monotonic()-batch_started
                            self._batch_seconds=elapsed if self._batch_seconds is None else (
                                .8*self._batch_seconds+.2*elapsed)
                            # React to measured disk cost, with a bounded pause
                            # between batches; never increase concurrency.
                            self._pace=max(.01,min(.25,2*self._batch_seconds))
                    with self._lock:
                        completed = list(self._completed)
                        self._completed.clear()
                    for key, revision, task in completed:
                        try:
                            try:
                                payload, q = task.result()
                            except Exception:
                                # A worker exception is retryable durable work,
                                # not a result to replay forever in memory.
                                self.store.retry_job(key, revision)
                                self.failed_count += 1
                                with self._lock:self.pending.discard(key)
                                continue
                            if payload is not None:
                                self.store.finish_job(key, revision, q, payload)
                        except (sqlite3.Error, OSError) as exc:
                            self._database_failure(exc)
                            with self._lock:
                                self._completed.append((key, revision, task))
                            continue
                        except Exception:
                            self.store.retry_job(key, revision)
                            self.failed_count += 1
                        with self._lock:
                            self.pending.discard(key)
                    with self._lock:
                        request = self._requests.popleft() if self._requests else None
                    if request:
                        method, argument, receipt = request
                        try:
                            value=getattr(self.store, method)(argument)
                            if method=='get_results':
                                with self._lock:
                                    for k,_,force in self._ingest:
                                        if force:value.pop(k,None)
                            receipt.set_result(value)
                        except Exception as exc:
                            receipt.set_exception(exc)
                            self._database_failure(exc)
                    with self._lock:
                        stopping = self.stopped
                        drained = not self._ingest_seen and not self.pending
                        if stopping and not self._ingest_seen:
                            self._flush_receipt.set()
                    if stopping and drained:
                        break
                    if not stopping and not self.paused:
                        jobs = self.store.claim_jobs(max(0, 2-len(self.pending)), tuple(self.pending))
                        for key, q, force, revision in jobs:
                            with self._lock:
                                self.pending.add(key)
                            task = self.executor.submit(self._work, key, q, force, revision)
                            task.add_done_callback(lambda f,k=key,r=revision: self._complete(k,r,f))
                    self._counts = self.store.state_counts()
                except (sqlite3.Error, OSError) as exc:
                    self._database_failure(exc)
                    self._ingest_event.wait(.25)
        except Exception as exc:
            self._database_failure(exc)
            self._ready.set()
            # Failed startup/lease is never a successful flush acknowledgement.
        finally:
            with self._lock:
                for _, _, receipt in self._requests:
                    receipt.set_exception(RuntimeError('scheduler stopped'))
                self._requests.clear()
            self.executor.shutdown(wait=True, cancel_futures=True)
            self.store.close()
            with self._lock:
                if not self._ingest_seen:self._flush_receipt.set()
            self._stop_receipt.set()

    def _complete(self, key, revision, task):
        with self._lock:
            self._completed.append((key, revision, task))
        self._ingest_event.set()

    def pause(self):
        with self._lock:
            self.paused = True

    def resume(self):
        with self._lock:
            if self.stopped:
                return
            self.paused = False
        self._ingest_event.set()

    def wait_ready(self, timeout=10):
        return self._ready.wait(timeout) and not self.db_error

    def wait_stopped(self, timeout=10):
        return self._stop_receipt.wait(timeout) and self._flush_receipt.is_set()

    def _work(self,key,q,force=False,revision=1):
        source_results={}
        statuses={}
        progress = self.store.provider_progress(key, revision)
        for source in SOURCES:
            if self.stopped:return (None, q)  # preserve queued job for next Picard start
            if source in progress:
                entry = progress[source]
                if entry['status'] != 'running':
                    statuses[source] = entry['status']
                    if entry['payload'] is not None:
                        source_results[source] = entry['payload']
                    continue
            if not self.store.checkpoint(key,revision,source,None,'running'):
                return (None,q)  # canceled/replaced work cannot launch another provider
            adapter=ADAPTERS[source]
            cache_id=hashlib.sha256((source+'|'+key).encode()).hexdigest()
            cached=None if force else self.store.get_response(cache_id)
            if cached is not None:
                source_results[source]=cached
                statuses[source]='cached'
                self.store.checkpoint(key, revision, source, cached, 'cached')
                continue
            try:
                # Keep credentials memory-only; never include in cache keys.
                candidates=adapter(q,self.http.request,self.credentials)
                if candidates is None:
                    statuses[source]='not_configured'
                    self.store.checkpoint(key, revision, source, None, 'not_configured')
                    continue
                if not isinstance(candidates,list):raise ValueError('unexpected candidates')
                source_results[source]=candidates[:18]
                self.store.save_response(cache_id,candidates[:18])
                statuses[source]='ok'
            except ProviderError as e:
                statuses[source]=str(e)
            except Exception as e:
                statuses[source]='error_'+type(e).__name__
            self.store.checkpoint(key, revision, source, source_results.get(source), statuses[source])
            with self._lock:
                self._rates[source] = self._rates.get(source, 0) + 1
        if self.stopped:return (None, q)
        # If the file has no ISRC, streaming catalogues can provide one.
        # Resolve that exact identifier back to MusicBrainz *without treating
        # a Spotify/Deezer album ID as a native Picard release ID*.
        if not source_results.get('musicbrainz') and statuses.get('musicbrainz') in ('ok','cached'):
            for src in ('spotify','deezer'):
                other=next((v for v in source_results.get(src,[])
                            if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{3}[0-9]{7}',v.get('isrc',''))
                            and similarity(q['title'],v.get('title')) > .92
                            and similarity(q['artist'],v.get('artist')) > .92),None)
                if other:
                    try:
                        q2={**q,'isrc':other['isrc']}
                        candidates=ADAPTERS['musicbrainz'](q2,self.http.request,self.credentials)
                        source_results['musicbrainz']=candidates[:18]
                        statuses['musicbrainz']='ok_crosssource_isrc'
                    except ProviderError as exc:
                        statuses['musicbrainz']='crosssource_'+str(exc)
                    except Exception as exc:
                        statuses['musicbrainz']='crosssource_error_'+type(exc).__name__
                    break
        joined=aggregate(q,source_results)
        joined['status']=statuses
        joined['queried_sources']=len(source_results)
        return (joined, q)

    def status(self):
        with self._lock:
            elapsed = max(.001, time.monotonic()-self._started)
            return {'queued':self.queued_count, 'committed':self.committed_count,
                    'pending':len(self.pending), 'failed':self._counts['failed'],
                    'paused':self.paused, 'auto_paused_backlog':self.auto_paused_backlog,
                    'staging':len(self._ingest_seen), 'capacity':self.capacity,
                    'batch_size':self.batch_size, 'batch_seconds':self._batch_seconds,
                    'pacing_seconds':self._pace,
                    'backpressure':self.backpressure, 'db_error':self.db_error,
                    'backlog':self._counts['queued'], 'retry':self._counts['retry'],
                    'running':self._counts['running'],
                    'flushed':self._flush_receipt.is_set(),
                    'stopped':self._stop_receipt.is_set(),
                    'provider_rate':{k:v/elapsed for k,v in self._rates.items()},
                    'provider_eta':{k:(self._counts['queued']*elapsed/v if v else None)
                                    for k,v in self._rates.items()}}

    def stop(self):
        with self._lock:
            self.stopped = True
            self.paused = True
        self._ingest_event.set()
