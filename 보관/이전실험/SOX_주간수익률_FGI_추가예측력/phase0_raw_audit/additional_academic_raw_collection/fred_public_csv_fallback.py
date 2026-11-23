"""Single bounded request per series to FRED's standard full-history CSV link.

Only run after the date-filtered URL's three attempts have failed. No authentication,
proxy, third-party mirror, alternative indicator, or challenge bypass is used.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,sys
from concurrent.futures import ThreadPoolExecutor
import requests
RUN=Path(__file__).resolve().parent
ROOT=RUN.parents[2]
def fetch(spec):
    url='https://fred.stlouisfed.org/graph/fredgraph.csv?id='+spec['symbol']
    try:
        r=requests.get(url,timeout=(8,20))
        info={'request_url':url,'response_url':r.url,'http_status':r.status_code,'headers':dict(r.headers),
              'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(r.content)}
        r.raise_for_status()
        assert r.content.lstrip().startswith((b'observation_date,',b'DATE,')), 'Not an official CSV response'
        folder=RUN/'download_cache'/spec['dataset_id'];folder.mkdir(parents=True,exist_ok=True)
        p=folder/spec['filename'];assert not p.exists();p.write_bytes(r.content)
        info.update(file=str(p.relative_to(ROOT)),sha256=hashlib.sha256(r.content).hexdigest())
        (folder/'HTTP_RESPONSE_METADATA.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
        return spec['dataset_id'],dict(status='FETCHED',**info)
    except Exception as e:
        return spec['dataset_id'],{'status':'ERROR','message':str(e),'type':type(e).__name__,'request_url':url}
if __name__=='__main__':
    results=json.loads((RUN/'FETCH_RESULTS.json').read_text(encoding='utf-8'))
    path=RUN/'FRED_FULL_HISTORY_FALLBACK.json'
    fallback=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if '--merge' in sys.argv:
        for ds,outcome in fallback.items():
            if outcome['status']=='FETCHED':
                prior=results[ds]
                results[ds]={'specification':prior['specification'],**outcome,'errors':prior.get('errors',[]),
                             'fallback_reason':'Three date-filtered official CSV requests failed; standard full-history official CSV link tried once'}
        (RUN/'FETCH_RESULTS.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    else:
        sources=[s for s in json.loads((RUN/'COLLECTION_PLAN.json').read_text(encoding='utf-8'))['sources'] if s['kind']=='fred' and results.get(s['dataset_id'],{}).get('status')=='ERROR' and s['dataset_id'] not in fallback]
        with ThreadPoolExecutor(max_workers=5) as pool: fallback.update(dict(pool.map(fetch,sources)))
        path.write_text(json.dumps(fallback,indent=2),encoding='utf-8')
    print(json.dumps({k:v['status'] for k,v in fallback.items()}))
