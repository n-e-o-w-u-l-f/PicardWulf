"""S2 capabilities and persisted request governance; no credentials in SQLite."""
import time
import math
from email.utils import parsedate_to_datetime

STATES=('AVAILABLE','CREDENTIALS_REQUIRED','QUOTA_WAIT','TEMPORARY_ERROR','RESTRICTED','DISABLED')
RETRYABLE=frozenset(('QUOTA_WAIT','TEMPORARY_ERROR'))


def normalize_options(options):
    known=('musicbrainz','deezer','itunes','spotify','soundcloud','lastfm')
    disabled=options.get('disabled',())
    if not isinstance(disabled,(list,tuple,set)):disabled=()
    try:budget=max(1,min(3000,int(options.get('requests_per_hour',3000))))
    except (ValueError,TypeError,OverflowError):budget=3000
    return {'disabled':tuple(s for s in known if s in disabled),'requests_per_hour':budget,
            'exhaustive':options.get('exhaustive') is True,
            'spotify_existing_access_confirmed':options.get('spotify_existing_access_confirmed') is True}


class ProviderError(Exception):
    def __init__(self,reason,state=None,retry_after=0,attempted=None):
        # Only application-defined reason codes are retained, never an HTTP
        # body, URL, exception message or token-bearing authentication payload.
        safe={'HTTP_401','HTTP_403','HTTP_429','HTTP_503','HTTP_500','HTTP_502','HTTP_504',
              'HTTP_400','HTTP_404','rate_limit_cooldown','network_loss','response_invalid',
              'service_rejected','invalid_token','refresh_uncertain','vault_unavailable',
              'provider_disabled','access_not_confirmed','credentials_missing',
              'request_budget','circuit_open','request_canceled'}
        self.reason=reason if reason in safe else 'network_loss'
        self.state=state or ('CREDENTIALS_REQUIRED' if self.reason in ('HTTP_401','invalid_token',
            'credentials_missing','refresh_uncertain','vault_unavailable') else
            'RESTRICTED' if self.reason in ('HTTP_403','HTTP_400','HTTP_404','access_not_confirmed') else
            'QUOTA_WAIT' if self.reason in ('HTTP_429','rate_limit_cooldown','request_budget') else
            'DISABLED' if self.reason in ('provider_disabled','request_canceled') else 'TEMPORARY_ERROR')
        self.attempted=(self.reason not in ('request_budget','rate_limit_cooldown','credentials_missing',
            'refresh_uncertain','vault_unavailable','provider_disabled','access_not_confirmed','request_canceled')
            if attempted is None else bool(attempted))
        try:
            delay=float(retry_after)
            self.retry_after=max(0,delay) if math.isfinite(delay) else 0
        except (TypeError,ValueError):self.retry_after=0
        super().__init__(self.reason)


def retry_delay(value,now=None):
    now=time.time() if now is None else now
    try:
        number=float(value)
        return max(0,number) if math.isfinite(number) else 45.
    except (ValueError,TypeError):
        try:return max(0,parsedate_to_datetime(str(value)).timestamp()-now)
        except (ValueError,TypeError,OverflowError):return 45.


def capability(source,credentials,options):
    state,reason='AVAILABLE','eligible_unprobed'
    if source in options.get('disabled',()):state,reason='DISABLED','operator_disabled'
    elif source=='spotify':
        present=bool(credentials.get('spotify_access_token') or
            (credentials.get('spotify_client_id') and credentials.get('spotify_client_secret')))
        if not present:state,reason='CREDENTIALS_REQUIRED','credentials_missing'
        elif not options.get('spotify_existing_access_confirmed',False):
            state,reason='RESTRICTED','existing_access_not_confirmed_no_purchase'
    elif source=='soundcloud':
        if credentials.get('soundcloud_refresh_pending'):
            state,reason='CREDENTIALS_REQUIRED','one_time_refresh_uncertain'
        elif not (credentials.get('soundcloud_token') or
                (credentials.get('soundcloud_client_id') and credentials.get('soundcloud_client_secret'))):
            state,reason='CREDENTIALS_REQUIRED','credentials_missing'
    elif source=='lastfm' and not credentials.get('lastfm_api_key'):
        state,reason='CREDENTIALS_REQUIRED','credentials_missing'
    return {'state':state,'reason':reason,'observed':False}


