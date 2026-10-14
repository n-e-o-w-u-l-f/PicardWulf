"""Source-neutral release ranking for PicardWulf.

A source wins by evidence, not by its identity. We distinguish release
variants, disqualify incompatible identifiers and refuse ambiguous auto-apply.
No external provider ID is interpreted as a MusicBrainz MBID.
"""
from collections import defaultdict
import hashlib
import json
import re
from .universal_engine import norm, similarity

AUTO_THRESHOLD = 0.935
AUTO_GAP = 0.045
MODEL = 'release-v2'
WEIGHTS = {'title':.44,'artist':.34,'album':.12,'albumartist':.025,
           'duration':.065,'isrc':.015,'recording_mbid':.015,'corroboration':.016}
EDITION_FIELDS = ('albumartist','release_date','country','barcode','edition',
                  'tracknumber','totaltracks','discnumber','totaldiscs')

def version_markers(value):
    """Preserve semantic variants; punctuation/accent normalization is harmless."""
    text=norm(value)
    return tuple(sorted(set(re.findall(
        r'\b(?:live|remix|clean|explicit|remaster(?:ed)?|instrumental|acoustic|demo|mono|stereo|deluxe|expanded|anniversary|bonus)\b',text))))

def matching_text(value):
    # Normalize credit spelling, never discard collaborators or version words.
    return re.sub(r'\b(?:featuring|ft)\b','feat',norm(value))

def text_similarity(a,b):
    return similarity(matching_text(a),matching_text(b))

def breakdown(q,c):
    if not source_neutral_score(q,c):return {'disqualified':0.0}
    parts={'title':.44*text_similarity(q.get('title'),c.get('title')),
           'artist':.34*text_similarity(q.get('artist'),c.get('artist'))}
    parts['album']=.12*text_similarity(q.get('album'),c.get('album')) if q.get('album') else .07 if c.get('album') else 0
    parts['albumartist']=.025*text_similarity(q.get('albumartist'),c.get('albumartist')) if q.get('albumartist') and c.get('albumartist') else .015 if not q.get('albumartist') else 0
    a,b=int(q.get('duration_ms') or 0),int(c.get('duration_ms') or 0)
    parts['duration']=.065*max(0,1-abs(a-b)/25000) if a and b else 0
    for key in ('isrc','recording_mbid'):parts[key]=.015 if q.get(key) and c.get(key) else 0
    parts['filename_penalty']=-.055 if q.get('inferred_filename') else 0
    return {k:round(v,6) for k,v in parts.items()}

def edition_value(candidate,key):
    value=norm(candidate.get(key))
    if key=='albumartist' and not value:value=norm(candidate.get('artist'))
    if key=='release_date':
        match=re.match(r'\d{4}(?: \d{1,2}){0,2}$',value)
        return match.group() if match else value
    if key in ('tracknumber','discnumber','totaltracks','totaldiscs'):
        match=re.match(r'0*(\d+)',value)
        return str(int(match.group())) if match else value
    return value

def edition_conflicts(a,b):
    conflicts=[]
    for key in EDITION_FIELDS:
        if key=='albumartist' and (not a.get(key) or not b.get(key)):continue
        left,right=edition_value(a,key),edition_value(b,key)
        if not left or not right:continue
        if key=='release_date':
            size=min(len(left.split()),len(right.split()))
            if left.split()[:size]==right.split()[:size]:continue
        if left!=right:conflicts.append(key)
    return conflicts

def decision_identity(candidate):
    """Provider IDs are namespaced, never interpreted as recording/release UUIDs."""
    data=(candidate.get('source'), candidate.get('release_mbid') if candidate.get('source')=='musicbrainz'
          else candidate.get('provider_album_id'), release_identity(candidate))
    return hashlib.sha256(json.dumps(data,ensure_ascii=True).encode()).hexdigest()

def consensus_cache_key(q):
    if not q.get('album'):return None
    fields=(norm(q.get('album')),edition_value(q,'albumartist'),
            tuple(edition_value(q,k) for k in EDITION_FIELDS if k not in ('albumartist','tracknumber','discnumber')))
    return hashlib.sha256(('release-v2-consensus|'+json.dumps(fields)).encode()).hexdigest()
EXTERNAL_PROVIDER_NAMES = frozenset((
    'apple music','spotify','deezer','soundcloud','lastfm','last fm',
    'itunes','musicbrainz',
))

def release_identity(candidate):
    """Credit and album title distinguish editions containing the same recording."""
    return (norm(candidate.get('artist')),
            norm(candidate.get('title')),
            norm(candidate.get('album')),
            tuple(edition_value(candidate,k) for k in EDITION_FIELDS),
            version_markers(candidate.get('title')),version_markers(candidate.get('album')))

