"""기존 접근실패와 구별되는 공식 대체 URL 근거 수집."""
from concurrent.futures import ThreadPoolExecutor
from collect_calendar_sources import fetch
from common import save
if __name__=='__main__':
    jobs=[('bush_trader','https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2018-99'),
          ('carter_trader','https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-632'),
          ('juneteenth_rule','https://listingcenter.nasdaq.com/assets/rulebook/nasdaq/filings/SR-NASDAQ-2021-093.pdf'),
          ('juneteenth2022','https://indexes.nasdaq.com/docs/June2022_rebalance_schedule.pdf')]
    with ThreadPoolExecutor(max_workers=4) as ex:r=list(ex.map(fetch,jobs))
    save('inputs/EXCHANGE_SUPPLEMENT_REGISTER.json',{'sources':r})
    print({x['id']:x.get('http_status',x.get('status')) for x in r})
