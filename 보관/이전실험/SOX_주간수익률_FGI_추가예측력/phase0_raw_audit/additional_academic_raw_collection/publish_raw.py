"""Validate downloaded source tables, then publish NEW RAW folders only."""
from pathlib import Path
import csv, hashlib, io, json, re, shutil, zipfile
from datetime import datetime, timezone
import pandas as pd
import numpy as np

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]
FRED = {
    'ICSA': ('Number; seasonally adjusted', 'Weekly, ending Saturday', 'U.S. Department of Labor'),
    'CPIAUCSL': ('Index 1982-1984=100; seasonally adjusted', 'Monthly', 'U.S. Bureau of Labor Statistics'),
    'CPILFESL': ('Index 1982-1984=100; seasonally adjusted', 'Monthly', 'U.S. Bureau of Labor Statistics'),
    'PAYEMS': ('Thousands of persons; seasonally adjusted', 'Monthly', 'U.S. Bureau of Labor Statistics'),
    'UNRATE': ('Percent; seasonally adjusted', 'Monthly', 'U.S. Bureau of Labor Statistics'),
}
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def js(p, x):
    p.write_text(json.dumps(x, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
def french_tables(body):
    lines = body.decode('utf-8-sig').splitlines()
    tables, name, header, rows = [], 'Daily', None, []
    for line in lines:
        if 'Average Value Weighted Returns -- Daily' in line: name = 'VW'
        elif 'Average Equal Weighted Returns -- Daily' in line: name = 'EW'
        fields = [v.strip() for v in next(csv.reader([line]))]
        if fields and fields[0] == '' and len(fields)>1:
            if header is not None and rows: tables.append((name_old, header, rows))
            header, rows, name_old = ['Date'] + fields[1:], [], name
        elif fields and re.fullmatch(r'\d{8}', fields[0]) and header:
            assert len(fields) == len(header), fields
            date = datetime.strptime(fields[0], '%Y%m%d').date().isoformat()
            rows.append([date] + ['' if v in ('-99.99','-999','-999.00') else v for v in fields[1:]])
    if header and rows: tables.append((name_old, header, rows))
    return tables
def quality(header, rows):
    df = pd.DataFrame(rows, columns=header)
    dates = pd.to_datetime(df.Date, errors='raise')
    values = df.drop(columns='Date').apply(pd.to_numeric, errors='raise')
    assert len(df)>0 and dates.notna().all() and not dates.duplicated().any() and dates.is_monotonic_increasing
    arr = values.to_numpy(dtype=float)
    assert not np.isinf(arr).any()
    return dict(rows=len(df), min_date=dates.min().date().isoformat(), max_date=dates.max().date().isoformat(),
                duplicate_dates=int(dates.duplicated().sum()), missing_cells=int(values.isna().sum().sum()),
                missing_by_column={k:int(v) for k,v in values.isna().sum().items()}, columns=header,
                max_calendar_gap_days=int(dates.diff().dt.days.max()),
                absolute_values_over_100_cells=int((values.abs()>100).sum().sum()),
                min_by_column={k:None if pd.isna(v) else float(v) for k,v in values.min().items()},
                max_by_column={k:None if pd.isna(v) else float(v) for k,v in values.max().items()})
def save_table(dest, meta, header, rows):
    qc = quality(header, rows)
    with dest.open('w', encoding='utf-8', newline='') as f:
        f.write('# SOURCE | ' + ' | '.join(f'{k}={v}' for k,v in meta.items()) + '\n')
        w=csv.writer(f, lineterminator='\n'); w.writerow(header); w.writerows(rows)
    return qc
def main():
    plan=json.loads((RUN/'COLLECTION_PLAN.json').read_text(encoding='utf-8'))
    fetched=json.loads((RUN/'FETCH_RESULTS.json').read_text(encoding='utf-8'))
    results, manifest = [], []
    for spec in plan['sources']:
        ds, kind, sym = spec['dataset_id'],spec['kind'],spec['symbol']
        result=fetched.get(ds,{})
        if result.get('status') not in ('FETCHED','CACHED'):
            results.append(dict(dataset_id=ds,status=result.get('status','NOT_FETCHED'),errors=result.get('errors',[])))
            continue
        destination=ROOT/'data/raw'/ds
        if destination.exists(): raise FileExistsError(destination)
        stage=RUN/'validated_staging'/ds
        stage.mkdir(parents=True, exist_ok=True)
        original=stage/'source_original'; original.mkdir(exist_ok=True)
        cache=RUN/'download_cache'/ds
        for p in cache.iterdir():
            if p.is_file(): shutil.copyfile(p, original/p.name)
        tables=[]
        retrieved=result.get('retrieved_at_utc',result.get('fetched_at_utc','UNKNOWN'))
        provider = 'Kenneth R. French Data Library' if kind=='french' else ('Yahoo Finance' if kind=='yahoo' else 'FRED')
        extra={}
        if kind=='french':
            archive=original/spec['filename']
            with zipfile.ZipFile(archive) as z:
                members=[n for n in z.namelist() if n.lower().endswith('.csv')]
                assert len(members)==1
                body=z.read(members[0]); member=Path(members[0]).name
                (original/member).write_bytes(body)
            payload_sha=sha(archive)
            parsed=french_tables(body)
            assert len(parsed)==(2 if ds.startswith('43') else 1)
            for label,header,all_rows in parsed:
                expected=50 if ds.startswith('43') else (7 if ds.startswith('44') else 2)
                assert len(header)==expected
                rows=[r for r in all_rows if r[0]>='2010-01-01']
                full_dates=[r[0] for r in all_rows]
                assert full_dates==sorted(set(full_dates))
                extra[label]={'full_source_rows':len(all_rows),'full_source_min':all_rows[0][0], 'full_source_max':all_rows[-1][0],
                              'full_source_missing_cells':sum(v=='' for r in all_rows for v in r[1:]),
                              'canonical_abs_return_over_100_flags':sum(v!='' and abs(float(v))>100 for r in rows for v in r[1:])}
                tables.append((label,header,rows))
            if ds.startswith('43'): assert [r[0] for r in tables[0][2]]==[r[0] for r in tables[1][2]]
            unit, frequency, administrator='Percent; original published scale retained','Daily','Kenneth R. French / CRSP inputs'
        elif kind=='yahoo':
            with (original/f'{sym}_YFINANCE_RETURN.csv').open(encoding='utf-8-sig',newline='') as f:
                source=list(csv.DictReader(f))
            payload_sha=result['chart_http_responses'][-1]['sha256']
            header=['Date','Open','High','Low','Close','Adj Close','Volume']
            rows=[[r['Date'][:10]]+[r[c] for c in header[1:]] for r in source]
            assert all(r[0] < result['end_exclusive_et_date'] for r in rows)
            values=pd.DataFrame(rows,columns=header).drop(columns='Date').apply(pd.to_numeric)
            assert values.notna().all().all() and (values>=0).all().all()
            assert (values.drop(columns='Volume')>0).all().all() and (values.Volume%1==0).all()
            assert ((values.High>=values[['Open','Close','Low']].max(axis=1)) & (values.Low<=values[['Open','Close','High']].min(axis=1))).all()
            tables.append(('Daily',header,rows))
            actioncols=[c for c in ['Dividends','Stock Splits','Capital Gains'] if c in source[0]]
            events=[[r['Date'][:10]]+[r[c] for c in actioncols] for r in source if any(float(r[c])!=0 for c in actioncols)]
            (stage/'actions').mkdir()
            with (stage/'actions'/f'{sym}_CORPORATE_ACTIONS.csv').open('w',encoding='utf-8',newline='') as f:
                f.write(f'# SOURCE | provider=Yahoo Finance | series_or_symbol={sym} | transformation=nonzero provider corporate-action rows only; no rescaling\n')
                w=csv.writer(f,lineterminator='\n'); w.writerow(['Date']+actioncols);w.writerows(events)
            extra={'actions_rows':len(events),'auto_adjust':False,'repair':False,'end_exclusive_et_date':result['end_exclusive_et_date']}
            unit,frequency,administrator='USD prices; shares volume','Daily','Yahoo Finance; exchange/vendor market data'
        else:
            with (original/spec['filename']).open(encoding='utf-8-sig',newline='') as f:
                reader=csv.reader(f); sourceheader=next(reader); all_rows=list(reader)
            payload_sha=sha(original/spec['filename'])
            assert sourceheader in (['observation_date',sym],['DATE',sym]), sourceheader
            rows=[[r[0],'' if r[1] in ('.','') else r[1]] for r in all_rows if r[0]>='2010-01-01']
            tables.append(('Native',['Date',sym],rows))
            numeric=pd.to_numeric(pd.Series([r[1] for r in rows]))
            assert (numeric.dropna()>0).all()
            if sym=='UNRATE': assert (numeric.dropna()<=100).all()
            dates=pd.to_datetime([r[0] for r in rows])
            if sym=='ICSA': assert (dates.dayofweek==5).all() and ((dates[1:]-dates[:-1]).days==7).all()
            else: assert (dates.day==1).all() and len(pd.period_range(dates.min(),dates.max(),freq='M'))==len(dates)
            unit,frequency,administrator=FRED[sym]
            extra={'full_source_rows':len(all_rows),'full_source_min_date':all_rows[0][0],
                   'full_source_max_date':all_rows[-1][0],'observation_date_is_not_release_date':True}
        outputs=[]
        for label,header,rows in tables:
            suffix=f'_{label}' if kind=='french' and ds.startswith('43') else ''
            filename=f'{ds}{suffix}_RAW_{rows[0][0].replace("-", "")}_{rows[-1][0].replace("-", "")}.csv'
            metadata=dict(dataset_id=ds,provider=provider,administrator=administrator,source_url=spec['url'],series_or_symbol=sym,
                          table=label,unit=unit,frequency=frequency,start_date=rows[0][0],end_date=rows[-1][0],retrieved_at_utc=retrieved,
                          source_original_sha256=payload_sha,
                          vintage='current revised archive; historical point-in-time availability UNVERIFIED',
                          transformation='source columns preserved; date ISO format; documented missing markers to empty; no scaling or interpolation')
            qc=save_table(stage/filename,metadata,header,rows)
            outputs.append(dict(file=(destination/filename).relative_to(ROOT).as_posix(),table=label,sha256=sha(stage/filename),**qc))
        info=dict(dataset_id=ds,status='SUCCESS',provider=provider,source_url=spec['url'],symbol=sym,unit=unit,frequency=frequency,
                  administrator=administrator,outputs=outputs,details=extra,
                  original_sha256={p.name:sha(p) for p in original.iterdir() if p.is_file()},
                  availability_status='UNVERIFIED_HISTORICAL_PUBLICATION_AND_VINTAGE')
        js(stage/'RAW_METADATA.json',info)
        # New directories only: all validation above completes before publication.
        assert destination.resolve().is_relative_to((ROOT/'data/raw').resolve())
        assert stage.resolve().is_relative_to((RUN/'validated_staging').resolve())
        # Windows sandbox can deny directory rename despite allowing file writes.
        # Publish into a previously absent directory; retain validated staging for audit.
        shutil.copytree(stage,destination)
        for p in destination.rglob('*'):
            if p.is_file():
                out=next((o for o in outputs if o['file']==p.relative_to(ROOT).as_posix()),{})
                manifest.append(dict(dataset_id=ds,file=p.relative_to(ROOT).as_posix(),role='canonical' if out else ('source_original' if 'source_original' in p.parts else 'metadata_or_actions'),
                                     bytes=p.stat().st_size,sha256=sha(p),provider=provider,source_url=spec['url'],unit=unit,frequency=frequency,rows=out.get('rows',''),min_date=out.get('min_date',''),max_date=out.get('max_date','')))
        results.append(info)
        print(ds,'SUCCESS',[(o['table'],o['rows'],o['min_date'],o['max_date']) for o in outputs],flush=True)
    js(RUN/'ACADEMIC_RAW_COLLECTION_QC.json',{'datasets':results,'model_or_feature_operations':0})
    with (RUN/'ACADEMIC_RAW_COLLECTION_MANIFEST.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['dataset_id','file','role','bytes','sha256','provider','source_url','unit','frequency','rows','min_date','max_date']);w.writeheader();w.writerows(manifest)
    print('Published',sum(r['status']=='SUCCESS' for r in results),'of',len(results),flush=True)
if __name__=='__main__': main()
