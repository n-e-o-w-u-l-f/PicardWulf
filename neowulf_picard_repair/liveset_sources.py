"""Official Mixcloud metadata *suggestions* for DJ/LiveSets.

Only the documented public JSON API is accessed; never scrape HTML, stream
audio, fetch tracks, guess a provider identity or change Picard tags.
Network calls are opt-in and occur in the standalone command or an explicit
background job, not inside Picard's GUI thread.
"""
from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
import json
import re
from typing import Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .album_routing import route_album

API = 'https://api.mixcloud.com/search/'
_MAX_BODY = 256_000
_WORDS = re.compile(r'[^\w]+',re.UNICODE)


def _norm(value: object) -> str:
    return ' '.join(_WORDS.sub(' ',str(value or '').casefold()).split())


def _similar(a: str,b: str) -> float:
    return SequenceMatcher(None,_norm(a),_norm(b)).ratio()


def public_mixcloud_request(query: Mapping[str,str]) -> Mapping:
    """One bounded documented HTTPS API read, no redirects off Mixcloud."""
    from urllib.parse import urlparse
    url = API+'?'+urlencode(dict(query))
    req=Request(url,headers={'Accept':'application/json','User-Agent':'PicardWulf-live-metadata/1.0'})
    with urlopen(req,timeout=8) as response:
        if urlparse(response.geturl()).hostname != 'api.mixcloud.com':
            raise ValueError('provider redirect to untrusted host')
        if response.status != 200:
            raise ValueError('provider unsuccessful response')
        raw=response.read(_MAX_BODY+1)
    if len(raw)>_MAX_BODY:
        raise ValueError('provider response too large')
    out=json.loads(raw.decode('utf-8'))
    if not isinstance(out,dict) or not isinstance(out.get('data'),list):
        raise ValueError('provider search schema invalid')
    return out


def lookup_mixcloud(artist: str,title: str,*,fetch: Callable = public_mixcloud_request,
                    minimum_similarity: float = 0.85) -> dict[str,object]:
    """Return a source-linked suggestion ONLY if both title and DJ match.

    Official Mixcloud search offers cloudcast/show metadata publicly without
    auth. Usernames are not release credits; the returned author must agree
    with the *requested* DJ or the result is not authoritative.
    """
    if not 0.75 <= minimum_similarity <= 1.0:
        raise ValueError('invalid threshold')
    if not artist or not title or len(artist)>120 or len(title)>180:
        return {'status':'ABSTAIN','reason':'incomplete_query','matches':[]}
    data=fetch({'q':f'{artist} {title}','type':'cloudcast','limit':'5'})
    if not isinstance(data,dict) or not isinstance(data.get('data'),list):
        raise ValueError('provider search schema invalid')
    matches=[]
    for row in data['data'][:5]:
        if not isinstance(row,dict):
            continue
        user=row.get('user')
        if not isinstance(user,dict):
            continue
        dj=str(user.get('name') or user.get('username') or '').strip()
        name=str(row.get('name') or '').strip()
        if not dj or not name:
            continue
        # Never permit substring artist spoofing ("DJ X" / "DJ XYZ") or
        # generic 'Live Set' alone to override an unrelated original.
        artist_score=_similar(artist,dj)
        title_score=_similar(title,name)
        if artist_score < 0.91 or title_score < minimum_similarity:
            continue
        date_str=str(row.get('created_time') or row.get('publish_date') or '')
        date_match=re.match(r'^(\d{4}-\d{2}-\d{2})',date_str)
        day=date_match.group(1) if date_match else ''
        if day:
            try: datetime.strptime(day,'%Y-%m-%d')
            except ValueError: day=''
        link=str(row.get('url') or '')
        if not link.startswith('https://www.mixcloud.com/'):
            continue
        meta={'album':name,'albumartist':dj,'artist':dj,
              'date':day, 'is_liveset':True}
        plan=route_album(meta)
        if plan.review:
            continue
        matches.append({
            'source':'mixcloud','source_url':link,
            'title':name,'artist':dj,'date':day,
            'duration_seconds':max(0,min(24*3600,int(row.get('audio_length') or 0)))
                if str(row.get('audio_length') or '0').isdigit() else 0,
            'score':round((artist_score+title_score)/2,3),
            'suggested_folder':plan.folder,
            'requires_confirmation':True,
        })
    matches.sort(key=lambda m:(-m['score'],m['source_url']))
    if not matches:
        return {'status':'ABSTAIN','reason':'no_verified_same_dj_show','matches':[]}
    # Multiple near-equal same-performer shows remain ambiguous. Never
    # silently choose a similar show's date for a local recording.
    if len(matches)>1 and matches[0]['score']-matches[1]['score'] < 0.08:
        return {'status':'REVIEW','reason':'multiple_matching_shows','matches':matches}
    return {'status':'SUGGESTION_ONLY','matches':matches[:1],
            'automatic_tagging':False}
