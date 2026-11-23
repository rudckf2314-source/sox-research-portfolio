"""공식 기록/규칙 추정/충돌을 분리한 날짜 근거 감사. 주간 B10 계산 없음."""
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from collect_evidence import OUT,ROOT,load,save,sha

START=date(2010,1,1)
END=date(2026,10,16)
MAIN_START=date(2011,1,1)
MAIN_END=date(2026,10,9)

def write_csv(rel,rows,fields=None):
    assert rows,'원천 실패를 빈 성공 CSV로 표시하지 않는다.'
    with (OUT/rel).open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields or list(rows[0]))
        writer.writeheader();writer.writerows(rows)

def body(rec):
    return (OUT/rec['body_file']).read_bytes()

def soup(rec):
    return BeautifulSoup(body(rec),'html.parser')

def calendar_page(rec):
    s=soup(rec); text=s.get_text(' ',strip=True)
    dates=[]
    for row in s.find_all('tr'):
        value=row.get_text(' ',strip=True)
        m=re.fullmatch(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) ([A-Z][a-z]+ \d{1,2}, \d{4})(?: Updated)?',value)
        if m:
            dates.append(datetime.strptime(m[2],'%B %d, %Y').date().isoformat())
    m=re.search(r'Releases\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)',text)
    return {'dates':dates,'displayed_range':[int(m[i]) for i in [1,2,3]] if m else None,
            'title':s.title.get_text(strip=True) if s.title else '', 'source_id':rec['id'],'url':rec['requested_url']}

def document(rec):
    s=soup(rec); text=s.get_text(' ',strip=True)
    found=re.search(r'Release [Dd]ate:\s*([A-Z][a-z]+ \d{1,2}, \d{4})',text)
    if not found or rec.get('http_status')!=200:
        return None
    rd=datetime.strptime(found[1],'%B %d, %Y').date()
    expected=re.search(r'fed_release_(\d{8})',rec['id'])
    if expected and rd!=datetime.strptime(expected[1],'%Y%m%d').date():
        return None
    table=next((t for t in s.find_all('table') if 'Treasury constant maturities' in t.get_text(' ',strip=True)),None)
    obs=[]
    if table:
        headers={}
        for h in table.find_all('th'):
            m=re.fullmatch(r'(\d{4}) ([A-Z][a-z]{2}) (\d{1,2})\*?',h.get_text(' ',strip=True))
            if m:
                headers[h.get('id')]=datetime.strptime(' '.join(m.groups()),'%Y %b %d').date().isoformat()
        row=next((tr for tr in table.find_all('tr') if tr.find('th') and re.fullmatch(r'10-year',tr.find('th').get_text(' ',strip=True))),None)
        if row:
            for cell in row.find_all('td'):
                txt=cell.get_text(strip=True)
                if re.fullmatch(r'\d+(?:\.\d+)?',txt):
                    obs.extend(headers[h] for h in cell.get('headers',[]) if h in headers)
    return {'release_date':rd.isoformat(),'observation_dates_verified':sorted(set(obs)),
            'source_id':rec['id'],'url':rec['requested_url'],'body_sha256':rec['sha256'],
            'actual_release_at':None,'actual_available_at':None}

