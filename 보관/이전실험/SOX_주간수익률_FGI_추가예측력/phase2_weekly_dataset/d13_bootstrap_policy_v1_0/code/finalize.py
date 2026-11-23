"""D13 합성/독립 검사 후 신규 보고서와 무결성 봉인 작성."""
import sys
from datetime import datetime,timezone
from prepare import OUT, ROOT, LOCK, BUILD, load, save, sha

def main():
    syn=load(OUT/'qc/D13_SYNTHETIC_TEST_RESULTS.json')
    independent=load(OUT/'qc/D13_INDEPENDENT_QC.json')
    inputs=load(OUT/'inputs/D13_INPUT_MANIFEST.json')
    policy=load(OUT/'policy/D13_LOCK_CANDIDATE.json')
    meta=load(OUT/'inputs/WEEKLY_METADATA_RECHECK.json')
    locked=load(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json')
    gate=load(BUILD/'qc/PHASE2B_D10_GATE_RESULT.json')
    changed=[r for r,v in inputs['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    checks={
        'Phase1_D08설정원문승계':policy['inherited_inference']==locked['inference'],
        'Phase1_D13원본상세null보존':locked['inference']['MBB']['minimum_valid_resample_n'] is None,
        'D10_IMPL_PASS승계':gate['D10_GATE']=='IMPLEMENTATION_PASS',
        'Phase2B_DATASET_PASS승계':gate['PHASE2B_DATASET_QC']=='PASS',
        '823격자818공통':meta['calendar_weeks']==823 and meta['common_valid']==818,
        '내부결측0_초기5':len(meta['initial_missing_weeks'])==5 and meta['internal_missing_after_first_valid']==0,
        '최소표본52_80퍼센트':policy['candidate_rules']['minimum_valid_n']=='max(52, ceil(0.80*N_grid))',
        '유효5000_전체시도10000':policy['candidate_rules']['target_valid_replicates']==5000 and policy['candidate_rules']['max_total_attempts']==10000,
        '블록8_4_12_비순환':policy['candidate_rules']['block_lengths']==[8,4,12] and 'noncircular' in policy['candidate_rules']['algorithm'],
        '시드20261016_격자기반파생':policy['candidate_rules']['root_seed']==20261016 and 'SHA256' in policy['candidate_rules']['rng'],
        '합성22사례통과':syn['case_count']==22 and syn['status']=='PASS',
        '독립전수검사통과':independent['status']=='PASS',
        '공유짝인덱스_결측슬롯보존':independent['checks']['모든시도_블록시작_짝_결측_공백_유효블록전수검사'],
        '분산0_비유한중단':all(c['attempts']==0 for c in syn['cases'] if c['case'] in ['zero_variance','nonfinite_variance']),
        'CI_p추론미실행':all(c['p_value'] is None and c['confidence_interval'] is None for c in syn['cases']),
        '실제시험Y파싱0':meta['test_Y_values_read'] is False,
        '추가방법론결정미승인표시':all(x['status']=='ADDITIONAL_DECISION_REQUIRED' for x in policy['additional_decisions'][:2]),
        '보조모형표본미조작':policy['auxiliary_sample_counts'] is None,
        'LOCK아닌후보':policy['status']=='LOCK_CANDIDATE_REVIEW_REQUIRED' and not policy['approved'],
        '기존보호SHA불변':not changed,
        'Phase3미승인유지':policy['gate_snapshot']['PHASE3_EXECUTION']=='NOT_AUTHORIZED'}
    status='PASS' if all(checks.values()) else 'BLOCKED'
    result={'D13_POLICY_QC':status,'checks':checks,'count':len(checks),'protected_files':len(inputs['protected_files']),
        'protected_changed':changed,'gate_snapshot':{**policy['gate_snapshot'],'D13_POLICY_QC':status},
        'execution_counts':{'empirical_XY_regeneration':0,'model_fit':0,'tuning':0,'predictions':0,'performance':0,
            'test_Y_parse':0,'real_loss_bootstrap':0,'real_CI_p_values':0,'phase3':0},
        'synthetic_cases':22,'independent_checks':independent['count'],
        'scope':'후보 정책의 구현 정합성만 검사'}
    result['scope']='후보 정책의 구현 정합성 QC. 최종 승인·통계적 보장·외부 심사 아님.'
    save('qc/D13_POLICY_QC.json',result)
    # Requested QC-area manifest is an exact copy, not a separately drifting record.
    save('qc/D13_INPUT_MANIFEST.json',(OUT/'inputs/D13_INPUT_MANIFEST.json').read_text(encoding='utf-8'))
    assert sha(OUT/'qc/D13_INPUT_MANIFEST.json')==sha(OUT/'inputs/D13_INPUT_MANIFEST.json')
    totals=sum(c['attempts'] for c in syn['cases'])
    accepted=sum(c['accepted'] for c in syn['cases'])
    table='\n'.join('| '+c['case']+' | '+str(c['N_grid'])+' / '+str(c['original_valid_n'])+' | '+str(c['L'])+' | '+str(c['attempts'])+' | '+str(c['accepted'])+' | '+c['status']+' | '+c['test_status']+' |' for c in syn['cases'])
    report=f'''# 연구 C D13 Bootstrap 정책 후보 검토 보고서

작성: 2026-10-18 KST. **D13_POLICY_QC={status}**, **D13_LOCK_STATUS=LOCK_CANDIDATE_REVIEW_REQUIRED**.
이번 작업은 후보 문서와 합성 QC다. 정책 최종 승인, 실제 통계추론, Phase3 실행을 뜻하지 않는다.

## 1. 기존 설계 및 결측 재확인

기존 Phase1 LOCK·승인결정 D08/D13·통계계획과 Phase2B 보고서/QC를 열람하고 해시를 기록했다. 날짜/유효성 전용 CSV에서823주,공통818주,2011-02-07~2026-10-05를 독립 확인했다. 초기학습308,개발209,밀봉시험301주다. 첫5주 예열결손 뒤 내부결측0이다.

301주는 현재 X/Y 가용 주수이며 모델 예측손실의 유효301건은 아직 보장되지 않는다. 시험 데이터 CSV는 파싱하지 않았고 바이너리 해시만 확인했다. 실제Y/예측오차/성과를 열람·계산하지 않았다.

## 2. 후보 규칙

- 하한: `max(52,ceil(.80*N_grid))`. 301→241,209→168,50→52로 검정 불가.
- 블록8주 기본/4·12주 민감도, 비순환 MBB. 원래 연속 달력격자 유지, 균등시작점0..N−L,복원추출,연결 후N슬롯 절단.
- 같은 원천주 M0/M1 손실과 결측mask를 함께 추출한다. 유효 n은 복원추출 중복을 포함하는 슬롯 수다.
- 원본하한 미달은 추출 전 중단. 반복하한 미달은 기록 후 같은 분포로 재추출한다.
- 유효5000회 목표, 총10000회 한도. 한도 내 미달은 BOOTSTRAP_INFERENCE_UNAVAILABLE; 부족반복으로CI/p 산출·조건완화 금지.
- root seed20261016 + 격자SHA/L 기반 PCG64. 동일격자/L이면 알고리즘 공통 시도 인덱스. mask가 다르면 채택번호는 다를 수 있다.
- 분산0/비유한/수치실패는 별도 추론 불가. epsilon이나p=0으로 대체하지 않는다.

이80%는 FGI 변수80% 규칙과 별개다.52/80%는 표본수 운영기준으로 통계적 검정력·coverage를 보장하지 않는다. n하한 재추출은 조건부 분포를 만들며 연속결손에서 거절률이 높을 수 있다. 비무작위 결측, 구조변화, 모형선정 불확실성은 해결하지 못한다. 모든 미개선·실패 결과도 보고한다.

## 3. 기존 D08 유지와 남은 결정

Delta_MAE=M0−M1, 양수FGI유리. 단측alpha.05/양측95%CI, HAC Bartlett4달력주(2·8민감도), 소표본 보정없음,5종Holm,주력Ridge 유지. 기존 details_source에는 HAC z/정규p/CI/분산식과 percentile Bootstrap CI가 명시돼 있어 재선택하지 않았다. 초안의 구버전 민감도는 최신LOCK값으로만 승계한다.

**ADDITIONAL_DECISION_REQUIRED**: A01 percentile 보간(`linear` type7 권고), A02 일부 알고리즘 p미산출시5종Holm 처리(현재 전체family결론 보류 권고). 별도승인 전 어느 것도 확정값으로 처리하지 않는다. Bootstrap p는 원래 필수가 아니므로 새로 추가하지 않으며, 요청시 귀무하 중심화 등 별도승인이 필요하다.

보조 C-M2/3 및 C-M4/5는 가용성/자체격자/paired표본이 미검증이므로 실제주수를 만들지 않았다. 주력818주를 자동승계하지 않는다.

## 4. 합성 및 독립 QC

합성22사례와 {len(syn['guards'])}개 추가경계검사 PASS. 별도구현 독립QC **{independent['count']}/{independent['count']} PASS**, 정책QC **{sum(checks.values())}/{len(checks)} {status}**. 합성 추출시도 총{totals:,}회,채택{accepted:,}회이며 연구의 실증 Bootstrap 횟수는0이다. 음성사례에서 의도한 중단은 테스트PASS로 구분한다.

|합성사례|격자 / 원본유효|L|총시도|채택|처리결과|QC|
|---|---|---|---|---|---|---|
{table}

독립코드는 주 계산함수를 재사용하지 않고 난수·블록 시작점·쌍 인덱스·유효n·최대결손·유효블록·합성평균·정지조건을 전수 재계산했다. 동일 Codex 작업 내 별도구현이며 외부 독립심사는 아니다. RNG라이브러리 자체는 공유한다. 이 검사는 검정력/실제CI coverage 시뮬레이션이 아니다.

## 5. 보호 및 실행이력

기존 보호파일 **{len(inputs['protected_files'])}개 SHA-256 불변**, 변경{len(changed)}건. RAW/freeze/Phase0·1/기존감사·승인·Phase2B 포함. 입력manifest의 동일사본을 inputs와qc에 저장했다. 새 폴더 밖 쓰기0, X/Y재생성0,fit/튜닝/예측/성과/PCA0,실제손실Bootstrap0이다.

작업 중 사용자 중단 후 재개했고 작성된 코드2개를 확인한 뒤 계속했다. UTF8를 명시해 지시문을 재열람했다. 합성QC와 독립QC의 예기치 않은 실패는 없었다. 의도적으로 원본부족/전결측/분산0/비유한/10000한도 실패를 주입하고 모든 원시기록을 보존했다. 독립QC 실행 중 완료 전 파일조회1회는 아직 생성되지 않은 보고서라는 조회오류였으며 QC실패가 아니다. 산출값을 예상치에 맞춰 수정하지 않았다.

## 6. 상태와 다음 승인

D10_GATE=IMPLEMENTATION_PASS, PHASE2B_DATASET_QC=PASS, D13_POLICY_QC={status}, D13_LOCK_STATUS=LOCK_CANDIDATE_REVIEW_REQUIRED, PHASE3_EXECUTION=NOT_AUTHORIZED, PHASE4_TEST_PERFORMANCE=SEALED.

후보 정책 및 추가 방법론 결정을 사용자가 검토해야 한다. 승인은 새 버전으로 보존하고 기존LOCK을 자동변경하지 않는다. Phase3 실행은 별도지시가 필요하다. 이번 작업을 여기서 종료한다.

## 경로

현재폴더: `research_C/phase2_weekly_dataset/d13_bootstrap_policy_v1_0/`. policy에5개정책파일, qc에합성/독립/정책검사와입출력manifest, reports에검토/승인요청/인수인계, code에실행·독립검증코드, inputs에지시문/참조/메타데이터, logs에실행이력. output manifest와 별도sha256은 모든 신규산출물의 무결성을 관리한다.
'''
    save('reports/D13_POLICY_REVIEW_REPORT.md',report)
    save('reports/D13_APPROVAL_REQUEST.md','''# D13 사용자 검토·승인 대상

상태 LOCK_CANDIDATE_REVIEW_REQUIRED. 아직 최종 승인 없음.

1. min_valid_n=max(52,ceil(.80*N_grid)); 원본미달 중단, 재표본미달 거절/재추출.
2. 비순환 MBB8주(4·12민감도), 유효5000회/총10000시도, 실패시 추론불가·조건완화금지.
3. 원래격자/paired 공동추출/가변유효n, 격자SHA+L 기반 seed20261016 파생, 동일격자 시도 인덱스공유.
4. 분산0/비유한·수치오류 중단, 결측및모형실패 원인공개, 추론불가를 비유의로 해석하지 않음.
5. A01: 기존 percentile CI의 유한표본 보간을 linear(type7)로 명시할지 승인 필요.
6. A02: 일부 알고리즘 HAC p산출 불가시 전체Holm결론보류 또는 보수적m5유지 처리의 사전결정 필요. 현재 권고는 결론보류. 임의family축소는 불가.

기존 HAC단측검정+percentileCI를 유지하며 Bootstrap p추가는 권고하지 않는다. 필요시 별도설계승인이다. 연구한계(조건부재추출/결측선택/시계열구조/빈티지)를 함께 명시한다.

이 문서는 검토할 구체적 결과물이다. 사용자 승인 전 LOCKED/APPROVED로 바꾸지 않는다. 정책 승인만으로 모델 학습이나 시험성과 열람이 승인되지 않는다.
''')
    save('reports/D13_HANDOFF.md',f'''# D13 인수인계

후보정책/QC 완료. 정책QC={status},합성22사례PASS,독립{independent['count']}개PASS. 기존1474파일 해시불변.

먼저 policy/D13_LOCK_CANDIDATE.json과md, D13_OPEN_METHODOLOGY_ITEMS.md, reports/D13_APPROVAL_REQUEST.md를 검토한다. D13은 LOCK_CANDIDATE_REVIEW_REQUIRED다. 사용자 승인 후 별도승인기록을 생성해야 하며 원본LOCK/Phase2B는 수정하지 않는다.

코드 재현순서: prepare.py → synthetic_tests.py → write_policy.py → independent_qc.py → finalize.py. 실행기는 기존산출물 덮어쓰기를 거부한다. 동일폴더 재실행 대신 승인된 새실행폴더에서 입력해시를 대조한다. Python경로는 research_C/phase0_raw_audit/.venv/Scripts/python.exe, -B -X utf8 사용. code/environment는 inputs/D13_INPUT_MANIFEST.json에 기록한다.

합성코드는 실제입력/CI/p 기능을 갖지 않는다. 향후 실증코드는 승인된정책·모형예측·새독립QC를 별도로 구현해야 한다. 301은 시험XY유효주수이지 예측오차완료건수가 아니다. metadata 접근은 PAIRED_COMMON_WEEK_MEMBERSHIP.csv의3열만 사용했다. sealed_test는 해시외 열람금지.

추가결정 A01보간/A02누락p의Holm처리는 승인대기다. Bootstrap p는추가하지않는다. Phase3=NOT_AUTHORIZED,Phase4성과=SEALED. D10구현PASS와D13정책대기를구별한다. 이후단계자동시작금지.
''')
    save('README.md',f'''# 연구 C D13 Bootstrap 정책 후보 v1.0

상태: **LOCK_CANDIDATE_REVIEW_REQUIRED**. 정책QC {status}. 합성22사례/독립{independent['count']}개검사.

주 보고서: [D13_POLICY_REVIEW_REPORT.md](reports/D13_POLICY_REVIEW_REPORT.md)
승인 검토: [D13_APPROVAL_REQUEST.md](reports/D13_APPROVAL_REQUEST.md)
정책: [D13_LOCK_CANDIDATE.md](policy/D13_LOCK_CANDIDATE.md)
독립 검사: [D13_INDEPENDENT_QC.md](qc/D13_INDEPENDENT_QC.md)

policy/후보5파일;inputs/참조·메타데이터;qc/합성fixture와시도기록·QC·manifest;code/별도구현;reports/보고·인계;logs/작업이력.
실제 연구Y·예측오차·모델성과를 사용하지 않았다. 기존RAW/LOCK/Phase2B 수정0. 합성재표본의 성공은 연구결과의 유의성이나CI포함률을 뜻하지 않는다.
''')
    save('logs/D13_WORK_LOG.md',f'''# D13 작업 이력

- 2026-10-17 지시문·필수참조 열람, 기존HAC수식/percentileCI 확인, 새폴더코드2개작성 후 사용자중단.
- 2026-10-18 continue로재개. 기존2개코드확인. prepare.py 입력해시1474개PASS와날짜플래그823/818검사.
- 실제Y열람없이22개합성fixture생성.5000목표/10000상한/결측패턴/경계/음성경로실행. 총시도{totals},채택{accepted}.
- 정책5문서/JSON작성.승인대기, A01/A02 추가결정과선택지기록.
- 주함수호출없는독립검사{independent['count']}개PASS. 최종정책QC{sum(checks.values())}/{len(checks)}.
- 독립검사수행중 미생성QC파일 조회1회. 실행실패아님. 출력후다시확인.
- 신규코드내설명용임시외국어문구를한국어로정리; 계산로직·결과변경없음. 기존파일수정없음.
- 의도한음성시험의UNAVAILABLE/INSUFFICIENT는정상PASS. 예기치않은테스트실패0. 실패기록삭제없음.
- sealed_test내용파싱0;해시계산만수행.모델/예측/성과/실제손실bootstrap/Phase3이후0.
''')
    files=[]
    for p in sorted(OUT.rglob('*')):
        if p.is_file():files.append({'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    save('qc/D13_OUTPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':files,
        'file_count':len(files),'excludes':['qc/D13_OUTPUT_MANIFEST.json','qc/D13_OUTPUT_MANIFEST.sha256'],
        'self_hash_policy':'별도sha256파일에이manifest해시기록','protected_count':1474})
    save('qc/D13_OUTPUT_MANIFEST.sha256',sha(OUT/'qc/D13_OUTPUT_MANIFEST.json')+'  D13_OUTPUT_MANIFEST.json\n')
    assert all(sha(OUT/x['path'])==x['sha256'] for x in files)
    print({'D13_POLICY_QC':status,'checks':len(checks),'protected':1474,'synthetic_attempts':totals,'accepted':accepted,'output_manifest_files':len(files)})
    if status!='PASS':sys.exit(1)

if __name__=='__main__':main()