def _valid_identifiers(q, candidate):
    for key in ('isrc','recording_mbid'):
        if q.get(key) and candidate.get(key) and norm(q[key]) != norm(candidate[key]):
            return False
    if candidate.get('source')=='musicbrainz' and q.get('release_mbid') and candidate.get('release_mbid'):
        if norm(q['release_mbid'])!=norm(candidate['release_mbid']):return False
    return True

def source_neutral_score(q, candidate):
    """0–1 fit: no MusicBrainz preference or non-comparable provider trust boost."""
    if not candidate.get('source') or not candidate.get('artist') or not candidate.get('title'):
        return 0.0
    if candidate.get('enrichment_status') in ('CONFLICT','ALBUM_CONFLICT'):
        return 0.0
    if norm(candidate.get('artist')) in EXTERNAL_PROVIDER_NAMES:
        return 0.0
    if norm(candidate.get('albumartist')) in EXTERNAL_PROVIDER_NAMES:
        return 0.0
    if not _valid_identifiers(q, candidate):
        return 0.0
    if edition_conflicts(q,candidate):return 0.0
    if any(version_markers(q.get(k))!=version_markers(candidate.get(k))
           for k in ('title','album') if q.get(k) and candidate.get(k)):return 0.0
    title = text_similarity(q.get('title'), candidate.get('title'))
    artist = text_similarity(q.get('artist'),candidate.get('artist'))
    if title < .82 or artist < .86:
        return 0.0
    # A Various Artists *album* is not evidence that a solo recording's
    # album artist should be overwritten. Keep such candidates for review.
    if norm(candidate.get('albumartist')) == 'various artists' and (
        q.get('albumartist') and norm(q['albumartist']) != 'various artists'
    ):
        return 0.0
    fit = .44 * title + .34 * artist
    if q.get('album'):
        if candidate.get('album'):
            fit += .12 * text_similarity(q['album'],candidate['album'])
    elif candidate.get('album'):
        fit += .07
    if q.get('albumartist') and candidate.get('albumartist'):
        fit += .025 * text_similarity(q['albumartist'],candidate['albumartist'])
    elif not q.get('albumartist'):
        fit += .015
    length_q = int(q.get('duration_ms') or 0)
    length_c = int(candidate.get('duration_ms') or 0)
    if length_q and length_c:
        difference = abs(length_q-length_c)
        if difference > 25000:
            return 0.0
        fit += .065 * max(0.,1.-difference/25000.)
    if q.get('isrc') and candidate.get('isrc'):
        fit += .015
    if q.get('recording_mbid') and candidate.get('recording_mbid'):
        fit += .015
    if q.get('inferred_filename'):
        fit -= .055
    return round(max(0.0,min(1.0,fit)),4)

def rank_candidates(q, results, album_evidence=()):
    """Score every source, then count independent corroboration per release."""
    rows = []
    by_release = defaultdict(set)
    for source,candidates in results.items():
        for c in candidates:
            row = dict(c)
            row['source'] = source  # authoritative provenance; never remote field
            row['score'] = source_neutral_score(q,row)
            row['model']=MODEL
            row['weights']=dict(WEIGHTS)
            row['score_breakdown']=breakdown(q,row)
            row['edition_conflicts']=edition_conflicts(q,row)
            row['reason'] = 'compatible' if row['score'] else 'incompatible_or_incomplete'
            rows.append(row)
            if row['score'] >= .78 and row.get('album'):
                # Missing edition fields do not prove cross-source equivalence.
                by_release[release_identity(row)].add(source)
    for row in rows:
        support = len(by_release[release_identity(row)]) if row['score'] else 0
        row['source_support'] = max(1,support) if row['score'] else 0
        row['release_score'] = round(min(1.0,row['score'] + .016 * (support-1)),4) if row['score'] else 0.0
        row['score_breakdown']['corroboration']=.016*max(0,support-1) if row['score'] else 0
        # Count distinct sibling recordings only in the SAME provider album.
        # Never use one song/ISRC or a shared album name as album consensus.
        album_id=row.get('release_mbid') if row.get('source')=='musicbrainz' else row.get('provider_album_id')
        siblings=set()
        recording=norm(row.get('recording_mbid') or row.get('isrc'))
        for sibling in album_evidence:
            sibling_id=sibling.get('release_mbid') if sibling.get('source')=='musicbrainz' else sibling.get('provider_album_id')
            sibling_recording=norm(sibling.get('recording_mbid') or sibling.get('isrc'))
            if (album_id and sibling_id==album_id and sibling.get('source')==row.get('source')
                    and norm(sibling.get('album'))==norm(row.get('album'))
                    and edition_value(sibling,'albumartist')==edition_value(row,'albumartist')
                    and norm(sibling.get('title'))!=norm(row.get('title'))
                    and sibling_recording and sibling_recording!=recording
                    and not set(edition_conflicts(row,sibling)) - {'tracknumber','discnumber'}):
                siblings.add(sibling_recording)
        row['album_support']=len(siblings)
    # Final source-name tie-breaker is alphabetical, never MusicBrainz-first.
    rows.sort(key=lambda r:(-r['release_score'],-r['source_support'],-r['album_support'],r.get('source',''),r.get('url','')))
    return rows

