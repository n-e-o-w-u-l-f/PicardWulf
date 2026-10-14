"""Official catalogue search adapters. No HTML crawling, login bypass or audio downloads.

Use only documented endpoints; credentials are optional and are never logged.
Transport is injected for tests. Result dictionaries are untrusted data.
"""
import base64
import os
import time
import re
import hashlib
import threading
from difflib import SequenceMatcher
from urllib.parse import urlencode
from .credentials import persist_soundcloud
from .provider_policy import ProviderError

_AUTH_LOCKS={'spotify':threading.RLock(),'soundcloud':threading.RLock()}


def rows(payload,key):
    if not isinstance(payload,dict) or not isinstance(payload.get(key),list):
        raise ValueError('catalog response schema invalid')
    values=payload[key][:6]
    if not all(isinstance(row,dict) for row in values):raise ValueError('catalog row schema invalid')
    return values

SOURCES = ('musicbrainz', 'deezer', 'itunes', 'spotify', 'soundcloud', 'lastfm')


def one(value):
    if isinstance(value, (list, tuple)):
        return one(value[0]) if value else ''
    return str(value or '').strip()


def credit(value):
    if isinstance(value, list):
        return ''.join(one(v.get('name', '')) if isinstance(v, dict) else one(v)
                       for v in value).strip()
    return one(value)


def _number(value, maximum=999):
    if isinstance(value, bool):return ''
    try:
        number=int(value)
        return str(number) if 0 < number <= maximum else ''
    except (TypeError, ValueError, OverflowError):return ''


def _genre(value):
    # A text-only genre from a provider response, never artwork or HTML.
    if isinstance(value, dict):
        value=value.get('name','')
    if isinstance(value, list):
        value=next((v for v in value if v), '')
    return one(value)[:120]


def item(source, title, artist, album='', duration=0, isrc='', mbid='', url='', albumartist='', release_mbid='', provider_album_id='', release_url='', release_date='', *,
         tracknumber='', discnumber='', totaltracks='', totaldiscs='', genre='', label='', barcode='', composer='', originaldate='', country='', edition=''):
    try: duration = max(0, min(10_000_000, int(float(duration or 0))))
    except (TypeError, ValueError, OverflowError): duration = 0
    # Keep credits and release fields separate. Never manufacture missing
    # provider fields, or treat the source's brand as an artist.
    return {'source': source, 'title': one(title)[:300], 'artist': one(artist)[:300],
            'album': one(album)[:300], 'albumartist': one(albumartist)[:300],
            'duration_ms': duration, 'isrc': one(isrc).upper()[:14],
            'recording_mbid': one(mbid)[:40], 'release_mbid': one(release_mbid)[:40], 'url': one(url)[:800],
            'provider_album_id':one(provider_album_id)[:110],
            'release_url':one(release_url)[:800], 'release_date':one(release_date)[:40],
            'tracknumber':_number(tracknumber), 'discnumber':_number(discnumber),
            'totaltracks':_number(totaltracks,9999), 'totaldiscs':_number(totaldiscs),
            'genre':_genre(genre), 'label':one(label)[:180],
            'barcode':one(barcode)[:32], 'composer':one(composer)[:180],
            'originaldate':one(originaldate)[:40], 'country':one(country)[:40], 'edition':one(edition)[:80]}


