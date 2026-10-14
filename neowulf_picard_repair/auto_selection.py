"""Source-neutral release ranking for PicardWulf.

A source wins by evidence, not by its identity. We distinguish release
variants, disqualify incompatible identifiers and refuse ambiguous auto-apply.
No external provider ID is interpreted as a MusicBrainz MBID.
"""
from collections import defaultdict
from .universal_engine import norm, similarity

AUTO_THRESHOLD = 0.935
AUTO_GAP = 0.045
EXTERNAL_PROVIDER_NAMES = frozenset((
    'apple music','spotify','deezer','soundcloud','lastfm','last fm',
    'itunes','musicbrainz',
))

def release_identity(candidate):
    """Credit and album title distinguish editions containing the same recording."""
    return (norm(candidate.get('artist')),
            norm(candidate.get('title')),
            norm(candidate.get('album')))

def _valid_identifiers(q, candidate):
    for key in ('isrc','recording_mbid'):
        if q.get(key) and candidate.get(key) and norm(q[key]) != norm(candidate[key]):
            return False
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
    title = similarity(q.get('title'), candidate.get('title'))
    artist = similarity(q.get('artist'),candidate.get('artist'))
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
            fit += .12 * similarity(q['album'],candidate['album'])
    elif candidate.get('album'):
        fit += .07
    if q.get('albumartist') and candidate.get('albumartist'):
        fit += .025 * similarity(q['albumartist'],candidate['albumartist'])
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

def rank_candidates(q, results):
    """Score every source, then count independent corroboration per release."""
    rows = []
    by_release = defaultdict(set)
    for source,candidates in results.items():
        for c in candidates:
            row = dict(c)
            row['source'] = source  # authoritative provenance; never remote field
            row['score'] = source_neutral_score(q,row)
            row['reason'] = 'compatible' if row['score'] else 'incompatible_or_incomplete'
            rows.append(row)
            if row['score'] >= .78 and row.get('album'):
                by_release[release_identity(row)].add(source)
    for row in rows:
        support = len(by_release[release_identity(row)]) if row['score'] else 0
        row['source_support'] = max(1,support) if row['score'] else 0
        row['release_score'] = round(min(1.0,row['score'] + .016 * (support-1)),4) if row['score'] else 0.0
    # Final source-name tie-breaker is alphabetical, never MusicBrainz-first.
    rows.sort(key=lambda r:(-r['release_score'],-r['source_support'],r.get('source',''),r.get('url','')))
    return rows

def decide_auto(q, rows, status=None):
    """Require strong release match and a non-ambiguous independent runner-up."""
    status = status or {}
    healthy = [x for x in rows if x.get('release_score',0)>0]
    if not healthy:
        return {'state':'no_match','reason':'no compatible candidate'}
    winner = healthy[0]
    if winner['release_score'] < AUTO_THRESHOLD:
        return {'state':'review','reason':'confidence below auto threshold'}
    if not winner.get('album'):
        return {'state':'review','reason':'candidate does not identify an album'}
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
    if same_source_editions:
        return {'state':'ambiguous','reason':'multiple editions with distinct release IDs'}
    other = next((r for r in healthy[1:] if release_identity(r)!=release_identity(winner)),None)
    if other and winner['release_score']-other['release_score'] < AUTO_GAP:
        return {'state':'ambiguous','reason':'two different releases score similarly'}
    if not any(v in ('ok','cached','ok_crosssource_isrc') for v in status.values()) and status:
        return {'state':'review','reason':'no provider completed'}
    return {'state':'ready','reason':'unambiguous high-confidence release',
            'source':winner['source'],'candidate':winner,'score':winner['release_score']}
