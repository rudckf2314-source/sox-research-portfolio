"""기록이 없는 후기 평일의 연준 공식 월별 일정·예외 추가 조사."""
from concurrent.futures import ThreadPoolExecutor
from collect_evidence import fetch,save

def main():
    jobs=[('fed_gap_2015_april','https://www.federalreserve.gov/newsevents/2015-april.htm'),
          ('fed_gap_2017_january','https://www.federalreserve.gov/newsevents/2017-january.htm'),
          ('fed_gap_2018_march','https://www.federalreserve.gov/newsevents/2018-march.htm'),
          ('fed_gap_2018_december','https://www.federalreserve.gov/newsevents/2018-december.htm'),
          ('fed_gap_2020_december','https://www.federalreserve.gov/newsevents/2020-december.htm'),
          ('fed_gap_2021_december','https://www.federalreserve.gov/newsevents/2021-december.htm'),
          ('fed_gap_2024_december','https://www.federalreserve.gov/newsevents/2024-december.htm'),
          ('fed_gap_2025_january','https://www.federalreserve.gov/newsevents/2025-january.htm')]
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(lambda x:fetch(*x),jobs))
    save('sources/H15_GAP_DOCUMENTS.json',{'sources':records,'scope':'일별 자료가 촘촘해진 이후의 추가 미기록 평일9개 관련8개월 공식 일정 조사. 자동 자료 채움 없음.'})
    print([(r['id'],r.get('http_status')) for r in records])

if __name__=='__main__':main()
