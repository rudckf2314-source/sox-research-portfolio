"""ALFRED 2011 공개 달력의 마지막 페이지 수집 절차. 기존 응답은 덮어쓰지 않는다."""
from collect_evidence import OUT, fetch, save

if __name__ == '__main__':
    if (OUT/'sources/H15_SOURCE_REGISTER_SUPPLEMENT.json').exists():
        raise SystemExit('기존 추가 페이지 기록 보존. 새 수집은 별도 실행 폴더 사용.')
    record = fetch('alfred_calendar_2011_page2',
        'https://alfred.stlouisfed.org/releases/calendar?rid=18&y=2011&pageID=2')
    save('sources/H15_SOURCE_REGISTER_SUPPLEMENT.json', {'sources': [record]})
