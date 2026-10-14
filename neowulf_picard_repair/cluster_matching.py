"""Pure, source-neutral, album-group comparisons for PicardWulf v1.0.

A selection is a review candidate, never an instruction to write tags or
pretend that a non-MusicBrainz provider release has a MusicBrainz UUID.
"""
from collections import defaultdict
import re

from .auto_selection import source_neutral_score, edition_conflicts, version_markers
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
    return (norm(row.get('source')), _identifier(row),
            norm(row.get('album')), norm(row.get('albumartist') or row.get('artist')),
            version_markers(row.get('album')),
            norm(row.get('release_date')), norm(row.get('barcode')),
            norm(row.get('totaltracks')))


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
    releases=defaultdict(lambda:defaultdict(dict))
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
            # Do not let duplicate catalogue hits count as multiple album tracks.
            old=releases[key].get(i)
            if old is None or match>old[0]:
                releases[key][i]=(match,row)
    ranked=[]
    for key,by_track in releases.items():
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
