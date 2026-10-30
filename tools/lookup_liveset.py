"""Opt-in, read-only Mixcloud show search and candidate LiveSets folders.

Usage: python tools/lookup_liveset.py --artist "DJ X" --title "Boiler Room Set"
No downloads, local filesystem reads, Picard changes or automatic tag writes.
Needs only standard-library Python and the publicly documented Mixcloud API.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import types


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artist',required=True)
    parser.add_argument('--title',required=True)
    args=parser.parse_args()
    # The installed Picard plugin __init__ imports PyQt6, which an ordinary
    # command-line read-only lookup must not depend on.
    folder=Path(__file__).resolve().parents[1]/'neowulf_picard_repair'
    name='_picardwulf_offline_liveset'
    package=types.ModuleType(name)
    package.__path__=[str(folder)]
    sys.modules[name]=package
    source=importlib.import_module(name+'.liveset_sources')
    result=source.lookup_mixcloud(args.artist,args.title)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['status']=='SUGGESTION_ONLY' else 2


if __name__=='__main__':
    raise SystemExit(main())