def main():
    if (OUT/'audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv').exists():
        raise SystemExit('이미 만든 감사 결과를 덮어쓰지 않습니다.')
    registry=load(OUT/'sources/H15_SOURCE_REGISTER_FINAL.json')
    records=registry['sources']+load(OUT/'sources/H15_SOURCE_REGISTER_SUPPLEMENT.json')['sources']
    successful={r['id']:r for r in records if r.get('http_status')==200}
    def latest(prefix):
        return next((r for r in reversed(records) if r['id'].startswith(prefix) and r.get('http_status')==200),None)
    txt_rec=latest('alfred_release_dates_txt')
    assert txt_rec,'ALFRED TXT 원천 수집이 성공해야 분석한다.'
    txt=body(txt_rec).decode('utf-8-sig')
    alfred_list=[x.strip() for x in re.findall(r'^\d{4}-\d{2}-\d{2}\s*$',txt,re.M)]
    assert 'Release: H.15 Selected Interest Rates' in txt
    assert alfred_list and alfred_list==sorted(alfred_list) and len(alfred_list)==len(set(alfred_list))
    alfred=set(alfred_list)
    api=load(OUT/'sources/FRED_API_COLLECTION.json')
    api_sets={};api_pages=[]
    for run in api['runs']:
        values=[]
        assert run['status']=='COLLECTED_PAGINATION_VERIFIED'
        for p in run['pages']:
            data=load(OUT/p['body_file'])
            assert sha(OUT/p['body_file'])==p['sha256'] and all(x['release_id']==18 for x in data['release_dates'])
            values.extend(x['date'] for x in data['release_dates'])
            api_pages.append({**p,'id':'API_'+str(run['include_release_dates_with_no_data'])+'_'+str(p['offset']),
                              'requested_url':p['public_endpoint'],'status':'HTTP_SUCCESS_REQUIRES_CONTENT_VALIDATION'})
        assert len(values)==run['count'] and values==sorted(set(values))
        api_sets[run['include_release_dates_with_no_data']]=set(values)
    recorded_api=api_sets[True]
    confirmed_data_api=api_sets[False]
    # 공개 캘린더의 페이징/실제 응답 범위도 보존한다. 오래된 FRED요청의 연도제한을 숨기지 않는다.
    pages=[calendar_page(r) for r in records if r.get('http_status')==200 and '_calendar_' in r['id']]
    fred_pages=[p for p in pages if re.fullmatch(r'fred_calendar_20(?:25|26)_\d+(?:_retry_default)?',p['source_id'])]
    pagination=[]
    for year in [2025,2026]:
        ps=[p for p in fred_pages if p['source_id'].startswith('fred_calendar_'+str(year)+'_')]
        vals=[v for p in ps for v in p['dates']]
        count=ps[0]['displayed_range'][2]
        pagination.append({'provider':'FRED_PUBLIC','year':year,'pages':len(ps),'declared_count':count,
                           'rows':len(vals),'unique_rows':len(set(vals)),'complete':len(vals)==len(set(vals))==count,
                           'ranges':[p['displayed_range'] for p in ps]})
    alfred_pages=[p for p in pages if p['source_id'] in ['alfred_calendar_old_request_retry_default','alfred_calendar_2011_page2']]
    apdates=[d for p in alfred_pages for d in p['dates']]
    pagination.append({'provider':'ALFRED_PUBLIC','year':2011,'pages':len(alfred_pages),'declared_count':53,
                       'rows':len(apdates),'unique_rows':len(set(apdates)),'complete':set(apdates)=={d for d in alfred if d.startswith('2011')}})
    fred_public={d for p in fred_pages for d in p['dates']}
    release_rows=[]
    for d in sorted(alfred|recorded_api|fred_public):
        release_rows.append({'release_date':d,'release_id':18,'in_ALFRED_TXT':d in alfred,
            'in_FRED_API_include_no_data_false':d in confirmed_data_api,'in_FRED_API_include_no_data_true':d in recorded_api,
            'in_FRED_PUBLIC_2025_2026_calendar':d in fred_public,
            'future_to_collection_cutoff':d>'2026-10-16',
            'record_interpretation':'release-level date; may reflect source/provider/FRED fallback or any-series revision; not DGS10 first availability',
            'evidence_url':txt_rec['requested_url'] if d in alfred else 'https://api.stlouisfed.org/fred/release/dates?release_id=18',
            'actual_release_at':'null','actual_available_at':'null'})
    write_csv('sources/FRED_ALFRED_RELEASE_DATES.csv',release_rows)
    docs=[document(r) for r in records if r.get('http_status')==200 and (r['id'].startswith('fed_release_') or r['id']=='fed_current')]
    docs=[d for d in docs if d]
    doc_map={d['release_date']:d for d in docs}
    save('audit/H15_OFFICIAL_DOCUMENT_EXTRACTS.json',{'documents':docs,'method':'게시자료 release date와 명시적 표 헤더/10-year 행을 대조. 실제 게시시각은 검증하지 않음.'})
    # OPM은 연방공휴일의 별도 공식 기록이다. Board휴일과 자동 동일시하지 않는다.
    opm_rec=latest('opm_holidays');opm=[];opm_map={};weekday_typos=[]
    for t in soup(opm_rec).find_all('table'):
        cap=t.find('caption')
        if not cap:
            continue
        match=re.search(r'(\d{4}) Holiday Schedule',cap.get_text(' ',strip=True))
        if not match:
            continue
        year=int(match[1])
        for tr in t.find_all('tr'):
            cells=tr.find_all('td')
            if len(cells)<2:
                continue
            label=cells[0].get_text(' ',strip=True)
            m=re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ([A-Z][a-z]+) (\d{1,2})(?:, (\d{4}))?',label)
            if not m:
                continue
            d=datetime.strptime(f'{m[2]} {m[3]} {m[4] or year}','%B %d %Y').date()
            mismatch=d.strftime('%A')!=m[1]
            item={'holiday_date':d.isoformat(),'holiday_name':cells[1].get_text(' ',strip=True),'source_schedule_year':year,
                'source_date_label':label,'weekday_label_conflict':mismatch,'evidence_url':opm_rec['requested_url'],
                'Board_holiday_equivalence_verified':False}
            opm.append(item);opm_map.setdefault(d.isoformat(),[]).append(item)
            if mismatch and START<=d<=END:
                weekday_typos.append(item)
    write_csv('audit/US_FEDERAL_HOLIDAYS_OPM_REFERENCE.csv',opm)
    # K8의2026 Board일정만 직접 확인. 토요일 휴일의금요일Board폐쇄는명시각주에근거한다.
    k8_rec=latest('fed_k8')
    k8_dates={'2026-01-01','2026-01-19','2026-02-16','2026-05-25','2026-06-19','2026-07-03','2026-09-07','2026-10-12','2026-11-11','2026-11-26','2026-12-25'}
    assert 'July 3, 2026' in soup(k8_rec).get_text(' ',strip=True)
    # 공지 원문에서 개별 예외를 수집한다. 공지일과 영향일은 별도다.
    feed_rec=latest('fed_announcements'); events=[];closure={};planned={};delay={}
    for node in soup(feed_rec).find_all('p',class_='article__time'):
        try:
            notice=datetime.strptime(node.get_text(strip=True),'%B %d, %Y').date()
        except ValueError:
            continue
        if not START<=notice<=END:
            continue
        parent=node.parent;strong=parent.find('strong');content=parent.find('div')
        title=strong.get_text(' ',strip=True) if strong else ''
        desc=content.get_text(' ',strip=True) if content else parent.get_text(' ',strip=True)
        lower=(title+' '+desc).lower()
        category=None
        if ('closed' in lower or 'closure' in lower) and ('as scheduled' in lower or 'as planned' in lower) and 'h.15' in lower:
            category='BOARD_CLOSED_H15_PLANNED_EXCEPTION'
        elif ('closed' in lower or 'closure' in lower or 'no update' in lower or 'holiday -' in lower) and any(w in lower for w in ['postpon','will not','first business day','will be published on']):
            category='CLOSURE_OR_POSTPONEMENT'
        elif any(w in lower for w in ['omitted','missing','incorrect','correction','corrected']) and any(w in lower for w in ['treasury','government securities']):
            category='TREASURY_MISSING_OR_CORRECTION'
        elif 'unavailable' in lower:
            category='DDP_CHANNEL_OUTAGE'
        elif '2016' in str(notice) and any(w in lower for w in ['4:15','weekly and monthly']):
            category='PUBLICATION_FORMAT_OR_SCHEDULE_CHANGE'
        if category is None:
            continue
        extracted=[]
        for candidate in re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',desc):
            try:
                extracted.append(datetime.strptime(candidate.replace(',',''),'%B %d %Y').date().isoformat())
            except ValueError:
                pass
        affected=sorted(set(extracted)) or [notice.isoformat()]
        # 公告12/23에 기재된12/25,26 폐쇄를 빠뜨리지 않도록 원문 근거의 두 날짜를 명시한다.
        if notice==date(2014,12,23):
            affected=['2014-12-25','2014-12-26']
        item={'notice_date':notice.isoformat(),'category':category,'title':title,'affected_dates':';'.join(affected),
            'date_extraction_scope':'공지 원문 명시 날짜; 관측일/게시일/정정일이 섞일 수 있어 의미 자동 통합하지 않음',
            'official_statement':desc,'dgs10_scope':'DIRECT_10Y' if re.search(r'10.year.*constant matur',title,re.I) else 'H15_OR_TREASURY_SCOPE_NOT_DGS10_SPECIFIC',
            'actual_release_at':'null','actual_available_at':'null','reopen_timestamp_if_verified':'null',
            'evidence_url':feed_rec['requested_url'],'recovery_mapping_complete':False}
        events.append(item)
        if category=='CLOSURE_OR_POSTPONEMENT':
            for d in affected:
                # 過去金利観測の月日をそのまま閉鎖日とみなさない。閉鎖notice当日または明示休日のみ。
                if d==notice.isoformat() or (notice==date(2014,12,23) and d in affected):
                    closure[d]=item;delay[d]=item
        elif category=='BOARD_CLOSED_H15_PLANNED_EXCEPTION':
            planned[notice.isoformat()]=item
    assert events
    write_csv('audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv',events)
    # RAWでは日付だけを読み、米国株式セッション参照とBoard/連邦暦を分離する。
    sox_path=next((ROOT/'data/raw/02_sox').glob('*RAW*.csv'))
    with sox_path.open(encoding='utf-8-sig',newline='') as f:
        sox_dates={r['Date'] for r in csv.DictReader(x for x in f if not x.startswith('#'))}
    write_csv('audit/US_EQUITY_DATE_REFERENCE.csv',[{'date':d,'basis':'Yahoo SOX RAW observation date only',
        'independent_exchange_calendar_verified':False,'raw_sha256':sha(sox_path)} for d in sorted(sox_dates)])
    evidence=[];d=START
    source_date_union=(alfred|recorded_api|confirmed_data_api)
    while d<=END:
        ds=d.isoformat();recorded=ds in source_date_union
        doc=doc_map.get(ds);is_weekend=d.weekday()>=5
        official_board_holiday=ds in k8_dates
        opm_holiday=ds in opm_map
        source_conflict=recorded and (is_weekend or official_board_holiday or ds in closure)
        opm_weekday_bad=any(x['weekday_label_conflict'] for x in opm_map.get(ds,[]))
        conflict=source_conflict or opm_weekday_bad
        grade='E4' if conflict else 'E1' if doc else 'E2' if recorded else 'E3'
        publication_candidate=True if doc or recorded else False if (is_weekend or official_board_holiday or opm_holiday or ds in closure) else True
        notes=[]
        if source_conflict: notes.append('release日記録と週末/Board休日/明示閉鎖の衝突。公開成功やDGS10反映を推定しない。')
        if opm_weekday_bad: notes.append('OPM日付表記の曜日が暦日と不一致。原文を保持し自動修正しない。')
        if not recorded and not doc and not is_weekend and not opm_holiday and ds not in closure:
            notes.append('個別記録なし。一般日次規則の候補推定のみ。Board休日と断定しない。')
        if recorded and ds not in confirmed_data_api:
            notes.append('API no-data=falseにはなくtrue/ALFREDにある日。記録は保存しデータ更新済とみなさない。')
        if ds in planned:
            notes.append('Board閉鎖でもH15予定発行の個別例外あり。閉鎖=必ず非発表ではない。')
        urls=[doc['url']] if doc else [txt_rec['requested_url']] if recorded else []
        if official_board_holiday: urls.append(k8_rec['requested_url'])
        if opm_holiday: urls.append(opm_rec['requested_url'])
        if ds in closure or ds in planned: urls.append(feed_rec['requested_url'])
        if not urls: urls=['https://www.federalreserve.gov/releases/h15/']
        obs=doc['observation_dates_verified'] if doc else []
        evidence.append({'calendar_date':ds,'in_main_audit_period':MAIN_START<=d<=MAIN_END,
            'source_type':'FED_DOCUMENT' if doc else 'FRED_ALFRED_DATE_RECORD' if recorded else 'OFFICIAL_RULE_OR_HOLIDAY_REFERENCE',
            'release_date':ds if doc or recorded else 'null','observation_date_if_verified':max(obs) if obs else 'null',
            'all_verified_DGS10_observation_dates':';'.join(obs),'evidence_grade':grade,'evidence_url':';'.join(dict.fromkeys(urls)),
            'official_release_document_found':bool(doc),'dgs10_observation_verified_in_release':bool(obs),
            'board_holiday_status':'OFFICIAL_K8_BOARD_HOLIDAY' if official_board_holiday else 'OPM_FEDERAL_HOLIDAY_BOARD_EQUIVALENCE_UNVERIFIED' if opm_holiday else 'UNVERIFIED',
            'US_federal_holiday_record':opm_holiday,'US_equity_RAW_date_present':ds in sox_dates,
            'US_equity_date_basis':'SOX_RAW_DATE_ONLY_NOT_INDEPENDENT_EXCHANGE_CALENDAR',
            'special_closure_status':'OFFICIAL_CLOSURE_H15_POSTPONED' if ds in closure else 'OFFICIAL_CLOSURE_H15_PLANNED' if ds in planned else 'NOT_IN_COLLECTED_NOTICES_NOT_PROOF_OF_NO_EVENT',
            'known_delay_status':'OFFICIAL_POSTPONEMENT_REOPEN_TIME_UNVERIFIED' if ds in delay else 'NO_DATE_SPECIFIC_TIMING_CONFIRMED',
            'conflict_flag':conflict,'actual_release_at':'null','actual_available_at':'null','assumed_release_at':'null','assumed_available_at':'null',
            'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
            'calendar_evidence_status':{'E1':'OFFICIAL_DOCUMENT_DATE_ONLY','E2':'OFFICIAL_RELEASE_DATE_RECORD_ONLY','E3':'ASSUMED_CALENDAR','E4':'UNRESOLVED'}[grade],
            'publication_candidate_under_rule':publication_candidate,
            'normal_nonpublication_confirmed_by_official_rule':(is_weekend or official_board_holiday) and not recorded,
            'nonpublication_due_to_specific_notice':ds in closure and not recorded,
            'calendar_assumption_authorized':False if grade=='E3' else 'NOT_APPLICABLE',
            'in_ALFRED':ds in alfred,'in_FRED_API_false':ds in confirmed_data_api,'in_FRED_API_true':ds in recorded_api,
            'notes':' '.join(notes) or '날짜 근거와 실제 게시/제공처 수신·빈티지는 별도. 정책시각을 관측에 적용하지 않음.'})
        d+=timedelta(days=1)
    # 위 notes는 근거 설명을 한국어로 통일한다.
    replacements={
        'release日記録と週末/Board休日/明示閉鎖の衝突。公開成功やDGS10反映を推定しない。':'발표일 기록과 주말/Board휴일/명시폐쇄 충돌. 실제 공개 성공이나DGS10 반영을 추정하지 않음.',
        'OPM日付表記の曜日が暦日と不一致。原文を保持し自動修正しない。':'OPM 원문 요일과 달력 날짜 불일치. 원문 보존, 자동 정정 없음.',
        '個別記録なし。一般日次規則の候補推定のみ。Board休日と断定しない。':'개별 기록 없음. 일반 일별규칙으로 후보를 추정할 뿐 Board휴일로 단정하지 않음.',
        'API no-data=falseにはなくtrue/ALFREDにある日。記録は保存しデータ更新済とみなさない。':'API no-data=false에는 없고true/ALFRED에 있는 날짜. 삭제하지 않으며 자료 갱신 완료로 해석하지 않음.',
        'Board閉鎖でもH15予定発行の個別例外あり。閉鎖=必ず非発表ではない。':'Board폐쇄에도 H15 예정 발행의 개별 예외가 있음. 폐쇄를 일률적 비게시로 치환하지 않음.'}
    for row in evidence:
        for a,b in replacements.items():row['notes']=row['notes'].replace(a,b)
    write_csv('audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv',evidence)
    gaps=[{k:r[k] for k in ['calendar_date','in_main_audit_period','evidence_grade','calendar_evidence_status','publication_candidate_under_rule',
          'board_holiday_status','special_closure_status','conflict_flag','evidence_url','notes']} for r in evidence if r['evidence_grade'] in {'E3','E4'}]
    write_csv('audit/H15_CALENDAR_GAP_REGISTER.csv',gaps)
    yearly=[]
    for year in range(2010,2027):
        rows=[r for r in evidence if r['calendar_date'].startswith(str(year)) and (r['in_main_audit_period'] or year==2010)]
        counts=Counter(r['evidence_grade'] for r in rows)
        yearly.append({'year':year,'scope':'WARMUP_2010' if year==2010 else 'MAIN_THROUGH_20261009','dates':len(rows),
            **{g:counts[g] for g in ['E1','E2','E3','E4']},
            'official_document_dates':sum(r['official_release_document_found'] for r in rows),
            'FRED_ALFRED_record_dates':sum(r['in_ALFRED'] or r['in_FRED_API_true'] for r in rows),
            'normal_nonpublication_rule_confirmed':sum(r['normal_nonpublication_confirmed_by_official_rule'] for r in rows),
            'rule_only_weekday_publication_candidates':sum(r['evidence_grade']=='E3' and r['publication_candidate_under_rule'] and date.fromisoformat(r['calendar_date']).weekday()<5 for r in rows),
            'official_special_closure_dates':sum(r['special_closure_status'].startswith('OFFICIAL') for r in rows),
            'known_delay_notice_dates':sum(r['known_delay_status'].startswith('OFFICIAL') for r in rows),
            'conflicts':sum(r['conflict_flag'] for r in rows)})
    write_csv('audit/H15_YEARLY_COVERAGE.csv',yearly)
    mainrows=[r for r in evidence if r['in_main_audit_period']]
    counts=Counter(r['evidence_grade'] for r in mainrows)
    differences={'ALFRED_minus_API_false':sorted(alfred-confirmed_data_api),'API_false_minus_ALFRED':sorted(confirmed_data_api-alfred),
        'ALFRED_minus_API_true':sorted(alfred-recorded_api),'API_true_minus_ALFRED_past_cutoff':sorted(d for d in recorded_api-alfred if d<='2026-10-16'),
        'API_true_future_beyond_cutoff':sorted(d for d in recorded_api if d>'2026-10-16'),
        'FRED_public_minus_ALFRED_past_cutoff':sorted(d for d in fred_public-alfred if d<='2026-10-16'),
        'official_docs_absent_API_false':sorted(d for d in doc_map if d not in confirmed_data_api),
        'recorded_dates_without_official_document_count_main':sum((r['in_ALFRED'] or r['in_FRED_API_true']) and not r['official_release_document_found'] for r in mainrows),
        'OPM_weekday_label_conflicts':weekday_typos,'public_calendar_pages':pages,'public_pagination':pagination}
    save('audit/SOURCE_CROSSCHECK_DETAILS.json',differences)
    rec={'recommendation':'PARTIAL_EVIDENCE_ADDITIONAL_APPROVAL_REQUIRED','recommendation_only':True,
        'D10_gate_automatically_passed':False,'original_policy_modified':False,'policy_id':'C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1',
        'main_period':['2011-01-01','2026-10-09'],'main_calendar_date_count':len(mainrows),'main_evidence_counts':dict(counts),
        'calendar_candidate_estimates_not_approved':True,'actual_release_timestamp_verified':False,
        'reason_ko':'공식 release date 전수 다운로드/API 대조로 상당한 근거를 확보했지만2014-04-02 이전 기록은 주로 주간이다. 일별 후보 추정과 명시 폐쇄/특정 기록 충돌이 남아 추가 검토가 필요하다.',
        'requires_user_decision':['근거 공백 일별 게시 후보를 E3 가정으로 허용할지 또는 해당 구간 별도 처리할지',
            'E4 충돌·지연 재개 미확인 관측의 보수적 제외/추가근거 확보 방침','후속 D10 구현 및 Phase2-B 재개는 별도 지시'],
        'weekly_B10_XY_or_models_executed':False,'D13_unchanged':True}
    save('audit/D10_CALENDAR_GATE_RECOMMENDATION.json',rec)
    all_sources=records+api_pages
    original_index=OUT/'sources/H15_SOURCE_REGISTER.json'
    (OUT/'sources/H15_SOURCE_REGISTER_INITIAL.json').write_bytes(original_index.read_bytes())
    final={'release_id':18,'sources':all_sources,'API_collection':'sources/FRED_API_COLLECTION.json',
        'initial_index_preserved':'sources/H15_SOURCE_REGISTER_INITIAL.json','ALFRED_complete_download_rows':len(alfred_list),
        'secret_saved_or_printed':False,'date_classification_is_not_final_approved_calendar':True}
    original_index.write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('sources/SOURCE_COLLECTION_LOG.md',f'''# H.15 근거 수집 기록

초기에는 로컬 FRED 키가 없어 API를 건너뛰고 ALFRED 공식 TXT를 확보했다. 사용자 키 추가 후 공식 API를 별도 수집해 초기 기록을 보존했다. 키/키가 포함된 URL·오류메시지는 출력/저장하지 않았다.

API release_id18, limit1000, offset별 count/limit/offset 검증. no-data=false {len(confirmed_data_api)}개, true {len(recorded_api)}개를 각각5페이지 수집했다. ALFRED TXT {len(alfred)}개와 true의 과거분은 일치한다. true에는 수집시점 이후 예정일51개가 포함되므로 역사 게시 확인으로 사용하지 않았다.

일부 초기 HTTP 설정의 연결실패 후 기본 요청 설정으로 재시도해 성공했다. 실패 기록과404 응답은 원본 그대로 보존했다. 기본 샌드박스 네트워크 WinError10013도 접근실패이며 자료부재가 아니다.

FRED 공개2011 요청이2025 자료를 반환하는 사례를 기록했다. ALFRED2011 공개페이지2개53건, FRED2025/2026 공개페이지 각각5개를 count와 대조했다. API와 공개 화면 페이지네이션은 별개다.

개별 연준 게시자료 성공 날짜는 audit/H15_OFFICIAL_DOCUMENT_EXTRACTS.json, 공지 예외는 audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv에 있다. 원본 바이트/HTTP상태/URL/수집UTC/해시는 sources 원본 메타데이터와 최종 H15_SOURCE_REGISTER.json에 기록했다. 금융 RAW 재수집·수정 및 주간변수 계산은 없다.
''')
    # 주요 결과만 출력. 개별 금리값이나 주간 수익률을 출력하지 않는다.
    print(json.dumps({'ALFRED':len(alfred),'API_false':len(confirmed_data_api),'API_true':len(recorded_api),
        'documents':[(d['release_date'],len(d['observation_dates_verified'])) for d in docs],
        'main_counts':dict(counts),'main_dates':len(mainrows),'events':len(events),
        'pagination':pagination,'recommendation':rec['recommendation']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
