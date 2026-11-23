"""공식 H.15 게시일 근거 수집 전용. 금융 RAW/주간 변수는 생성하지 않는다."""
import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[2]
BUILD=OUT.parent/'build_v1_0'
LOCK=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
APPROVAL=OUT.parent/'prebuild_D10_audit/approval_v1_0'
INSTRUCTION=Path(r'C:\Users\rudck\.codex\attachments\9b67ba8d-5a55-4441-901b-85488610ad1a\Pasted text.txt')
ALLOWED={'fred.stlouisfed.org','alfred.stlouisfed.org','api.stlouisfed.org','www.federalreserve.gov','www.opm.gov','www.nyse.com'}

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def save(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8',newline='\n') as f:
        f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def prepare():
    for d in ['sources','sources/originals','code','audit','qc','reports','logs']:
        (OUT/d).mkdir(parents=True,exist_ok=True)
    if (OUT/'qc/INPUT_MANIFEST.json').exists():
        raise SystemExit('기존 실행 덮어쓰기 금지')
    old=load(BUILD/'inputs/PHASE2B_INPUT_MANIFEST.json')
    protected=dict(old['protected_files'])
    seal=load(BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.json')
    assert all(sha(BUILD/r['path'])==r['sha256'] for r in seal['files'])
    assert sha(BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.json')==(BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for p in [BUILD/r['path'] for r in seal['files']]+[BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.json',BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.sha256']:
        protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    mismatch=[r for r,v in protected.items() if not (ROOT/r).exists() or sha(ROOT/r)!=v['sha256']]
    assert not mismatch,mismatch
    refs=[LOCK/'PHASE1_LOCKED_SPEC_v1_1.md',OUT.parent/'prebuild_D10_audit/reports/PHASE2A_D10_REPORT.md',
          APPROVAL/'D10_APPROVED_POLICY.md',APPROVAL/'D10_APPROVED_POLICY.json',
          BUILD/'reports/PHASE2B_REPORT.md',BUILD/'qc/PHASE2B_INDEPENDENT_QC.md',INSTRUCTION]
    reads=[]
    for p in refs:
        body=p.read_text(encoding='utf-8-sig')
        reads.append({'path':str(p),'sha256':sha(p),'characters':len(body),'entire_file_read':True})
    (OUT/'sources/USER_INSTRUCTION.txt').write_bytes(INSTRUCTION.read_bytes())
    save('qc/INPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'H15 역사적 게시달력 근거 보완만. 주간변수/라벨/전체Phase2-B/모델/D13 미실행.',
        'protected_files':protected,'full_read_log':reads,'baseline_mismatches':mismatch,
        'original_D10_policy_sha256':sha(APPROVAL/'D10_APPROVED_POLICY.json'),
        'original_D10_gate_sha256':sha(APPROVAL/'D10_GATE_STATUS.json'),
        'runtime':{'python':sys.version,'requests':requests.__version__,'executable':sys.executable}})
    print('Prepared; protected files:',len(protected))

def fetch(name,url):
    assert urlparse(url).hostname in ALLOWED
    rec={'id':name,'requested_url':url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    p=OUT/'sources/originals'/f'{name}.body'
    if p.exists():
        return load(OUT/'sources/originals'/f'{name}.metadata.json')
    try:
        res=requests.get(url,timeout=(10,25))
        assert urlparse(res.url).hostname in ALLOWED
        p.write_bytes(res.content)
        rec.update({'http_status':res.status_code,'final_url':res.url,'bytes':len(res.content),
            'body_file':p.relative_to(OUT).as_posix(),'sha256':sha(p),
            'headers':{k:v for k,v in res.headers.items() if k.lower() in {'content-type','content-length','date','last-modified','etag','content-disposition'}},
            'status':'HTTP_SUCCESS_REQUIRES_CONTENT_VALIDATION' if res.status_code==200 else 'HTTP_ERROR'})
    except Exception as e:
        rec.update({'status':'ACCESS_FAILED','error_type':type(e).__name__,
            'note':'실패 URL과 예외 종류만 보관. 자료 부재로 단정하지 않음.'})
    save('sources/originals/'+name+'.metadata.json',rec)
    return rec

def collect():
    assert (OUT/'qc/INPUT_MANIFEST.json').exists()
    if (OUT/'sources/H15_SOURCE_REGISTER.json').exists():
        raise SystemExit('이미 수집 완료한 버전. 새 버전에서 수행하십시오.')
    # 키는 읽어도 출력/저장하지 않는다. 현재 환경에서는 알려진 키가 없다.
    local=dict(os.environ)
    env_file=ROOT/'.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            match=re.match(r'^\s*(FRED_API_KEY|FRED_KEY)\s*=\s*(.*?)\s*$',line)
            if match:
                local.setdefault(match[1],match[2].strip('"\''))
    key=local.get('FRED_API_KEY') or local.get('FRED_KEY')
    api={'endpoint':'https://api.stlouisfed.org/fred/release/dates','release_id':18,
         'file_type':'json','sort_order':'asc','include_release_dates_with_no_data':False,
         'requested_limit':10000,'requested_offset':0,'api_key_present':bool(key),
         'status':'SKIPPED_NO_API_KEY' if not key else 'READY','pagination_status':'NOT_APPLICABLE_API_NOT_USED','pages':[]}
    if key:
        offset=0; total=None
        while total is None or offset<total:
            params={'release_id':18,'file_type':'json','sort_order':'asc','limit':10000,'offset':offset,
                    'include_release_dates_with_no_data':'false','api_key':key}
            try:
                res=requests.get(api['endpoint'],params=params,timeout=(10,45))
                obj=res.json()
            except Exception as e:
                api.update(status='ACCESS_FAILED',error_type=type(e).__name__)
                break
            if res.status_code!=200 or 'release_dates' not in obj:
                api.update(status='API_ERROR',http_status=res.status_code)
                break
            path=OUT/'sources/originals'/f'fred_api_offset_{offset}.json'
            # 응답에는 요청 키가 없어야 한다. 안전상 있으면 저장하지 않는다.
            assert key not in res.text
            path.write_bytes(res.content)
            count=int(obj['count']); limit=int(obj['limit']); actual_offset=int(obj['offset'])
            assert actual_offset==offset and limit>0 and (total is None or total==count)
            assert all(x['release_id']==18 for x in obj['release_dates'])
            total=count
            api['pages'].append({'count':count,'limit':limit,'offset':offset,'rows':len(obj['release_dates']),
                'path':path.relative_to(OUT).as_posix(),'sha256':sha(path)})
            offset+=limit
            api.update(status='COLLECTED',pagination_status='CHECK_COUNT_LIMIT_OFFSET_COMPLETE')
        if api['status']=='COLLECTED':
            api['pagination_complete']=sum(x['rows'] for x in api['pages'])==total
    save('sources/FRED_API_ACCESS_STATUS.json',api)
    jobs=[
        ('fred_api_docs','https://fred.stlouisfed.org/docs/api/fred/release_dates.html'),
        ('alfred_release','https://alfred.stlouisfed.org/release?rid=18'),
        ('alfred_download_page','https://alfred.stlouisfed.org/release/downloaddates?rid=18'),
        ('alfred_release_dates_txt','https://alfred.stlouisfed.org/release/downloaddates?rid=18&ff=txt'),
        ('fed_current','https://www.federalreserve.gov/releases/h15/'),
        ('fed_announcements','https://www.federalreserve.gov/feeds/h15.html'),
        ('fed_archive_index','https://www.federalreserve.gov/newsevents/calendar-archive.htm'),
        ('fed_k8','https://www.federalreserve.gov/aboutthefed/k8.htm'),
        ('fed_2026_october','https://www.federalreserve.gov/newsevents/2026-october.htm'),
        ('fred_calendar_old_request','https://fred.stlouisfed.org/releases/calendar?rid=18&y=2011'),
        ('alfred_calendar_old_request','https://alfred.stlouisfed.org/releases/calendar?rid=18&y=2011'),
        ('fred_calendar_old_vs','https://fred.stlouisfed.org/releases/calendar?rid=18&vs=2011-01-01&ve=2011-12-31'),
        ('nyse_official','https://www.nyse.com/markets/hours-calendars'),
        ('opm_holidays','https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/')]
    # 역사 개별 공식 게시자료 표본. 실패/다른 날짜 응답은 E1로 올리지 않는다.
    for d in ['20100104','20110110','20120625','20140106','20150302','20160119','20161011','20180918','20230913','20261009']:
        jobs.append(('fed_release_'+d,'https://www.federalreserve.gov/releases/h15/'+d+'/'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(lambda x:fetch(*x),jobs))
    # FRED 공개 연간 캘린더는 실제 반환한 제목과 count/페이지를 검증한다.
    # 과거 y 요청이 최근 연도로 제한될 수 있어2011로 오인하지 않는다.
    for year in [2025,2026]:
        rec=fetch(f'fred_calendar_{year}_1',f'https://fred.stlouisfed.org/releases/calendar?rid=18&y={year}')
        records.append(rec)
        if rec.get('http_status')!=200:
            continue
        soup=BeautifulSoup((OUT/rec['body_file']).read_bytes(),'html.parser')
        more={urljoin(rec['final_url'],a.get('href','')) for a in soup.find_all('a')
              if re.fullmatch(r'\d+',a.get_text(strip=True)) and 'pageID=' in a.get('href','')}
        with ThreadPoolExecutor(max_workers=4) as pool:
            records += list(pool.map(lambda u:fetch(f'fred_calendar_{year}_'+re.search(r'pageID=(\d+)',u).group(1),u),sorted(more)))
    save('sources/H15_SOURCE_REGISTER.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'release_id':18,'API_access_record':'sources/FRED_API_ACCESS_STATUS.json',
        'sources':records,'calendar_output_is_not_final_approved_calendar':True,
        'initial_sandbox_probe':'기본 네트워크 WinError10013. 승인된 공개자료 수집을 네트워크 허용 실행으로 수행. 자료 부재와 구별.'})
    print(json.dumps({'source_requests':len(records),'http200':sum(x.get('http_status')==200 for x in records),
        'API_status':api['status']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','collect'])
    args=parser.parse_args()
    {'prepare':prepare,'collect':collect}[args.stage]()