def musicbrainz(q, request, credentials):
    """Retrieve Picard-native release UUIDs via MusicBrainz recording data.

    Spotify/Deezer results are never allowed to invent release UUIDs. The
    MusicBrainz recording lookup is a second, independently verified step.
    """
    isrc = one(q.get('isrc')).upper()
    if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{3}\d{7}', isrc):
        query = f'isrc:{isrc}'
    else:
        def safe(v):
            return re.sub(r'[^\w\s\-\'\.]', ' ', one(v))[:130].strip()
        query = f'recording:"{safe(q["title"])}" AND artist:"{safe(q["artist"])}"'
    recording=one(q.get('recording_mbid'))
    if re.fullmatch(r'[0-9a-fA-F-]{36}',recording):
        record=request('musicbrainz_lookup',f'https://musicbrainz.org/ws/2/recording/{recording}',
                       {'inc':'releases+artist-credits+isrcs','fmt':'json'})
        if not isinstance(record,dict) or not record.get('id'):raise ValueError('recording response invalid')
        payload={'recordings':[record]}
    else:
        payload = request('musicbrainz', 'https://musicbrainz.org/ws/2/recording/',
                          {'query': query, 'fmt': 'json', 'limit': 6})
    found=[]
    for e in rows(payload,'recordings'):
        rid=one(e.get('id'))
        releases=e.get('releases') or []
        # Search results sometimes omit release relationships; use a bounded
        # MusicBrainz official recording lookup, not an external provider URL.
        if not releases and re.fullmatch(r'[0-9a-fA-F-]{36}',rid):
            try:
                full=request('musicbrainz_lookup', f'https://musicbrainz.org/ws/2/recording/{rid}',
                             {'inc':'releases+artist-credits+isrcs','fmt':'json'})
                releases=full.get('releases') or []
            except ProviderError:
                raise
            except Exception:
                releases=[]
        # Prefer the same named album, but return multiple releases for a user
        # to choose. Release identity is never synthesized from source titles.
        if releases:
            before=len(found)
            releases=sorted(releases,key=lambda x:SequenceMatcher(None,
                one(q.get('album')).casefold(), one(x.get('title')).casefold()).ratio()
                if q.get('album') else 0,reverse=True)
            for rel in releases[:10]:
                if not re.fullmatch(r'[0-9a-fA-F-]{36}',one(rel.get('id'))):continue
                found.append(item('musicbrainz',e.get('title'),credit(e.get('artist-credit')),
                    rel.get('title'),e.get('length'),(e.get('isrcs') or [''])[0],
                    rid, f'https://musicbrainz.org/release/{rel.get("id")}',
                    credit(rel.get('artist-credit')),rel.get('id'),
                    release_date=rel.get('date',''),country=rel.get('country',''),
                    barcode=rel.get('barcode',''),edition=rel.get('disambiguation','')))
        if not releases or len(found)==before:
            found.append(item('musicbrainz',e.get('title'),credit(e.get('artist-credit')),
                '',e.get('length'),(e.get('isrcs') or [''])[0],rid,
                f'https://musicbrainz.org/recording/{rid}'))
    return found[:18]


def _deezer_details(candidate, raw, q, request):
    """Resolve one strongly matching Deezer track and album from official API.

    Enrich with ISRC, album artist, real positions and label rather than
    assuming that /search already contains a complete album/recording.
    """
    def valid_id(v):
        return str(v) if isinstance(v,int) and not isinstance(v,bool) and 0 < v <= 10**16-1 else ''
    rid=valid_id(raw.get('id'))
    album_id=valid_id((raw.get('album') or {}).get('id')) if isinstance(raw.get('album'),dict) else ''
    if not rid:return
    detail=request('deezer_track',f'https://api.deezer.com/track/{rid}',{})
    if not isinstance(detail,dict) or not isinstance(detail.get('artist'),dict):
        raise ValueError('Deezer track detail schema invalid')
    if (SequenceMatcher(None,one(q.get('title')).casefold(),one(detail.get('title')).casefold()).ratio()<.9
        or SequenceMatcher(None,one(q.get('artist')).casefold(),
                           one(detail['artist'].get('name')).casefold()).ratio()<.9):
        candidate['enrichment_status']='CONFLICT'
        return
    fields={'isrc':one(detail.get('isrc')).upper()[:14],
            'tracknumber':_number(detail.get('track_position')),
            'discnumber':_number(detail.get('disk_number')),
            'release_date':one(detail.get('release_date'))[:40]}
    for field,value in fields.items():
        if value:candidate[field]=value
    actual_album=detail.get('album') or {}
    if isinstance(actual_album,dict):
        new_album=one(actual_album.get('title'))
        new_id=valid_id(actual_album.get('id'))
        if new_album and (not candidate['album'] or new_album.casefold()==candidate['album'].casefold()):
            candidate['album']=new_album[:300]
            if new_id:album_id=new_id
    if album_id:
        album=request('deezer_album',f'https://api.deezer.com/album/{album_id}',{})
        if not isinstance(album,dict) or not isinstance(album.get('title'),str):
            raise ValueError('Deezer album detail schema invalid')
        if candidate['album'] and SequenceMatcher(None,candidate['album'].casefold(),album['title'].casefold()).ratio()<.86:
            candidate['enrichment_status']='ALBUM_CONFLICT'
            return
        for field,source in (('release_date','release_date'),('barcode','upc'),
                             ('totaltracks','nb_tracks'),('label','label')):
            raw_value=album.get(source)
            value=_number(raw_value,9999) if field=='totaltracks' else one(raw_value)
            if value:candidate[field]=value[:180]
        candidate['provider_album_id']=album_id
        creator=album.get('artist')
        if isinstance(creator,dict):
            credit_name=one(creator.get('name'))
            if credit_name and credit_name.casefold() not in ('deezer','spotify','apple music'):
                candidate['albumartist']=credit_name[:300]
    candidate['enrichment_status']='COMPLETE'