def _decide_auto(q, rows, status=None):
    """Require strong release match and a non-ambiguous independent runner-up."""
    status = status or {}
    healthy = [x for x in rows if x.get('release_score',0)>0]
    if not healthy:
        return {'state':'no_match','reason':'no compatible candidate'}
    winner = healthy[0]
    if not q.get('album'):
        # A recording may occur on any number of releases; identifiers do not
        # resolve which one was imported. Still surface close rivals below.
        other=next((r for r in healthy[1:] if release_identity(r)!=release_identity(winner)),None)
        if other and winner['release_score']-other['release_score'] < AUTO_GAP:
            return {'state':'ambiguous','reason':'album context missing; competing releases'}
        return {'state':'review','reason':'album context missing; recording is not release identity'}
    if winner['release_score'] < AUTO_THRESHOLD:
        return {'state':'review','reason':'matching points below auto threshold'}
    if norm(winner.get('albumartist'))=='various artists' and not q.get('albumartist'):
        return {'state':'review','reason':'album artist evidence missing for compilation'}
    if not winner.get('album'):
        return {'state':'review','reason':'candidate does not identify an album'}
    for key in EDITION_FIELDS:
        if key!='albumartist' and q.get(key) and not winner.get(key):
            return {'state':'review','reason':'release evidence missing: '+key}
    # Filename-inferred metadata is too weak for unattended overwrites.
    if q.get('inferred_filename'):
        return {'state':'review','reason':'inferred filename: verification required'}
    if q.get('album') and similarity(q['album'],winner['album']) < .83:
        return {'state':'review','reason':'existing album conflicts'}
    if q.get('albumartist') and winner.get('albumartist'):
        if similarity(q['albumartist'],winner['albumartist']) < .87:
            return {'state':'review','reason':'album artist conflict'}
    # Do not accept a single source with title+artist only when duration or
    # album information is unavailable.
    if not q.get('duration_ms') and winner['source_support'] < 2 and not q.get('isrc'):
        return {'state':'review','reason':'no independent duration or identifier'}
    # Distinct provider edition IDs or MusicBrainz release IDs can describe
    # different masters despite sharing artist, title and album text.
    edition_key='release_mbid' if winner.get('source')=='musicbrainz' else 'provider_album_id'
    winner_edition=winner.get(edition_key)
    same_source_editions=[
        r for r in healthy[1:] if r.get('source')==winner['source']
        and release_identity(r)==release_identity(winner)
        and r.get(edition_key) and winner_edition
        and r[edition_key]!=winner_edition
        and abs(r['release_score']-winner['release_score']) < AUTO_GAP]
    consensus_resolved=bool(same_source_editions and winner.get('album_support',0)>=2 and
        all(not r.get('album_support') and not edition_conflicts(winner,r)
            for r in same_source_editions))
    if same_source_editions and not consensus_resolved:
        return {'state':'ambiguous','reason':'multiple editions with distinct release IDs'}
    other = next((r for r in healthy[1:] if release_identity(r)!=release_identity(winner)),None)
    if other and winner['release_score']-other['release_score'] < AUTO_GAP:
        return {'state':'ambiguous','reason':'two different releases score similarly'}
    if not any(v in ('ok','cached','ok_crosssource_isrc') for v in status.values()) and status:
        return {'state':'review','reason':'no provider completed'}
    return {'state':'ready','reason':'unambiguous high-confidence release',
            'source':winner['source'],'candidate':winner,'score':winner['release_score'],
            'album_consensus_resolved':consensus_resolved}

def decide_auto(q,rows,status=None):
    decision=_decide_auto(q,rows,status)
    decision.update(model=MODEL,score_kind='matching_points',threshold=AUTO_THRESHOLD,
                    ranking_state={'ready':'SAFE_WINNER','ambiguous':'AMBIGUOUS',
                                   'no_match':'INCOMPLETE','review':'COMPLETE'}[decision['state']],
                    reason_code={'ready':'SAFE_RELEASE','ambiguous':'EDITION_AMBIGUOUS',
                                 'no_match':'NO_COMPATIBLE_EVIDENCE','review':'ABSTAIN'}[decision['state']])
    if decision['reason'].startswith('release evidence missing'):
        decision.update(ranking_state='INCOMPLETE',reason_code='EDITION_EVIDENCE_MISSING')
    return decision