def album_cache_key(q):
    # Album-local pool, not a release/edition identity. Only exact compatible
    # track candidates may be reused; S3 still owns edition consensus.
    import hashlib
    import unicodedata
    def normalize(v):return ' '.join(unicodedata.normalize('NFKC',str(v or '')).casefold().split())
    if not q.get('album'):return None
    return hashlib.sha256(('album-pool-v1-enriched-20261014|'+normalize(q.get('artist'))+'|'+normalize(q['album'])).encode()).hexdigest()


class PolicyClient:
    def __init__(self,store,transport,credentials,options,delays,stopped=lambda:False):
        self.store,self.transport,self.credentials=store,transport,credentials
        self.options,self.delays=options,delays
        self.stopped=stopped
        self._auth_tickets={}

    def _reserve(self,source):
        bucket=('musicbrainz' if source=='musicbrainz_lookup' else
                'deezer' if source in ('deezer_track','deezer_album') else source)
        provider=bucket.removesuffix('_auth')
        delay=self.delays.get(bucket,self.delays.get(provider,1.))
        budget=4 if source=='soundcloud_auth' else int(self.options.get('requests_per_hour',3000))
        if source=='soundcloud_auth':delay=max(delay,900.)
        deadline=time.monotonic()+8
        while True:
            if self.stopped():raise ProviderError('request_canceled')
            reservation=self.store.reserve_provider(bucket,time.time(),delay,budget)
            if reservation['state'] in ('CREDENTIALS_REQUIRED','RESTRICTED'):
                raise ProviderError(reservation['reason'],reservation['state'],attempted=False)
            wait=reservation['wait']
            if wait<=0:return bucket
            if wait>deadline-time.monotonic():
                raise ProviderError('request_budget','QUOTA_WAIT',wait)
            # Short within-adapter pacing stays entirely on its worker. Long
            # cooldowns return to durable retry instead of tying up a thread.
            time.sleep(min(.25,max(.01,wait)))

    def reserve_auth(self,source):
        if source!='soundcloud_auth':raise ProviderError('credentials_missing')
        cap=capability('soundcloud',self.credentials,self.options)
        if cap['state']!='AVAILABLE':raise ProviderError('credentials_missing',cap['state'])
        self._reserve(source)
        ticket=object()
        self._auth_tickets[source]=ticket  # bounded: one in-flight grant per source
        return ticket

    def request(self,source,*args,**kwargs):
        bucket=('musicbrainz' if source=='musicbrainz_lookup' else
                'deezer' if source in ('deezer_track','deezer_album') else source)
        provider=bucket.removesuffix('_auth')
        ticket=kwargs.pop('_reservation',None)
        reserved=ticket is not None and ticket is self._auth_tickets.get(source)
        if ticket is not None and not reserved:raise ProviderError('credentials_missing')
        if reserved:self._auth_tickets.pop(source,None)
        credentials=self.credentials
        if reserved and source=='soundcloud_auth':
            # Only this already-reserved in-flight refresh may cross its own
            # persisted pending fence. A reloaded/uncertain refresh has no ticket.
            credentials={k:v for k,v in credentials.items() if k!='soundcloud_refresh_pending'}
        cap=capability(provider,credentials,self.options)
        if cap['state']!='AVAILABLE':
            raise ProviderError('provider_disabled' if cap['state']=='DISABLED' else
                'access_not_confirmed' if cap['state']=='RESTRICTED' else 'credentials_missing',cap['state'])
        if not reserved:self._reserve(source)
        if self.stopped():raise ProviderError('request_canceled')
        try:
            result=self.transport.request(source,*args,**kwargs)
            if not isinstance(result,(dict,list)):
                raise ProviderError('response_invalid')
        except ProviderError as exc:
            now=time.time()
            self.store.provider_failure(bucket,exc.state,exc.reason,now+max(5,exc.retry_after),1)
            raise
        except Exception:
            self.store.provider_failure(bucket,'TEMPORARY_ERROR','network_loss',time.time()+10,1)
            raise ProviderError('network_loss',retry_after=10) from None
        self.store.provider_success(bucket)
        return result