def deezer(q, request, credentials):
    payload=request('deezer','https://api.deezer.com/search',
                    {'q': f'{q["artist"]} {q["title"]}', 'limit': 6})
    def duration(e):
        try:return 1000*max(0,min(10000,float(e.get('duration') or 0)))
        except (TypeError,ValueError,OverflowError):return 0
    raw_rows=rows(payload,'data')
    found=[item('deezer', e.get('title'), (e.get('artist') or {}).get('name'),
                 (e.get('album') or {}).get('title'), duration(e),
                 e.get('isrc'),url=e.get('link',''),
                 provider_album_id=(e.get('album') or {}).get('id',''),
                 release_url=(e.get('album') or {}).get('tracklist',''),
                 release_date=(e.get('album') or {}).get('release_date',''),
                 tracknumber=e.get('track_position'),discnumber=e.get('disk_number'),
                 totaltracks=(e.get('album') or {}).get('nb_tracks',''),
                 genre=(e.get('album') or {}).get('genre',''),
                 label=(e.get('album') or {}).get('label',''))
           for e in raw_rows]
    # Maximum one extra track and album lookup per six-result search.
    for candidate,raw in zip(found,raw_rows):
        if (isinstance(raw.get('id'),int)
            and SequenceMatcher(None,one(q.get('title')).casefold(),candidate['title'].casefold()).ratio()>=.92
            and SequenceMatcher(None,one(q.get('artist')).casefold(),candidate['artist'].casefold()).ratio()>=.92
            and (not q.get('album') or not candidate.get('album')
                 or SequenceMatcher(None,one(q['album']).casefold(),candidate['album'].casefold()).ratio()>=.86)):
            _deezer_details(candidate,raw,q,request)
            break
    return found


def itunes(q, request, credentials):
    payload = request('itunes', 'https://itunes.apple.com/search',
                      {'term': f'{q["artist"]} {q["title"]}', 'country': 'DE',
                       'media': 'music', 'entity': 'song', 'limit': 6})
    return [item('itunes',e.get('trackName'),e.get('artistName'),e.get('collectionName'),
                 e.get('trackTimeMillis'),url=e.get('trackViewUrl', ''),
                 albumartist=e.get('collectionArtistName', ''),
                 provider_album_id=e.get('collectionId',''),
                 release_url=e.get('collectionViewUrl',''),release_date=e.get('releaseDate',''),
                 tracknumber=e.get('trackNumber'),discnumber=e.get('discNumber'),
                 totaltracks=e.get('trackCount'),totaldiscs=e.get('discCount'),
                 genre=e.get('primaryGenreName',''),composer=e.get('composerName',''))
            for e in rows(payload,'results')]


def spotify(q,request,credentials):
    with _AUTH_LOCKS['spotify']:
        return _spotify(q,request,credentials)


def _spotify(q, request, credentials):
    token = one(credentials.get('spotify_access_token'))
    if not token:
        cid = one(credentials.get('spotify_client_id'))
        secret = one(credentials.get('spotify_client_secret'))
        if not cid or not secret:
            return None
        auth = 'Basic ' + base64.b64encode(f'{cid}:{secret}'.encode()).decode()
        payload = request('spotify_auth', 'https://accounts.spotify.com/api/token',
                          {}, headers={'Authorization': auth,
                                       'Content-Type': 'application/x-www-form-urlencoded'},
                          form={'grant_type': 'client_credentials'})
        token = one(payload.get('access_token'))
        if not token:raise ValueError('token response missing access token')
        # Held only in memory (never cached to disk).
        credentials['spotify_access_token'] = token
        credentials['spotify_token_until'] = time.time() + min(3600, int(payload.get('expires_in',3600))) - 90
    elif credentials.get('spotify_token_until', 0) and time.time() >= credentials['spotify_token_until']:
        credentials.pop('spotify_access_token', None)
        return _spotify(q,request,credentials)
    payload = request('spotify', 'https://api.spotify.com/v1/search',
                      {'q': f'track:{q["title"]} artist:{q["artist"]}', 'type': 'track', 'limit': 5},
                      headers={'Authorization': 'Bearer ' + token})
    return [item('spotify',e.get('name'), ', '.join(a.get('name','') for a in e.get('artists',[])),
                 (e.get('album') or {}).get('name'), e.get('duration_ms'),
                 (e.get('external_ids') or {}).get('isrc'),
                 url=(e.get('external_urls') or {}).get('spotify', ''),
                 albumartist=', '.join(a.get('name','') for a in (e.get('album') or {}).get('artists',[])),
                 provider_album_id=(e.get('album') or {}).get('id',''),
                 release_url=((e.get('album') or {}).get('external_urls') or {}).get('spotify',''),
                 release_date=(e.get('album') or {}).get('release_date',''),
                 tracknumber=e.get('track_number'),discnumber=e.get('disc_number'),
                 totaltracks=(e.get('album') or {}).get('total_tracks',''))
            for e in rows(payload.get('tracks'),'items')]


