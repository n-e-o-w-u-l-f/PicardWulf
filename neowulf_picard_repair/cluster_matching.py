"""Pure, source-neutral, album-group comparisons for PicardWulf v1.0.

A selection is a review candidate, never an instruction to write tags or
pretend that a non-MusicBrainz provider release has a MusicBrainz UUID.
"""
from collections import defaultdict
import re

from .auto_selection import source_neutral_score, edition_conflicts, version_markers, EDITION_FIELDS
from .universal_engine import norm, similarity

MINIMUM_ALBUM_MATCH = 0.75
MINIMUM_TRACK_COVERAGE = 0.75
MAX_GROUP_TRACKS = 200


def _identifier(row):
    # IDs are NAMESPACED by their real provider. They must not be mixed.
    source=str(row.get('source') or '')
    if source=='musicbrainz':
        return str(row.get('release_mbid') or '')
    return str(row.get('provider_album_id') or '')


def _group_key(row):
    source=norm(row.get('source'))
    release_id=_identifier(row)
    album=norm(row.get('album'))
    if release_id:
        # An authoritative source-scoped album ID is the release grouping
        # anchor. Optional album detail fields differ in completeness between
        # search and album-detail endpoints; splitting by them loses real
        # tracks. Contradictory *present* fields are rejected below.
        return (source,release_id,album,version_markers(row.get('album')))
    # Never use a missing ID as proof two editions are the same. Keep the
    # fallback conservative and distinct by observable edition attributes.
    return (source,'',album,norm(row.get('albumartist') or row.get('artist')),
            version_markers(row.get('album')),norm(row.get('release_date')),
            norm(row.get('barcode')),norm(row.get('totaltracks')))


def find_similar_albums(queries, result_envelopes, *, threshold=MINIMUM_ALBUM_MATCH):
    """Return ranked provider releases matching >=75% score AND coverage.

    Candidate score is computed from actual query-to-track matching, not from
    a provider's arbitrary internal rating. One recording contributes at most
    once per release. All included sources have the same score model.
    """
    if not 0 <= threshold <= 1:
        raise ValueError('threshold must be between 0 and 1')
    count=len(queries)
    if not count or count>MAX_GROUP_TRACKS:
        return []
    releases=defaultdict(dict)
    # A provider returning mutually contradictory edition fields for the
    # *same* ID is unreliable. Do not silently merge those candidate tracks.
    release_evidence=defaultdict(dict)
    conflicting=set()
    for i,(q,data) in enumerate(zip(queries,result_envelopes)):
        if not isinstance(data,dict):
            continue
        rows=data.get('candidates') or []
        for row in rows:
            if not isinstance(row,dict) or not row.get('source') or not row.get('album'):
                continue
            if edition_conflicts(q,row):
                continue
            if q.get('album') and similarity(q['album'],row['album']) < .75:
                continue
            match=source_neutral_score(q,row)
            if match < threshold:
                continue
            key=_group_key(row)
            if not key[2]:
                continue
            # One aggregated evidence snapshot per official release ID is
            # sufficient and bounded. Pairwise 200x200 comparisons would run
            # on Picard's Qt thread every refresh. Missing optional values
            # never erase verified ones; prefer the most precise compatible
            # release date to detect conflicting month/day information.
            evidence=release_evidence[key]
            if evidence:
                conflicts=set(edition_conflicts(row,evidence))-{'tracknumber','discnumber'}
                if conflicts:
                    conflicting.add(key)
            for field in EDITION_FIELDS:
                if field in ('tracknumber','discnumber'):
                    continue  # naturally differs between album tracks
                value=row.get(field)
                if not value:
                    continue
                old_value=evidence.get(field)
                if not old_value or (field=='release_date' and len(str(value))>len(str(old_value))):
                    evidence[field]=value
            # Do not let duplicate catalogue hits count as multiple album tracks.
            old=releases[key].get(i)
            if old is None or match>old[0]:
                releases[key][i]=(match,row)
    ranked=[]
    for key,by_track in releases.items():
        if key in conflicting:
            continue
        coverage=len(by_track)/count
        if coverage<MINIMUM_TRACK_COVERAGE:
            continue
        average=sum(row[0] for row in by_track.values())/len(by_track)
        confidence=round(.7*average+.3*coverage,4)
        if confidence < threshold:
            continue
        representative=max(by_track.values(),key=lambda x:x[0])[1]
        ranked.append({'source':representative['source'],
                       'album':representative.get('album',''),
                       'albumartist':representative.get('albumartist') or representative.get('artist',''),
                       'release_id':_identifier(representative),
                       'confidence':confidence,
                       'matched_tracks':len(by_track),
                       'total_tracks':count,
                       'coverage':round(coverage,4),
                       'mean_track_score':round(average,4),
                       'release_date':representative.get('release_date',''),
                       'matched_rows':[(i,found[1]) for i,found in sorted(by_track.items())]})
    ranked.sort(key=lambda x:(-x['confidence'],-x['matched_tracks'],
                              norm(x['album']),norm(x['source']),x['release_id']))
    return ranked
