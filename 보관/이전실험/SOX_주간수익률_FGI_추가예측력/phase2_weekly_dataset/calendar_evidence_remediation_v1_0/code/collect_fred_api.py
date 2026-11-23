"""사용자 추가 로컬 FRED 키로 공식 release/dates 전 페이지 수집. 비밀은 저장/출력하지 않는다."""
import os
import re
from datetime import datetime, timezone
import requests
from collect_evidence import ROOT,OUT,save,sha

def main():
    if (OUT/'sources/FRED_API_COLLECTION.json').exists():
        raise SystemExit('기존 API 수집 완료 기록 보존')
    settings=dict(os.environ)
    for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
        m=re.match(r'^\s*(FRED_API_KEY|FRED_KEY)\s*=\s*(.*?)\s*$',line)
        if m:
            settings.setdefault(m[1],m[2].strip('"\''))
    key=settings.get('FRED_API_KEY') or settings.get('FRED_KEY')
    assert key,'FRED 키 값 없음'
    results=[]
    for include in [False,True]:
        offset=0; count=None; pages=[]; status='COLLECTING'
        while count is None or offset<count:
            public={'release_id':18,'file_type':'json','sort_order':'asc','limit':1000,'offset':offset,
                    'include_release_dates_with_no_data':str(include).lower()}
            try:
                res=requests.get('https://api.stlouisfed.org/fred/release/dates',params={**public,'api_key':key},timeout=(10,35))
                data=res.json()
            except Exception as e:
                status='ACCESS_FAILED_'+type(e).__name__
                break
            if res.status_code!=200 or 'release_dates' not in data:
                status='API_ERROR_HTTP_'+str(res.status_code)
                break
            assert key not in res.text,'키 포함 응답은 저장하지 않음'
            current=int(data['count']); limit=int(data['limit'])
            assert int(data['offset'])==offset and limit==1000 and (count is None or count==current)
            assert all(int(x['release_id'])==18 for x in data['release_dates'])
            p=OUT/'sources/originals'/f'fred_api_include_{str(include).lower()}_offset_{offset}.json'
            with p.open('xb') as f:
                f.write(res.content)
            pages.append({'public_endpoint':'https://api.stlouisfed.org/fred/release/dates','public_parameters':public,
                'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'http_status':res.status_code,
                'count':current,'limit':limit,'offset':offset,'rows':len(data['release_dates']),
                'body_file':p.relative_to(OUT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size})
            count=current; offset+=limit
        dates=[]
        for page in pages:
            import json
            dates.extend(x['date'] for x in json.loads((OUT/page['body_file']).read_text())['release_dates'])
        if count is not None and sum(p['rows'] for p in pages)==count and len(dates)==len(set(dates)) and dates==sorted(dates):
            status='COLLECTED_PAGINATION_VERIFIED'
        results.append({'include_release_dates_with_no_data':include,'status':status,'count':count,'pages':pages,
                        'collected_rows':len(dates),'duplicates':len(dates)-len(set(dates)),'ascending':dates==sorted(dates)})
    save('sources/FRED_API_COLLECTION.json',{'release_id':18,'key_source':'승인된 로컬 환경변수/.env',
        'secret_saved_or_printed':False,'prior_no_key_record_preserved':True,'runs':results})
    print([{'include_no_data':r['include_release_dates_with_no_data'],'status':r['status'],'count':r['count'],
            'pages':len(r['pages'])} for r in results])

if __name__=='__main__':
    main()
