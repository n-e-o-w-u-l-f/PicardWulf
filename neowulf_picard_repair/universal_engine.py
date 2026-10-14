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
import random
import unicodedata
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, closing
from concurrent.futures import Future
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

from .universal_adapters import SOURCES, ADAPTERS, env_credentials, one
from .credentials import load as load_credentials
from .provider_policy import (ProviderError, PolicyClient, capability, RETRYABLE, album_cache_key,
                              retry_delay, normalize_options)

TTL = 72 * 3600
MAX_BODY = 900_000
_ALLOWED = {
    'musicbrainz': ('musicbrainz.org','/ws/2/recording/'),
    'musicbrainz_lookup': ('musicbrainz.org','/ws/2/recording/'),
    'deezer': ('api.deezer.com','/search'),
    'deezer_track': ('api.deezer.com','/track/'),
    'deezer_album': ('api.deezer.com','/album/'),
    'itunes': ('itunes.apple.com','/search'),
    'spotify_auth': ('accounts.spotify.com','/api/token'),
    'spotify': ('api.spotify.com','/v1/search'),
    'soundcloud': ('api.soundcloud.com','/tracks'),
    'soundcloud_auth': ('secure.soundcloud.com','/oauth/token'),
    'lastfm': ('ws.audioscrobbler.com','/2.0/'),
}
MIN_DELAY = {'musicbrainz':1.15,'musicbrainz_lookup':1.15,'deezer':1.4,'deezer_track':1.4,'deezer_album':1.4,'itunes':3.2,'spotify_auth':1.,
             'spotify':1.0,'soundcloud':1.1,'lastfm':1.1}
MIN_DELAY['soundcloud_auth']=900.

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
            'duration_ms':dura(), 'inferred_filename':bool(one(g('inferred_filename'))),
            'tracknumber':one(g('tracknumber')), 'discnumber':one(g('discnumber')),
            'date':one(g('date')), 'genre':one(g('genre')), 'label':one(g('label')),
            'barcode':one(g('barcode')), 'composer':one(g('composer')),
            'totaltracks':one(g('totaltracks')), 'totaldiscs':one(g('totaldiscs'))}


