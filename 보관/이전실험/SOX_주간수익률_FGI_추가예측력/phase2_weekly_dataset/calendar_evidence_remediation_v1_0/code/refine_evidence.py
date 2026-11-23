"""추가 공식 월별 근거를 기존 새 감사결과에 통합. 최초 분석 스냅샷 보존."""
import csv
import json
from collections import Counter
from datetime import date
from bs4 import BeautifulSoup
from collect_evidence import OUT,load,save

def rows(rel):
    with (OUT/rel).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def overwrite(rel,data):
    with (OUT/rel).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)

def main():
    if (OUT/'audit/REFINEMENT_RECORD.json').exists():
        raise SystemExit('추가 대조 완료 기록 덮어쓰기 금지')
    targets=['audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv','audit/H15_CALENDAR_GAP_REGISTER.csv',
             'audit/H15_YEARLY_COVERAGE.csv','audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv',
             'audit/D10_CALENDAR_GATE_RECOMMENDATION.json','sources/H15_SOURCE_REGISTER.json']
    for rel in targets:
        (OUT/'logs'/('INITIAL_'+rel.replace('/','__'))).write_bytes((OUT/rel).read_bytes())
    extra=load(OUT/'sources/H15_GAP_DOCUMENTS.json')['sources']
    success={r['id']:r for r in extra if r.get('http_status')==200}
    evidence=rows('audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv'); bydate={r['calendar_date']:r for r in evidence}
    events=rows('audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv')
    updates=[]
    cases=[
        ('2017-01-20','fed_gap_2017_january','OFFICIAL_BOARD_HOLIDAY_SCHEDULE','Holiday - Inauguration Day','null'),
        ('2018-12-05','fed_gap_2018_december','OFFICIAL_CLOSURE_H15_POSTPONED','postponed until Thursday December 6','2018-12-06'),
        ('2018-12-24','fed_gap_2018_december','OFFICIAL_CLOSURE_H15_POSTPONED','closed on December 24, 2018','2018-12-26'),
        ('2020-12-24','fed_gap_2020_december','OFFICIAL_CLOSURE_H15_POSTPONED','closed on December 24, 2020','2020-12-28'),
        ('2021-12-31','fed_gap_2021_december','OFFICIAL_BOARD_HOLIDAY_SCHEDULE',"Holiday- New Year's Day",'2022-01-03'),
        ('2024-12-24','fed_gap_2024_december','OFFICIAL_CLOSURE_H15_POSTPONED','closed on December 24, 2024','2024-12-26'),
        ('2025-01-09','fed_gap_2025_january','OFFICIAL_CLOSURE_H15_POSTPONED','national day of mourning','2025-01-10')]
    for d,source,status,phrase,recovery in cases:
        rec=success[source];text=BeautifulSoup((OUT/rec['body_file']).read_bytes(),'html.parser').get_text(' ',strip=True)
        assert phrase in text,(source,phrase)
        r=bydate[d]
        assert r['in_ALFRED']=='False' and r['in_FRED_API_true']=='False'
        r.update({'special_closure_status':status,'known_delay_status':'OFFICIAL_DELAY_DATE_ONLY_TIME_UNVERIFIED' if recovery!='null' else 'OFFICIAL_HOLIDAY_DATE_ONLY',
            'publication_candidate_under_rule':'False','normal_nonpublication_confirmed_by_official_rule':'True',
            'nonpublication_due_to_specific_notice':'True','evidence_url':r['evidence_url']+';'+rec['requested_url'],
            'notes':r['notes']+' 추가 공식 월별 일정/공지로 비게시·이월 근거 확인. 실제 재개시각은 미확인, 예정 재개일 '+recovery+'.'})
        if status=='OFFICIAL_BOARD_HOLIDAY_SCHEDULE':r['board_holiday_status']='OFFICIAL_FED_MONTHLY_BOARD_HOLIDAY'
        template={k:'null' for k in events[0]}
        template.update({'notice_date':d,'category':status,'title':'연준 공식 월별 휴일·폐쇄·이월 공지',
            'affected_dates':d,'date_extraction_scope':'공식 월별 일정의 명시 날짜. 공지 게시 timestamp는 미검증.',
            'official_statement':phrase,'dgs10_scope':'H15_OR_GENERAL_STATISTICAL_RELEASE',
            'reopen_timestamp_if_verified':'null','evidence_url':rec['requested_url'],'recovery_mapping_complete':'False'})
        events.append(template);updates.append({'date':d,'source':rec['requested_url'],'action':'explicit_nonpublication_or_postponement_date','planned_recovery_date':recovery})
    # Sandy 공지일10/29와 미래 영향일10/30을 혼동하지 않고 두 날짜를 분리한다.
    r=bydate['2012-10-30'];r.update({'special_closure_status':'OFFICIAL_CLOSURE_H15_POSTPONED',
        'known_delay_status':'OFFICIAL_POSTPONEMENT_REOPEN_TIME_UNVERIFIED','publication_candidate_under_rule':'False',
        'nonpublication_due_to_specific_notice':'True',
        'evidence_url':r['evidence_url']+';https://www.federalreserve.gov/feeds/h15.html',
        'notes':'10/29 공지가10/30 폐쇄를 명시함. 공지일과 영향일을 분리했고 실제 재개시각은 미확인.'})
    # 2018-03-02: 폐쇄에도 H15는 예정대로라는 공식문구. 기록 부재를 휴일로 보정하지 않는다.
    for d,source in [('2018-03-02','fed_gap_2018_march'),('2025-01-06','fed_gap_2025_january'),('2025-01-07','fed_gap_2025_january')]:
        rec=success[source];text=BeautifulSoup((OUT/rec['body_file']).read_bytes(),'html.parser').get_text(' ',strip=True)
        assert 'as scheduled' in text
        r=bydate[d];r['special_closure_status']='OFFICIAL_CLOSURE_H15_PLANNED'
        r['evidence_url']+=';'+rec['requested_url'];r['notes']+=' 공식폐쇄에도 H15/통계자료 예정발행 예외. 실제 최초 게시·수신은 미검증.'
        if r['in_ALFRED']=='False':
            r.update({'evidence_grade':'E4','calendar_evidence_status':'UNRESOLVED','conflict_flag':'True',
                      'notes':r['notes']+' 예정발행 문구와 release기록 부재의 확인 공백을 보존.'})
        updates.append({'date':d,'source':rec['requested_url'],'action':'closed_but_H15_planned; preserve_missing_record_if_any'})
    overwrite('audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv',evidence)
    overwrite('audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv',events)
    gap_fields=list(rows('audit/H15_CALENDAR_GAP_REGISTER.csv')[0])
    gaps=[{k:r[k] for k in gap_fields} for r in evidence if r['evidence_grade'] in {'E3','E4'}]
    overwrite('audit/H15_CALENDAR_GAP_REGISTER.csv',gaps)
    yearly=[]
    for year in range(2010,2027):
        subset=[r for r in evidence if r['calendar_date'].startswith(str(year)) and (r['in_main_audit_period']=='True' or year==2010)]
        counts=Counter(r['evidence_grade'] for r in subset)
        yearly.append({'year':year,'scope':'WARMUP_2010' if year==2010 else 'MAIN_THROUGH_20261009','dates':len(subset),
            **{g:counts[g] for g in ['E1','E2','E3','E4']},
            'official_document_dates':sum(r['official_release_document_found']=='True' for r in subset),
            'FRED_ALFRED_record_dates':sum(r['in_ALFRED']=='True' or r['in_FRED_API_true']=='True' for r in subset),
            'normal_nonpublication_rule_confirmed':sum(r['normal_nonpublication_confirmed_by_official_rule']=='True' for r in subset),
            'rule_only_weekday_publication_candidates':sum(r['evidence_grade']=='E3' and r['publication_candidate_under_rule']=='True' and date.fromisoformat(r['calendar_date']).weekday()<5 for r in subset),
            'official_special_closure_dates':sum(r['special_closure_status'].startswith('OFFICIAL') for r in subset),
            'known_delay_notice_dates':sum(r['known_delay_status'].startswith('OFFICIAL') for r in subset),
            'conflicts':sum(r['conflict_flag']=='True' for r in subset)})
    overwrite('audit/H15_YEARLY_COVERAGE.csv',yearly)
    recommendation=load(OUT/'audit/D10_CALENDAR_GATE_RECOMMENDATION.json')
    counts=Counter(r['evidence_grade'] for r in evidence if r['in_main_audit_period']=='True')
    recommendation['main_evidence_counts']=dict(counts)
    recommendation['supplemental_official_monthly_documents_reviewed']=len(success)
    (OUT/'audit/D10_CALENDAR_GATE_RECOMMENDATION.json').write_text(json.dumps(recommendation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    registry=load(OUT/'sources/H15_SOURCE_REGISTER.json');registry['sources']+=extra
    (OUT/'sources/H15_SOURCE_REGISTER.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('audit/REFINEMENT_RECORD.json',{'initial_analysis_snapshots':'logs/INITIAL_*','official_source_updates':updates,
        '20121030_notice_versus_affected_date_fixed':True,'data_or_policy_changed':False,
        'notes':'보완 중의 새 감사 산출물만 최종화. 기존 원본/Phase2-B는 수정하지 않음.'})
    print('Final main grades:',dict(counts),'exceptions:',len(events),'weekday estimates:',sum(r['rule_only_weekday_publication_candidates'] for r in yearly if r['year']>=2011))

if __name__=='__main__':main()
