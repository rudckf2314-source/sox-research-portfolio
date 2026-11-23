"""Independent source/RAW comparison; does not import the collection/parser code."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import csv, hashlib, io, json, re, zipfile
import numpy as np

RUN=Path(__file__).resolve().parent
ROOT=RUN.parents[2]
def digest(p): return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def reference_french(path):
    # Locate contiguous eight-digit daily blocks independently of the publisher's state machine.
    text=path.read_text(encoding='utf-8-sig'); result={}
    for match in re.finditer(r'(?m)^[ \t]*,([^\r\n]+)\r?\n((?:[ \t]*\d{8},[^\r\n]*(?:\r?\n|$))+)',text):
        columns=['Date']+[v.strip() for v in next(csv.reader([','+match[1]]))[1:]]
        prefix=text[:match.start()]
        table='EW' if prefix.rfind('Average Equal Weighted Returns -- Daily')>prefix.rfind('Average Value Weighted Returns -- Daily') else ('VW' if 'Average Value Weighted Returns -- Daily' in prefix else 'Daily')
        data={}
        for r in csv.reader(io.StringIO(match[2])):
            key=datetime.strptime(r[0].strip(),'%Y%m%d').strftime('%Y-%m-%d')
            if key>='2010-01-01': data[key]=[None if Decimal(v.strip()) in (Decimal('-99.99'),Decimal('-999')) else Decimal(v.strip()) for v in r[1:]]
        result[table]=(columns,data)
    return result
def check():
    issues=[]; checks=[]
    baseline=load(RUN/'PROTECTED_INPUT_HASHES.json')
    changed=[p for p,h in baseline.items() if not (ROOT/p).is_file() or digest(ROOT/p)!=h]
    issues += ['Protected file changed: '+p for p in changed]
    additional=load(RUN/'ADDITIONAL_EXISTING_RESEARCH_HASHES.json')
    additional_changed=[p for p,h in additional.items() if not (ROOT/p).is_file() or digest(ROOT/p)!=h]
    issues += ['Existing research file changed: '+p for p in additional_changed]
    manifest=list(csv.DictReader((RUN/'ACADEMIC_RAW_COLLECTION_MANIFEST.csv').open(encoding='utf-8-sig')))
    for r in manifest:
        if digest(ROOT/r['file'])!=r['sha256']: issues.append('Manifest hash mismatch: '+r['file'])
    for ds in load(RUN/'ACADEMIC_RAW_COLLECTION_QC.json')['datasets']:
        if ds['status']!='SUCCESS': continue
        folder=ROOT/'data/raw'/ds['dataset_id']; original=folder/'source_original'
        numeric_matches=0
        if ds['dataset_id'].startswith(('43','44','45')):
            archive=next(original.glob('*.zip'))
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
                for name in z.namelist():
                    if name.lower().endswith('.csv'): assert z.read(name)==(original/Path(name).name).read_bytes()
            reference=reference_french(next(original.glob('*.csv')))
            assert len(reference)==len(ds['outputs'])
        elif ds['dataset_id'].startswith(('46','47')):
            candidates=[]
            for p in original.glob('*CHART_HTTP*.json'):
                obj=load(p)
                if obj.get('chart',{}).get('result'):
                    candidates.append(obj['chart']['result'][0])
            chart=max(candidates,key=lambda x:len(x.get('timestamp',[])))
            quote=chart['indicators']['quote'][0]; adj=chart['indicators']['adjclose'][0]['adjclose']
            data={}
            for i,stamp in enumerate(chart['timestamp']):
                day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                data[day]=[quote[c][i] for c in ['open','high','low','close']]+[adj[i],quote['volume'][i]]
            reference={'Daily':(['Date','Open','High','Low','Close','Adj Close','Volume'],data)}
            with next((folder/'actions').glob('*.csv')).open(encoding='utf-8') as f:
                assert f.readline().startswith('# SOURCE')
                events=list(csv.DictReader(f))
            listed={r['Date']:r for r in events}
            for category,column in [('dividends','Dividends'),('splits','Stock Splits'),('capitalGains','Capital Gains')]:
                for event in chart.get('events',{}).get(category,{}).values():
                    day=datetime.fromtimestamp(event['date'],timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                    expected=event['numerator']/event['denominator'] if category=='splits' else event['amount']
                    assert day in listed and np.isclose(float(listed[day][column]),expected,rtol=1e-14,atol=1e-12)
        else:
            source=next(p for p in original.glob('*.csv'))
            with source.open(encoding='utf-8-sig') as f:
                reader=csv.reader(f); cols=next(reader)
                data={r[0]:[None if r[1] in ('','.') else Decimal(r[1])] for r in reader if r[0]>='2010-01-01'}
            reference={'Native':(['Date',ds['symbol']],data)}
        summaries=[]
        for output in ds['outputs']:
            path=ROOT/output['file']
            with path.open(encoding='utf-8') as f:
                assert f.readline().startswith('# SOURCE | ')
                reader=csv.reader(f); header=next(reader); rows=list(reader)
            refcols, ref=reference[output['table']]
            assert header==refcols
            dates=[r[0] for r in rows]
            assert dates==sorted(set(dates)) and set(dates)==set(ref)
            assert (len(rows),min(dates),max(dates))==(output['rows'],output['min_date'],output['max_date'])
            missing=0
            for r in rows:
                for value,expected in zip(r[1:],ref[r[0]],strict=True):
                    if expected is None:
                        assert value==''; missing+=1
                    elif isinstance(expected,Decimal):
                        assert Decimal(value)==expected, (path,r[0],value,expected)
                    else:
                        assert np.isclose(float(value),expected,rtol=1e-14,atol=1e-12),(path,r[0],value,expected)
                    numeric_matches+=1
            assert missing==output['missing_cells']
            summaries.append({'file':output['file'],'rows':len(rows),'min_date':min(dates),'max_date':max(dates),'missing_cells':missing,'source_values_match':True})
        checks.append({'dataset_id':ds['dataset_id'],'status':'PASS','compared_numeric_cells':numeric_matches,'tables':summaries})
    result={'status':'PASS' if not issues else 'FAIL','protected_files_checked':len(baseline),'protected_changed':changed,
            'additional_existing_research_files_checked':len(additional),'additional_existing_research_changed':additional_changed,
            'manifest_files_checked':len(manifest),'datasets':checks,'issues':issues,
            'historical_vintage_verified':False,'models_or_features_built':0}
    (RUN/'ACADEMIC_RAW_INDEPENDENT_QC.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    assert not issues,issues
    print(json.dumps({'status':result['status'],'datasets':len(checks),'protected_files':len(baseline),'numeric_cells':sum(x['compared_numeric_cells'] for x in checks)}))
if __name__=='__main__': check()
