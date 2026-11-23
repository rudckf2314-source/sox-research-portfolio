"""실패한 공개 문서의 기본 HTTP 요청 재시도. 첫 실패 기록은 보존한다."""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from collect_evidence import OUT,fetch,load,save

def main():
    old_path=OUT/'sources/H15_SOURCE_REGISTER.json'
    if not old_path.exists():
        raise SystemExit('초기 수집 완료 후 실행')
    if (OUT/'sources/H15_SOURCE_REGISTER_FINAL.json').exists():
        raise SystemExit('완료된 재시도를 덮어쓰지 않습니다.')
    initial=load(old_path)
    retry=[(r['id']+'_retry_default',r['requested_url']) for r in initial['sources'] if r['status']=='ACCESS_FAILED']
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(lambda x:fetch(*x),retry))
    for year in [2025,2026]:
        first=next((r for r in initial['sources'] if r['id']==f'fred_calendar_{year}_1'),None)
        if first and first.get('http_status')==200:
            continue
        r=next((r for r in records if r['id']==f'fred_calendar_{year}_1_retry_default'),None)
        if not r or r.get('http_status')!=200:
            continue
        s=BeautifulSoup((OUT/r['body_file']).read_bytes(),'html.parser')
        more={urljoin(r['final_url'],a.get('href','')) for a in s.find_all('a')
              if re.fullmatch(r'\d+',a.get_text(strip=True)) and 'pageID=' in a.get('href','')}
        with ThreadPoolExecutor(max_workers=3) as pool:
            records+=list(pool.map(lambda u:fetch(f'fred_calendar_{year}_'+re.search(r'pageID=(\d+)',u).group(1)+'_retry_default',u),sorted(more)))
    save('sources/H15_SOURCE_REGISTER_FINAL.json',{
        'release_id':18,'initial_register':'sources/H15_SOURCE_REGISTER.json',
        'retry_reason':'일부 사용자에이전트 설정 요청 연결 실패 후 기본 요청 설정으로 재시도. 실패 원인을 서버 정책으로 확정하지 않음.',
        'sources':initial['sources']+records,
        'original_failure_records_preserved':True})
    print('Initial:',len(initial['sources']),'retry requests:',len(records),'retry200:',sum(r.get('http_status')==200 for r in records))

if __name__=='__main__':
    main()