def soundcloud(q,request,credentials):
    with _AUTH_LOCKS['soundcloud']:
        return _soundcloud(q,request,credentials)


def _soundcloud(q,request,credentials):
    token = one(credentials.get('soundcloud_token'))
    try:expires=float(credentials.get('soundcloud_token_until') or 0)
    except (TypeError,ValueError):raise ProviderError('invalid_token',attempted=False) from None
    if not token or (expires and time.time()>=expires) or (
            not expires and credentials.get('soundcloud_refresh_token')):
        cid=one(credentials.get('soundcloud_client_id'))
        secret=one(credentials.get('soundcloud_client_secret'))
        refresh=one(credentials.get('soundcloud_refresh_token'))
        if not cid or not secret:
            if token:raise ProviderError('credentials_missing')
            return None
        if credentials.get('soundcloud_refresh_pending'):raise ProviderError('refresh_uncertain')
        headers={'Content-Type':'application/x-www-form-urlencoded'}
        form={'grant_type':'client_credentials'}
        ticket=None
        if refresh:
            owner=getattr(request,'__self__',None)
            if hasattr(owner,'reserve_auth'):ticket=owner.reserve_auth('soundcloud_auth')
            marker=hashlib.sha256(refresh.encode()).hexdigest()
            # Persist consumed/uncertain state BEFORE making a single-use request.
            try:persist_soundcloud({'soundcloud_refresh_pending':marker})
            except (OSError,RuntimeError,ValueError):raise ProviderError('vault_unavailable') from None
            credentials['soundcloud_refresh_pending']=marker
            form={'grant_type':'refresh_token','client_id':cid,'client_secret':secret,'refresh_token':refresh}
        else:
            headers['Authorization']='Basic '+base64.b64encode(f'{cid}:{secret}'.encode()).decode()
        reserved={'_reservation':ticket} if ticket is not None else {}
        try:
            payload=request('soundcloud_auth','https://secure.soundcloud.com/oauth/token',{},
                            headers=headers,form=form,**reserved)
        except ProviderError as exc:
            if refresh and not exc.attempted:
                try:persist_soundcloud({'soundcloud_refresh_pending':''})
                except (OSError,RuntimeError,ValueError):raise ProviderError('vault_unavailable') from None
                credentials.pop('soundcloud_refresh_pending',None)
            raise
        token=one(payload.get('access_token'))
        rotated=one(payload.get('refresh_token'))
        if not token or not rotated:raise ProviderError('invalid_token')
        updated={'soundcloud_token':token,'soundcloud_refresh_token':rotated,
                 'soundcloud_token_until':str(time.time()+max(1,min(3600,int(payload.get('expires_in',3600)))-60)),
                 'soundcloud_refresh_pending':''}
        try:persist_soundcloud(updated)
        except (OSError,RuntimeError,ValueError):
            raise ProviderError('vault_unavailable') from None
        credentials.update(updated)
    payload = request('soundcloud', 'https://api.soundcloud.com/tracks',
                      {'q':f'{q["artist"]} {q["title"]}','limit':6},
                      headers={'Authorization':'OAuth '+token})
    if isinstance(payload,list): data=payload
    elif isinstance(payload,dict) and ('collection' in payload or 'data' in payload):
        data=payload.get('collection', payload.get('data'))
    else:raise ValueError('catalog response schema invalid')
    if not isinstance(data,list) or not all(isinstance(e,dict) for e in data[:6]):
        raise ValueError('catalog response schema invalid')
    return [item('soundcloud',e.get('title'),
                 (e.get('publisher_metadata') or {}).get('artist')
                 or (e.get('user') or {}).get('username'),
                 (e.get('publisher_metadata') or {}).get('album_title',''),
                 e.get('duration'),(e.get('publisher_metadata') or {}).get('isrc',''),
                 url=e.get('permalink_url',''),
                 provider_album_id=(e.get('publisher_metadata') or {}).get('album_id',''),
                 release_date=(e.get('publisher_metadata') or {}).get('release_date',''),
                 genre=e.get('genre',''),
                 label=(e.get('publisher_metadata') or {}).get('label_name') or e.get('label_name',''),
                 composer=(e.get('publisher_metadata') or {}).get('composer',''))
            for e in data[:6]]


