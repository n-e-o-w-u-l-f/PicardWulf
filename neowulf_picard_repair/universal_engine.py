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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
    s='|'.join(norm(q.get(k,'')) for k in ('title','artist','album','isrc','recording_mbid'))
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


def aggregate(q,results):
    rows=[]
    for source, candidates in results.items():
        for candidate in candidates:
            quality, reason = score(q,candidate)
            row={**candidate, 'score':quality,'reason':reason}
            rows.append(row)
    # No consensus without compatible artist+title. Group independent sources
    # by recording identity (ISRC if both exist; else artist+title).
    matches=[x for x in rows if x['score']>=.70]
    groups=defaultdict(list)
    for x in matches:
        identity=(norm(x['artist']),norm(x['title']))
        # Same song often appears on several albums; don't merge release names
        # into any authoritative release/album-artist prediction.
        groups[identity].append(x)
    for group in groups.values():
        count=len(set(x['source'] for x in group))
        for x in group:x['source_support']=count
    rows.sort(key=lambda x:(x['score'],x.get('source_support',1)),reverse=True)
    winners=[r for r in rows if r['score']>=.84]
    if not winners:
        verdict='no_safe_match'
    elif (winners[0]['score']>=.90 and winners[0].get('source_support',1)>=2):
        verdict='review_high_confidence'
    else:
        verdict='review'
    # Never claim automatic tagging or album release matching.
    return {'verdict':verdict,'candidates':rows[:40]}


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
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS results(k TEXT PRIMARY KEY, updated REAL, query TEXT, payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS responses(k TEXT PRIMARY KEY, updated REAL, payload TEXT)')
            db.execute("CREATE TABLE IF NOT EXISTS jobs(k TEXT PRIMARY KEY, queued REAL, query TEXT, force INTEGER, state TEXT DEFAULT 'queued')")
            cols={row[1] for row in db.execute('PRAGMA table_info(jobs)').fetchall()}
            if 'state' not in cols:
                db.execute("ALTER TABLE jobs ADD COLUMN state TEXT DEFAULT 'queued'")

    @contextmanager
    def _db(self):
        conn=sqlite3.connect(str(self.path),timeout=8)
        try:
            with conn:yield conn
        finally:conn.close()

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

    def save_result(self,key,q,payload):
        with self._lock,self._db() as db:
            db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?,?)',
                       (key,time.time(),json.dumps(q,ensure_ascii=False),
                        json.dumps(payload,ensure_ascii=False)))
            db.execute('DELETE FROM results WHERE updated<?',(time.time()-30*86400,))

    def enqueue(self,key,q,force=False):
        with self._lock,self._db() as db:
            result=db.execute("INSERT OR IGNORE INTO jobs(k,queued,query,force,state) VALUES(?,?,?,?,'queued')",
                              (key,time.time(),json.dumps(q,ensure_ascii=False),int(bool(force))))
            # Refresh a queued job when explicitly requested by the user.
            if force and result.rowcount == 0:
                db.execute("UPDATE jobs SET force=1, state='queued' WHERE k=?",(key,))
            return result.rowcount > 0

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


def private_cache_path():
    app=os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME')
    if not app:app=str(Path.home()/'.cache')
    return Path(app)/'NEOWULF'/'Picard3'/'metadata-cache.sqlite3'


class UniversalAggregator:
    def __init__(self, store=None,transport=None, credentials=None):
        self.store=store or ResultStore(private_cache_path())
        self.http=transport or HTTPClient()
        if credentials is not None:
            self.credentials = credentials
        else:
            self.credentials = env_credentials()
            try:self.credentials.update(load_credentials())
            except (OSError, ValueError, RuntimeError):pass
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='NEOWULF-Metadata')
        self._lock=threading.RLock()
        self._pumping=False
        self._repump=False
        self.pending=set()
        self.stopped=False
        self.failed_count=0
        self.queued_count=0
        self._pump()

    def schedule(self,raw,force=False):
        q=clean_track(raw)
        if q is None:return False
        key=query_key(q)
        if not force and self.store.get_result(key) is not None:return False
        with self._lock:
            if self.stopped:return False
        accepted=self.store.enqueue(key,q,force=force)
        if accepted:
            with self._lock:self.queued_count+=1
        self._pump()
        return accepted

    def _pump(self):
        with self._lock:
            if self._pumping:
                self._repump=True
                return
            if self.stopped:return
            self._pumping=True
        try:
            while True:
                with self._lock:
                    if self.stopped:break
                    free=max(0,8-len(self.pending))
                    jobs=self.store.next_jobs(self.pending,free) if free else []
                    self._repump=False
                    for key,_,_ in jobs:self.pending.add(key)
                for key,q,force in jobs:
                    try:
                        future=self.executor.submit(self._work,key,q,force)
                        future.add_done_callback(lambda task,k=key:self._complete(k,task))
                    except RuntimeError:
                        with self._lock:self.pending.discard(key)
                with self._lock:
                    if not self._repump:break
        finally:
            with self._lock:
                self._pumping=False
                again=self._repump and not self.stopped
                self._repump=False
            if again:self._pump()

    def _complete(self,key,task):
        from concurrent.futures import CancelledError
        try:failed=task.cancelled() or task.exception() is not None
        except CancelledError:failed=True
        if self.stopped and task.cancelled():failed=False
        if failed:self.store.fail_job(key)
        with self._lock:
            self.pending.discard(key)
            if failed:self.failed_count+=1
        self._pump()

    def _work(self,key,q,force=False):
        source_results={}
        statuses={}
        for source in SOURCES:
            if self.stopped:return None  # preserve queued job for next Picard start
            adapter=ADAPTERS[source]
            cache_id=hashlib.sha256((source+'|'+key).encode()).hexdigest()
            cached=None if force else self.store.get_response(cache_id)
            if cached is not None:
                source_results[source]=cached
                statuses[source]='cached'
                continue
            try:
                # Keep credentials memory-only; never include in cache keys.
                candidates=adapter(q,self.http.request,self.credentials)
                if candidates is None:
                    statuses[source]='not_configured'
                    continue
                if not isinstance(candidates,list):raise ValueError('unexpected candidates')
                source_results[source]=candidates[:18]
                self.store.save_response(cache_id,candidates[:18])
                statuses[source]='ok'
            except ProviderError as e:
                statuses[source]=str(e)
            except Exception as e:
                statuses[source]='error_'+type(e).__name__
        if self.stopped:return None
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
        self.store.save_result(key,q,joined)
        self.store.delete_job(key)
        return joined

    def status(self):
        with self._lock:
            return {'queued':self.queued_count,'pending':len(self.pending),
                    'backlog':self.store.job_count(),'failed':self.failed_count}

    def stop(self):
        with self._lock:self.stopped=True
        self.executor.shutdown(wait=False,cancel_futures=True)
