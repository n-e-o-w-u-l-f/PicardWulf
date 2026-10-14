"""Opt-in read-only public-catalog probe. No user files, credentials or raw response cache.

NOT part of unittest discovery. Three anonymous queries with a fixed public
classical-music search term. Emits aggregate status only, never track metadata.
"""
import importlib
import json
from pathlib import Path
import sys
import types

ROOT=Path(__file__).parents[1]
pkg=types.ModuleType('public_probe');pkg.__path__=[str(ROOT/'neowulf_picard_repair')]
sys.modules['public_probe']=pkg
engine=importlib.import_module('public_probe.universal_engine')

def run():
    client=engine.HTTPClient()
    queries={
        'musicbrainz':('https://musicbrainz.org/ws/2/recording/',
                      {'query':'recording:"Air" AND artist:"Bach"','fmt':'json','limit':1},'recordings'),
        'deezer':('https://api.deezer.com/search',{'q':'Bach Air','limit':1},'data'),
        'itunes':('https://itunes.apple.com/search',
                  {'term':'Bach Air','country':'DE','media':'music','entity':'song','limit':1},'results')}
    output={}
    for source,(url,params,key) in queries.items():
        try:
            data=client.request(source,url,params)
            if not isinstance(data,dict) or not isinstance(data.get(key),list):
                raise engine.ProviderError('response_invalid')
            output[source]={'state':'AVAILABLE','observed':True,'result_count':len(data[key])}
        except engine.ProviderError as exc:
            output[source]={'state':exc.state,'observed':exc.attempted,'reason':exc.reason}
    for source in ('spotify','soundcloud','lastfm'):
        output[source]={'state':'UNAVAILABLE_FOR_THIS_VALIDATION','observed':False,
                        'reason':'No legitimate credentials supplied to the probe; no purchase or registration.'}
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':run()