def lastfm(q,request,credentials):
    key = one(credentials.get('lastfm_api_key'))
    if not key: return None
    payload = request('lastfm', 'https://ws.audioscrobbler.com/2.0/',
                      {'method':'track.search', 'artist':q['artist'], 'track':q['title'],
                       'api_key':key, 'format':'json', 'limit':6})
    if not isinstance(payload,dict) or not isinstance(payload.get('results'),dict):
        raise ValueError('catalog response schema invalid')
    matches=payload['results'].get('trackmatches')
    if not isinstance(matches,dict):
        if str(payload['results'].get('opensearch:totalResults',''))=='0':data=[]
        else:raise ValueError('catalog response schema invalid')
    else:
        data=matches.get('track')
        if data in (None,'') and str(payload['results'].get('opensearch:totalResults',''))=='0':data=[]
    if isinstance(data,dict): data=[data]
    if not isinstance(data,list) or not all(isinstance(e,dict) for e in data[:6]):
        raise ValueError('catalog response schema invalid')
    found=[]
    for index,e in enumerate(data[:6]):
        candidate=item('lastfm',e.get('name'),e.get('artist'),
                       mbid=e.get('mbid'),url=e.get('url',''))
        # track.search omits album. A bounded official track.getInfo
        # lookup enriches album identity, making Last.fm release-comparable.
        promising=(SequenceMatcher(None,one(q['artist']).casefold(),candidate['artist'].casefold()).ratio()>.9
                   and SequenceMatcher(None,one(q['title']).casefold(),candidate['title'].casefold()).ratio()>.9)
        if index < 1 and promising:
            try:
                details=request('lastfm','https://ws.audioscrobbler.com/2.0/',
                    {'method':'track.getInfo','artist':candidate['artist'],
                     'track':candidate['title'],'api_key':key,'format':'json'})
                track=details.get('track') or {}
                if isinstance(track,dict):
                    album=track.get('album') or {}
                    if isinstance(album,dict):
                        candidate['album']=one(album.get('title'))[:300]
                        candidate['albumartist']=one(album.get('artist'))[:300]
                        candidate['provider_album_id']=one(album.get('mbid'))[:110]
                        candidate['release_url']=one(album.get('url'))[:800]
                    genres=(track.get('toptags') or {}).get('tag',[])
                    if isinstance(genres,dict):genres=[genres]
                    if isinstance(genres,list):
                        candidate['genre']=_genre(genres)
            except ProviderError:
                raise
            except Exception:
                pass  # Keep usable search results when enrichment is unavailable.
        found.append(candidate)
    return found

ADAPTERS = {
    'musicbrainz':musicbrainz, 'deezer':deezer, 'itunes':itunes,
    'spotify':spotify, 'soundcloud':soundcloud, 'lastfm':lastfm,
}


def env_credentials():
    # Environment overrides are process-local; never written to config, cache or log.
    return {'spotify_client_id':os.environ.get('NEOWULF_SPOTIFY_CLIENT_ID',''),
            'spotify_client_secret':os.environ.get('NEOWULF_SPOTIFY_CLIENT_SECRET',''),
            'soundcloud_token':os.environ.get('NEOWULF_SOUNDCLOUD_ACCESS_TOKEN',''),
            'soundcloud_client_id':os.environ.get('NEOWULF_SOUNDCLOUD_CLIENT_ID',''),
            'soundcloud_client_secret':os.environ.get('NEOWULF_SOUNDCLOUD_CLIENT_SECRET',''),
            'soundcloud_refresh_token':os.environ.get('NEOWULF_SOUNDCLOUD_REFRESH_TOKEN',''),
            'soundcloud_token_until':os.environ.get('NEOWULF_SOUNDCLOUD_TOKEN_UNTIL',''),
            'lastfm_api_key':os.environ.get('NEOWULF_LASTFM_API_KEY','')}
