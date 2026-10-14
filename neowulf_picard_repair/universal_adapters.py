"""Official catalogue search adapters. No HTML crawling, login bypass or audio downloads.

Use only documented endpoints; credentials are optional and are never logged.
Transport is injected for tests. Result dictionaries are untrusted data.
"""
import base64
import os
import time
import re
from difflib import SequenceMatcher
from urllib.parse import urlencode

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


def item(source, title, artist, album='', duration=0, isrc='', mbid='', url='', albumartist='', release_mbid='', provider_album_id='', release_url='', release_date=''):
    try: duration = max(0, min(10_000_000, int(float(duration or 0))))
    except (TypeError, ValueError): duration = 0
    return {'source': source, 'title': one(title)[:300], 'artist': one(artist)[:300],
            'album': one(album)[:300], 'albumartist': one(albumartist)[:300],
            'duration_ms': duration, 'isrc': one(isrc).upper()[:14],
            'recording_mbid': one(mbid)[:40], 'release_mbid': one(release_mbid)[:40], 'url': one(url)[:800],
            'provider_album_id':one(provider_album_id)[:110],
            'release_url':one(release_url)[:800], 'release_date':one(release_date)[:40]}


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
    payload = request('musicbrainz', 'https://musicbrainz.org/ws/2/recording/',
                      {'query': query, 'fmt': 'json', 'limit': 6})
    found=[]
    for e in payload.get('recordings', [])[:6]:
        rid=one(e.get('id'))
        releases=e.get('releases') or []
        # Search results sometimes omit release relationships; use a bounded
        # MusicBrainz official recording lookup, not an external provider URL.
        if not releases and re.fullmatch(r'[0-9a-fA-F-]{36}',rid):
            try:
                full=request('musicbrainz_lookup', f'https://musicbrainz.org/ws/2/recording/{rid}',
                             {'inc':'releases+artist-credits+isrcs','fmt':'json'})
                releases=full.get('releases') or []
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
                    credit(rel.get('artist-credit')),rel.get('id')))
        if not releases or len(found)==before:
            found.append(item('musicbrainz',e.get('title'),credit(e.get('artist-credit')),
                '',e.get('length'),(e.get('isrcs') or [''])[0],rid,
                f'https://musicbrainz.org/recording/{rid}'))
    return found[:18]


def deezer(q, request, credentials):
    payload = request('deezer','https://api.deezer.com/search',
                      {'q': f'{q["artist"]} {q["title"]}', 'limit': 6})
    return [item('deezer', e.get('title'), (e.get('artist') or {}).get('name'),
                 (e.get('album') or {}).get('title'), 1000 * (e.get('duration') or 0),
                 e.get('isrc'), url=e.get('link', ''),
                 provider_album_id=(e.get('album') or {}).get('id',''),
                 release_url=(e.get('album') or {}).get('tracklist',''))
            for e in payload.get('data', [])[:6]]


def itunes(q, request, credentials):
    payload = request('itunes', 'https://itunes.apple.com/search',
                      {'term': f'{q["artist"]} {q["title"]}', 'country': 'DE',
                       'media': 'music', 'entity': 'song', 'limit': 6})
    return [item('itunes',e.get('trackName'),e.get('artistName'),e.get('collectionName'),
                 e.get('trackTimeMillis'),url=e.get('trackViewUrl', ''),
                 albumartist=e.get('collectionArtistName', ''),
                 provider_album_id=e.get('collectionId',''),
                 release_url=e.get('collectionViewUrl',''),release_date=e.get('releaseDate',''))
            for e in payload.get('results', [])[:6]]


def spotify(q, request, credentials):
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
        if not token: return []
        # Held only in memory (never cached to disk).
        credentials['spotify_access_token'] = token
        credentials['spotify_token_until'] = time.time() + min(3600, int(payload.get('expires_in',3600))) - 90
    elif credentials.get('spotify_token_until', 0) and time.time() >= credentials['spotify_token_until']:
        credentials.pop('spotify_access_token', None)
        return spotify(q,request,credentials)
    payload = request('spotify', 'https://api.spotify.com/v1/search',
                      {'q': f'track:{q["title"]} artist:{q["artist"]}', 'type': 'track', 'limit': 6},
                      headers={'Authorization': 'Bearer ' + token})
    return [item('spotify',e.get('name'), ', '.join(a.get('name','') for a in e.get('artists',[])),
                 (e.get('album') or {}).get('name'), e.get('duration_ms'),
                 (e.get('external_ids') or {}).get('isrc'),
                 url=(e.get('external_urls') or {}).get('spotify', ''),
                 albumartist=', '.join(a.get('name','') for a in (e.get('album') or {}).get('artists',[])),
                 provider_album_id=(e.get('album') or {}).get('id',''),
                 release_url=((e.get('album') or {}).get('external_urls') or {}).get('spotify',''),
                 release_date=(e.get('album') or {}).get('release_date',''))
            for e in (payload.get('tracks') or {}).get('items',[])[:6]]


def soundcloud(q,request,credentials):
    token = one(credentials.get('soundcloud_token'))
    if not token: return None
    payload = request('soundcloud', 'https://api.soundcloud.com/tracks',
                      {'q':f'{q["artist"]} {q["title"]}','limit':6},
                      headers={'Authorization':'OAuth '+token})
    if isinstance(payload,list): data=payload
    else: data=payload.get('collection', payload.get('data', []))
    if not isinstance(data,list): return []
    return [item('soundcloud',e.get('title'),
                 (e.get('publisher_metadata') or {}).get('artist')
                 or (e.get('user') or {}).get('username'),
                 (e.get('publisher_metadata') or {}).get('album_title',''),
                 e.get('duration'),(e.get('publisher_metadata') or {}).get('isrc',''),
                 url=e.get('permalink_url',''),
                 provider_album_id=(e.get('publisher_metadata') or {}).get('album_id',''))
            for e in data[:6]]


def lastfm(q,request,credentials):
    key = one(credentials.get('lastfm_api_key'))
    if not key: return None
    payload = request('lastfm', 'https://ws.audioscrobbler.com/2.0/',
                      {'method':'track.search', 'artist':q['artist'], 'track':q['title'],
                       'api_key':key, 'format':'json', 'limit':6})
    data = ((payload.get('results') or {}).get('trackmatches') or {}).get('track',[])
    if isinstance(data,dict): data=[data]
    found=[]
    for index,e in enumerate(data[:6]):
        candidate=item('lastfm',e.get('name'),e.get('artist'),
                       mbid=e.get('mbid'),url=e.get('url',''))
        # track.search omits album. A bounded official track.getInfo
        # lookup enriches album identity, making Last.fm release-comparable.
        if index < 2 and candidate['artist'] and candidate['title']:
            try:
                details=request('lastfm','https://ws.audioscrobbler.com/2.0/',
                    {'method':'track.getInfo','artist':candidate['artist'],
                     'track':candidate['title'],'api_key':key,'format':'json'})
                album=(details.get('track') or {}).get('album') or {}
                if isinstance(album,dict):
                    candidate['album']=one(album.get('title'))[:300]
                    candidate['albumartist']=one(album.get('artist'))[:300]
                    candidate['provider_album_id']=one(album.get('mbid'))[:110]
                    candidate['release_url']=one(album.get('url'))[:800]
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
            'lastfm_api_key':os.environ.get('NEOWULF_LASTFM_API_KEY','')}