def query_key(q):
    s='picardwulf-v1-fulltrack-20261014|'+ '|'.join(norm(q.get(k,'')) for k in ('title','artist','album','isrc','recording_mbid'))
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


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class HTTPClient:
    def __init__(self):
        self._lock=threading.Lock()
        self._last={}
        self._cooldown={}
        self._opener=build_opener(NoRedirect())

    def request(self,source,url,params,headers=None,form=None):
        host,path=_ALLOWED[source]
        parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.hostname!=host:
            raise ValueError('provider endpoint not allowed')
        if source=='musicbrainz_lookup':
            if not re.fullmatch(r'/ws/2/recording/[0-9a-fA-F-]{36}',parsed.path):
                raise ValueError('provider lookup endpoint not allowed')
        elif source in ('deezer_track','deezer_album'):
            if not re.fullmatch(re.escape(path)+r'[1-9][0-9]{0,15}',parsed.path):
                raise ValueError('provider detail endpoint not allowed')
        elif parsed.path!=path:
            raise ValueError('provider endpoint not allowed')
        # Subrequests consume the same rate/quota budget as parent searches.
        rate_bucket = ('musicbrainz' if source == 'musicbrainz_lookup' else
                       'deezer' if source in ('deezer_track','deezer_album') else source)
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
            with self._opener.open(req,timeout=9) as resp:
                if int(resp.status)!=200:raise ValueError('unexpected status')
                content_type=resp.headers.get('Content-Type','').split(';',1)[0].strip().lower()
                apple_json=(source=='itunes' and content_type in ('text/javascript','application/javascript'))
                if not apple_json and content_type not in ('application/json','text/json') and not content_type.endswith('+json'):
                    raise ValueError('unexpected content type')
                data=resp.read(MAX_BODY+1)
                if len(data)>MAX_BODY:raise ValueError('response too large')
                result=json.loads(data.decode('utf-8'))
                if isinstance(result,dict) and result.get('error'):
                    raise ProviderError('service_rejected')
                return result
        except HTTPError as exc:
            if exc.code in (429,503):
                delay=max(8,retry_delay(exc.headers.get('Retry-After','45')))
                with self._lock:self._cooldown[rate_bucket]=time.monotonic()+delay
            exc.close()
            raise ProviderError(f'HTTP_{exc.code}',retry_after=delay if exc.code in (429,503) else 0) from None
        except (URLError,OSError,TimeoutError) as exc:
            raise ProviderError(type(exc).__name__) from None
        except (ValueError, UnicodeError) as exc:
            raise ProviderError('response_invalid') from None


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
            if version > 3:
                raise sqlite3.DatabaseError('unsupported future queue schema')
            existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
            if existing and version < 3:
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
            task_cols={row[1] for row in db.execute('PRAGMA table_info(provider_tasks)')}
            for name,definition in (('attempts','INTEGER DEFAULT 0'),('retry_at','REAL DEFAULT 0')):
                if name not in task_cols:db.execute(f'ALTER TABLE provider_tasks ADD COLUMN {name} {definition}')
            db.execute('CREATE TABLE IF NOT EXISTS provider_budgets(source TEXT PRIMARY KEY,payload TEXT)')
            db.execute('PRAGMA user_version=3')

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
            rows = db.execute('SELECT source,status,payload,attempts,retry_at FROM provider_tasks WHERE k=? AND revision=?',
                              (key, revision)).fetchall()
        return {src: {'status': state, 'payload': json.loads(payload),'attempts':attempts,'retry_at':retry_at}
                for src, state, payload,attempts,retry_at in rows}

    def checkpoint(self, key, revision, source, candidates, status,attempts=0,retry_at=0):
        with self._lock, self._db() as db:
            if db.execute("SELECT 1 FROM jobs WHERE k=? AND revision=? AND state='running'",
                          (key, revision)).fetchone() is None:
                return False
            db.execute('INSERT OR REPLACE INTO provider_tasks(k,revision,source,status,payload,updated,attempts,retry_at) '
                       'VALUES(?,?,?,?,?,?,?,?)',
                       (key, revision, source, status, json.dumps(candidates), time.time(),attempts,retry_at))
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

    def _budget(self,db,source):
        row=db.execute('SELECT payload FROM provider_budgets WHERE source=?',(source,)).fetchone()
        return json.loads(row[0]) if row else {}

    def _save_budget(self,db,source,value):
        db.execute('INSERT OR REPLACE INTO provider_budgets VALUES(?,?)',(source,json.dumps(value)))

    def reserve_provider(self,source,now,delay,budget):
        with self._lock,self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            value=self._budget(db,source)
            if value.get('state') in ('CREDENTIALS_REQUIRED','RESTRICTED'):
                return dict(value,wait=0)
            window=value.get('window',now)
            if now>=window+3600:value.update(window=now,used=0)
            used=value.get('used',0)
            wait=max(0,value.get('next',0)-now,value.get('cooldown',0)-now,
                     window+3600-now if used>=max(1,budget) else 0)
            if not wait:
                # Capacity-one token bucket: persist the next refill before a
                # request, so plugin reload cannot manufacture another token.
                value.update(next=now+max(0,delay),window=value.get('window',now),used=used+1)
                self._save_budget(db,source,value)
            return {'wait':wait,'state':'QUOTA_WAIT' if wait else 'AVAILABLE',
                    'reason':'request_budget' if wait else 'reserved'}

    def provider_failure(self,source,state,reason,retry_at,errors,observed=True):
        with self._lock,self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            value=self._budget(db,source)
            count=value.get('errors',0)+errors
            cooldown=max(value.get('cooldown',0),retry_at)
            if state=='TEMPORARY_ERROR' and count>=3:cooldown=max(cooldown,time.time()+180)
            value.update(state=state,reason=reason,errors=count,cooldown=cooldown,observed=bool(observed))
            self._save_budget(db,source,value)

    def provider_success(self,source):
        with self._lock,self._db() as db:
            value=self._budget(db,source)
            value.update(state='AVAILABLE',reason='response_received',errors=0,observed=True)
            self._save_budget(db,source,value)

    def provider_status(self):
        with self._lock,self._db() as db:
            rows=db.execute('SELECT source,payload FROM provider_budgets').fetchall()
        return {s:json.loads(p) for s,p in rows}

    def reset_providers(self,sources):
        with self._lock,self._db() as db:
            for source in sources:
                value=self._budget(db,source)
                # Credentials update does not reset quota tokens or cooldown.
                value.update(state='AVAILABLE',reason='credentials_updated',errors=0)
                self._save_budget(db,source,value)

    def defer_job(self,key,revision,q,payload,retry_at):
        with self._lock,self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE k=? AND revision=? AND state='running'",
                          (key,revision)).fetchone() is None:return False
            db.execute('INSERT OR REPLACE INTO results VALUES(?,?,?,?)',
                       (key,time.time(),json.dumps(q),json.dumps(payload)))
            db.execute("UPDATE jobs SET state='retry',retry_at=? WHERE k=?",(retry_at,key))
        return True

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
                 capacity=2048, batch_size=256, predecessor=None,provider_options=None,provider_delays=None):
        from .background_io import DatabaseWorker
        self.capacity = max(1, min(2048, int(capacity)))
        self.batch_size = max(1, min(self.capacity, int(batch_size)))
        self.http = transport or HTTPClient()
        self.credentials = dict(credentials or {})
        self._load_credentials = credentials is None
        self.provider_options=normalize_options(provider_options or {})
        self.provider_delays=dict(MIN_DELAY if provider_delays is None else provider_delays)
        self._capabilities={}
        self._adapter_locks={source:threading.RLock() for source in ('musicbrainz','lastfm')}
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
        self.auto_paused_backlog = False  # legacy status key; no forced pause
        self.large_backlog_detected = False
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
            self.policy=PolicyClient(self.store,self.http,self.credentials,self.provider_options,self.provider_delays,
                                     stopped=lambda:self.stopped)
            self._counts = self.store.state_counts()
            self.large_backlog_detected = sum(self._counts.values()) > 2000
            # Asynchronous storage, provider-specific budgets and a two-task
            # worker cap now protect the GUI. Don't strand a 2k+ backlog
            # behind an unrequested automatic pause. An explicit persisted
            # operator pause (self.paused) must still be respected.
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
                                retry_at=payload.get('_defer_until',0)
                                clean_payload={k:v for k,v in payload.items() if k!='_defer_until'}
                                if retry_at:self.store.defer_job(key,revision,q,clean_payload,retry_at)
                                else:self.store.finish_job(key, revision, q, clean_payload)
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
                            if method=='apply_credentials':
                                from .universal_adapters import _AUTH_LOCKS
                                with _AUTH_LOCKS['spotify'],_AUTH_LOCKS['soundcloud']:
                                    values,persist=argument
                                    if persist:
                                        from .credentials import save
                                        current=load_credentials()
                                    else:current=dict(self.credentials)
                                    refresh_changed=('soundcloud_refresh_token' in values and
                                        values['soundcloud_refresh_token']!=current.get('soundcloud_refresh_token'))
                                    current.update(values)
                                    if refresh_changed:
                                        current.pop('soundcloud_refresh_pending',None)
                                        current['soundcloud_token_until']='1'
                                    if persist:save(current)
                                    self.credentials.update(current)
                                    if refresh_changed:self.credentials.pop('soundcloud_refresh_pending',None)
                                    if any(k.startswith('spotify_') for k in values):
                                        self.credentials.pop('spotify_access_token',None)
                                        self.credentials.pop('spotify_token_until',None)
                                self.store.reset_providers(('spotify','spotify_auth','soundcloud','soundcloud_auth','lastfm'))
                                value={'saved':bool(persist)}
                            else:value=getattr(self.store, method)(argument)
                            if method=='get_results':
                                with self._lock:
                                    for k,_,force in self._ingest:
                                        if force:value.pop(k,None)
                            receipt.set_result(value)
                        except Exception as exc:
                            receipt.set_exception(exc)
                            if method!='apply_credentials' or isinstance(exc,sqlite3.Error):
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
                    observed=self.store.provider_status()
                    with self._lock:
                        self._capabilities={source:capability(source,self.credentials,self.provider_options)
                                            for source in SOURCES}
                        for source,value in observed.items():
                            if source not in SOURCES:continue
                            if self._capabilities[source]['state']!='AVAILABLE':continue
                            self._capabilities[source].update(state=value.get('state','AVAILABLE'),
                                reason=value.get('reason','eligible_unprobed'),observed=value.get('observed',False))
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

    def update_credentials(self,values,persist=False):
        return self._request('apply_credentials',(dict(values),bool(persist)))

    def configure_providers(self,options):
        with self._lock:
            old=self.provider_options
            self.provider_options=normalize_options(options)
            if hasattr(self,'policy'):self.policy.options=self.provider_options
        newly_enabled=set(old['disabled'])-set(self.provider_options['disabled'])
        if newly_enabled:self._request('reset_providers',tuple(newly_enabled))

    def _work(self,key,q,force=False,revision=1):
        source_results={}
        statuses={}
        capabilities={}
        waiting=[]
        incomplete=False
        progress=self.store.provider_progress(key,revision)
        pool_key=album_cache_key(q)
        pool=None if force or not pool_key else self.store.get_response(pool_key)
        checkpoints_complete=all(entry.get('status') in ('ok','cached','COMPLETE') for entry in progress.values())
        if pool and checkpoints_complete and not self.provider_options.get('exhaustive',False):
            reusable={}
            for candidate in pool:
                src=candidate.get('source')
                if src not in SOURCES or capability(src,self.credentials,self.provider_options)['state']!='AVAILABLE':continue
                if norm(candidate.get('title'))==norm(q['title']) and score(q,candidate)[0]>=.93:
                    reusable.setdefault(src,[]).append(candidate)
            local=aggregate(q,reusable)
            if local['auto']['state']=='ready':
                local.update(status={src:'album_cache' if src in reusable else 'local_match_no_query' for src in SOURCES},
                    capabilities={src:dict(capability(src,self.credentials,self.provider_options),
                        reason='album_cache' if src in reusable else 'strong_local_match_no_query') for src in SOURCES},
                    queried_sources=0,completion='LOCAL_CACHE')
                return local,q
        for source in SOURCES:
            if self.stopped:return None,q
            cap=capability(source,self.credentials,self.provider_options)
            capabilities[source]=cap
            if cap['state']!='AVAILABLE':
                statuses[source]=cap['state']
                self.store.checkpoint(key,revision,source,None,cap['state'])
                continue
            entry=progress.get(source,{})
            attempts=entry.get('attempts',0)
            state=entry.get('status','running')
            if state in ('ok','cached','COMPLETE'):
                source_results[source]=entry['payload'] or []
                statuses[source]=state
                cap.update(observed=True,reason='completed_checkpoint')
                continue
            if state in RETRYABLE:
                if attempts>=3:
                    statuses[source]=state
                    cap.update(state=state,reason='retry_exhausted',observed=True)
                    incomplete=True
                    continue
                if entry.get('retry_at',0)>time.time():
                    waiting.append(entry['retry_at'])
                    statuses[source]=state
                    cap.update(state=state,reason='persisted_backoff',observed=True)
                    continue
            # A newly found strong MusicBrainz result is not a reason to
            # skip higher-scoring streaming catalogues. Only proven cached
            # complete decisions take the local-first shortcut above.
            if source=='lastfm' and q.get('album') and source_results and not force and not (
                    self.provider_options.get('exhaustive',False)):
                if aggregate(q,source_results)['auto']['state']=='ready':
                    statuses[source]='enrichment_not_needed'
                    cap.update(reason='known_album_strong_sources_no_enrichment_needed')
                    continue
            if not self.store.checkpoint(key,revision,source,None,'running',attempts):return None,q
            cache_id=hashlib.sha256((source+'|'+key).encode()).hexdigest()
            cached=None if force else self.store.get_response(cache_id)
            if cached is not None:
                source_results[source]=cached
                statuses[source]='cached'
                cap.update(observed=True,reason='cached_metadata')
                self.store.checkpoint(key,revision,source,cached,'cached')
                continue
            try:
                if source in self._adapter_locks:
                    with self._adapter_locks[source]:
                        candidates=ADAPTERS[source](q,self.policy.request,self.credentials)
                else:candidates=ADAPTERS[source](q,self.policy.request,self.credentials)
                if candidates is None:raise ProviderError('credentials_missing')
                if not isinstance(candidates,list):raise ProviderError('response_invalid')
                source_results[source]=candidates[:18]
                self.store.save_response(cache_id,candidates[:18])
                statuses[source]='ok'
                cap.update(observed=True,reason='valid_catalog_response')
                self.store.checkpoint(key,revision,source,candidates[:18],'COMPLETE')
            except (sqlite3.Error,OSError):
                raise  # storage errors must pause the scheduler, not masquerade as API failures
            except Exception as raw:
                exc=raw if isinstance(raw,ProviderError) else ProviderError('response_invalid')
                # A quota deferral consumes no attempt: no HTTP request occurred.
                attempted=exc.attempted
                count=attempts+int(attempted)
                delay=max(exc.retry_after, min(180.,5*(2**min(count,5)))+random.uniform(0,1))
                retry_at=time.time()+delay if exc.state in RETRYABLE and count<3 else 0
                statuses[source]=exc.state
                cap.update(state=exc.state,reason=exc.reason,observed=attempted)
                self.store.provider_failure(source,exc.state,exc.reason,time.time()+delay,
                    0 if isinstance(raw,ProviderError) else 1,attempted)
                self.store.checkpoint(key,revision,source,None,exc.state,count,retry_at)
                if retry_at:waiting.append(retry_at)
                else:incomplete=incomplete or exc.state in RETRYABLE
            if statuses.get(source)=='ok':
                with self._lock:self._rates[source]=self._rates.get(source,0)+1
        if self.stopped:return None,q
        # Preserve source-neutral exact-ISRC → native MusicBrainz resolution.
        # This subtask shares the provider budget and durable retry cursor.
        if not source_results.get('musicbrainz') and statuses.get('musicbrainz') in ('ok','cached','COMPLETE'):
            other=next((c for source in ('spotify','deezer') for c in source_results.get(source,[])
                        if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{3}[0-9]{7}',c.get('isrc','')) and
                        similarity(q['title'],c.get('title'))>.92 and similarity(q['artist'],c.get('artist'))>.92),None)
            if other:
                sub='musicbrainz_cross_isrc'
                entry=progress.get(sub,{})
                cap=capabilities['musicbrainz']
                count=entry.get('attempts',0)
                if entry.get('status')=='COMPLETE':
                    source_results['musicbrainz']=entry['payload'] or []
                elif entry.get('status') in RETRYABLE and count>=3:
                    incomplete=True
                    cap.update(state=entry['status'],reason='isrc_resolution_retry_exhausted')
                elif entry.get('retry_at',0)>time.time():
                    waiting.append(entry['retry_at'])
                    cap.update(state=entry['status'],reason='isrc_resolution_backoff')
                else:
                    try:
                        if not self.store.checkpoint(key,revision,sub,None,'running',count):return None,q
                        with self._adapter_locks['musicbrainz']:
                            resolved=ADAPTERS['musicbrainz']({**q,'isrc':other['isrc']},self.policy.request,self.credentials)
                        source_results['musicbrainz']=resolved[:18]
                        self.store.checkpoint(key,revision,sub,resolved[:18],'COMPLETE')
                        statuses['musicbrainz']='ok_crosssource_isrc'
                    except (sqlite3.Error,OSError):raise
                    except Exception as raw:
                        exc=raw if isinstance(raw,ProviderError) else ProviderError('response_invalid')
                        count+=int(exc.attempted)
                        retry_at=time.time()+max(exc.retry_after,5*2**min(count,5))+random.uniform(0,1) if (
                            exc.state in RETRYABLE and count<3) else 0
                        self.store.checkpoint(key,revision,sub,None,exc.state,count,retry_at)
                        cap.update(state=exc.state,reason='isrc_resolution_'+exc.reason,observed=exc.attempted)
                        if retry_at:waiting.append(retry_at)
                        else:incomplete=True
        joined=aggregate(q,source_results)
        joined.update(status=statuses,capabilities=capabilities,queried_sources=len(source_results),
                      completion='PENDING' if waiting else 'INCOMPLETE' if incomplete else 'COMPLETE')
        if waiting or incomplete:
            joined['auto']={'state':'pending_providers' if waiting else 'incomplete_providers',
                            'reason':'Provider responses are unfinished or unavailable; review only.'}
            joined['verdict']='review'
        if waiting:joined['_defer_until']=min(waiting)
        if pool_key and source_results and joined['completion']=='COMPLETE':
            # Bounded album-local normalized candidate pool. It contains text
            # metadata only; no artwork, credentials or raw API bodies.
            rows=list(pool or [])+[c for values in source_results.values() for c in values]
            unique={json.dumps(c,sort_keys=True):c for c in rows}
            self.store.save_response(pool_key,list(unique.values())[-200:])
        return joined,q

    def status(self):
        with self._lock:
            elapsed = max(.001, time.monotonic()-self._started)
            return {'queued':self.queued_count, 'committed':self.committed_count,
                    'pending':len(self.pending), 'failed':self._counts['failed'],
                    'paused':self.paused, 'auto_paused_backlog':self.auto_paused_backlog,
                    'large_backlog_detected':self.large_backlog_detected,
                    'staging':len(self._ingest_seen), 'capacity':self.capacity,
                    'batch_size':self.batch_size, 'batch_seconds':self._batch_seconds,
                    'pacing_seconds':self._pace,
                    'backpressure':self.backpressure, 'db_error':self.db_error,
                    'backlog':self._counts['queued'], 'retry':self._counts['retry'],
                    'running':self._counts['running'],
                    'flushed':self._flush_receipt.is_set(),
                    'stopped':self._stop_receipt.is_set(),
                    'provider_rate':{k:v/elapsed for k,v in self._rates.items()},
                    'capabilities':dict(self._capabilities),
                    'provider_eta':{k:(self._counts['queued']*elapsed/v if v else None)
                                    for k,v in self._rates.items()}}

    def stop(self):
        with self._lock:
            self.stopped = True
            self.paused = True
        self._ingest_event.set()
