"""공식 거래소 일정 근거를 신규 입력 폴더에 보존. 금융 데이터 재수집 없음."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import requests
from common import OUT,save,sha
URLS={
 'nasdaq_current':'https://www.nasdaqtrader.com/trader.aspx?id=Calendar',
 'nyse_rules':'https://www.nyse.com/publicdocs/nyse/regulation/nyse/NYSE_Rules.pdf',
 'nasdaq_2011':'https://www.nasdaqtrader.com/TraderNews.aspx?id=dn2010-030',
 'sandy29':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2012-44',
 'sandy30':'https://www.nasdaqtrader.com/TraderNews.aspx?id=mfqsnews2012-003',
 'bush':'https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-announces-closure-its-us-markets-honor-national-day',
 'carter':'https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-announces-closure-its-us-markets-honor-national-day-0',
 'july2014':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2014-43',
 'nyse_2020_2022':'https://s2.q4cdn.com/154085107/files/doc_news/archive/91a5230f-7233-4a93-b30a-79c9411ebdbe.pdf',
 'nasdaq2025':'https://www.nasdaq.com/docs/2025/01/06/2025holidayandtradinghours.pdf'}
URLS.update({f'nyse_{year}':f'https://www.nyse.com/publicdocs/ICE_NYSE_{year}_Yearly_Trading_Calendar.pdf' for year in range(2011,2027)})
def fetch(item):
    key,url=item;rec={'id':key,'url':url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        res=requests.get(url,timeout=(10,25));p=OUT/'inputs/sources'/f'{key}.body'
        with p.open('xb') as f:f.write(res.content)
        rec.update({'http_status':res.status_code,'body_file':p.relative_to(OUT).as_posix(),'sha256':sha(p),'headers':dict(res.headers)})
    except requests.RequestException as e:rec.update({'status':'ACCESS_FAILED','error_type':type(e).__name__})
    return rec
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as ex:records=list(ex.map(fetch,URLS.items()))
    save('inputs/EXCHANGE_SOURCE_REGISTER.json',{'sources':records})
    print({r['id']:r.get('http_status',r.get('status')) for r in records})
