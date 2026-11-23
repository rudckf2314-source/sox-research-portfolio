"""Reports, append-only index pointer and output hashes for approved lock v1.1."""
from pathlib import Path
import hashlib,json,platform
L=Path(__file__).resolve().parents[1];O=L.parent;ROOT=O.parents[1]
def read(n):return json.loads((L/n).read_text(encoding='utf-8'))
def write(n,t):(L/n).write_text(t.strip()+'\n',encoding='utf-8')
def main():
    if (L/'qc/LOCK_FINALIZATION.json').exists():raise RuntimeError('v1.1 is sealed; reports must be revised only in a separately approved version')
    spec=read('PHASE1_LOCKED_SPEC_v1_1.json');a=read('PHASE1_APPROVED_DECISIONS.json');inp=read('inputs/PHASE1_LOCK_INPUT_MANIFEST.json')
    auto=read('qc/PHASE1_LOCK_QC.json') if (L/'qc/PHASE1_LOCK_QC.json').exists() else {'qc_status':'PENDING','test_count':0,'unauthorized_changes':[]}
    ind=read('qc/PHASE1_LOCK_INDEPENDENT_QC.json') if (L/'qc/PHASE1_LOCK_INDEPENDENT_QC.json').exists() else {'qc_status':'PENDING','test_count':0}
    original=inp['protected_files']['RESEARCH_PROJECT_INDEX.md'];p=ROOT/'RESEARCH_PROJECT_INDEX.md';before=p.read_bytes()
    append='\n\n## 연구 C Phase 1 승인 LOCK v1.1 (2026-10-17)\n\n- 상태: PHASE1_DESIGN_LOCKED_WITH_GATES. D10·D13 미통과 게이트 유지, Phase 2 실행 미승인·미실행.\n- 승인 설계·QC·보고서: `research_C/phase1_research_design/approval_lock_v1_1/`\n'
    if hashlib.sha256(before).hexdigest()==original['sha256']:
        with p.open('ab') as stream:stream.write(append.encode('utf-8'))
    else:
        assert hashlib.sha256(before[:original['bytes']]).hexdigest()==original['sha256'],'Unexpected index prefix change'
        assert before[original['bytes']:]==append.encode('utf-8'),'Unexpected index appended content'
    write('qc/INDEX_CHANGE_v1_1.json',json.dumps({'path':str(p),'before_sha256':original['sha256'],'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'operation':'Authorized append only; v1.1 state/path; original bytes retained','original_bytes':original['bytes'],'appended_text':append},indent=2,ensure_ascii=False))
    decisions='\n'.join(f"|{r['decision_id']}|{r['approval_status']}|{r['decision']}|" for r in a['decisions'])
    write('reports/PHASE1_LOCK_REPORT.md',f'''# 연구 C Phase1 최종 승인 및 설계 LOCK v1.1 보고서

승인일 **2026-10-17 KST**. 최종 상태 **PHASE1_DESIGN_LOCKED_WITH_GATES**.

## 1. 연구 C 개요

연구명은 「CNN Fear & Greed Index의 추가 예측 정보가치와 시기별 안정성: 미국 반도체지수(SOX)의 비중첩 주간 수익률에 대한 표본외 머신러닝 분석」이다. 주력 질문은 B10을 통제한 후 FGI가 같은 주간의 표본외 MAE를 줄이는지이며 인과효과나 실거래 수익성을 검증하는 연구가 아니다.

## 2. 승인 작업의 목적·실제 범위

사용자 최종 승인 첨부 지시문과 로컬 연구계획서, 기존 Phase1 필수자료 및18후보 설정을 전체 읽었다. 기존 초안의31개 산출물은 시작 전 매니페스트와 일치했다. 승인결정·기계가독 사양·게이트·변경이력·QC·인수인계만 별도 버전 폴더에 작성했다. 원본 초안이나 Phase0/RAW/freeze를 재실행·수정하지 않았다.

승인 원문 SHA-256: `{inp['approval_source_sha256']}`. 사본은 inputs/USER_APPROVAL_INSTRUCTION.txt, 원본 절대경로·각 입력 해시는 inputs/PHASE1_LOCK_INPUT_MANIFEST.json에 있다. 승인 날짜는 클라이언트 KST 기준을 사용했다. 원계획서를 복제하거나 덮어쓰지 않았다.

## 3. 승인사항 D01~D14

|ID|승인 상태|결정 및 조건|
|---|---|---|
{decisions}

항목 승인, 데이터 검증 상태, 실행 권한은 서로 별도다. D04 APPROVED가 UNVERIFIED를 해소하지 않으며, D02 APPROVED_CONDITIONAL이 D10을 통과시키지 않는다. D13 기본 방향 승인도 상세 잠금이 아니다.

## 4. v1.0 초안과 v1.1 차이

전체 REQUIRES_APPROVAL에서 승인된 부분을 고정하는 PHASE1_DESIGN_LOCKED_WITH_GATES로 바뀌었다. 09:00 ET·B10·FGI80%/100%·분할·창·알고리즘·Ridge 주력·확장그룹·검정이 승인 상태로 기록됐다. HAC 민감도는 초안1·8에서 **2·8주**, bootstrap 민감도는4·13에서 **4·12주**로 최신 지시에 따라 변경했다. 이 변경은 시험성과를 보고 선택한 것이 아니다.

D04에는 실제/가정 필드와 버전 ID, 기본 원천 이동0세션/민감도1세션, 휴장/불일치/관측률 기록을 추가했다. 원래31개 파일과61개 후보 변수사전은 변경하지 않고 참조 해시로 연결했다. 전체 변경표는 PHASE1_CHANGELOG_v1_1.md에 있다.

## 5. 확정된 Y·X·모형·검정

- Y: `100*(P_sox[w]/P_sox[w-1]-1)`, 02 Yahoo ^SOX Close, 미국 월~일 비중첩 부호수익률.
- 원점: 해당 주 첫 실제 미국 거래일09:00 America/New_York. 실제 시각은 `<origin`, DST/휴장/조기마감 반영.
- C-M0=B1~B10, C-M1=C-M0+F1. B3 ddof1 비연율화, B4 Wilder SMA seed/0분모 규칙, B9 Adj Close, B10 bp를 그대로 유지한다.
- 초기2011~2016, 개발2017~2020, 시험2021~마지막Y완료주. 현 RAW 상한 후보는10/05주·10/09종가이며 실제 표본 수는 아직 모른다.
- Expanding 대5달력년 Rolling, 최소156유효 학습주, 미달원점 미예측/쌍별제외 기록. 결손 때문에260행까지 과거 연장 금지.
- 주력 Ridge. Ridge M0 개발MAE로 선택한 창을 Ridge M1에도 적용하며 창 동점은Expanding이다. 나머지 알고리즘은 원래 각 M0 기준을 유지하고5종 모두 보고한다.
- OLS1/Ridge5/ElasticNet4/RF4/HistGradientBoosting4=18고유 후보를 **표현별·창별·개발원점별** 적용한다. 원본18개 파라미터 레코드와 완전히 동일하며 후보 추가·재추출은 없다. seed20261016,0%/학습평균 기준을 유지한다.
- MAE 주지표, RMSE/학습평균기준 OOS R²/방향정확도 보조. ΔMAE=M0−M1이며 양수가FGI 유리다. 음수예측 clipping은 없다.
- 단측.05/양측95%CI, HAC4(2·8 민감도), MBB8(4·12 민감도)/5000회,5종Holm, 전제충족 OLS 제곱오차 Clark–West만 허용한다. bootstrap 결손 상세는 D13에서 대기한다.

C-M2/3 심리그룹과 C-M4/5 업종그룹은 산식·시점가용성 조건부 승인이다. French·월간산업·무역·거시는 별도 탐색 후보다. 이승인은 모든61개후보를한모형에동시투입하라는뜻이아니다.

## 6. D04 가정 기반 정보가용성 정책

A안은 APPROVED다. 주력 daily EOD/FGI 정책 ID는 C_DAILY_EOD_NEXT_US_SESSION_0800_ET_v1_1이며 관측세션 다음 실제 미국 세션08:00 ET를 **assumed_available_at**으로만 정의한다. 이는 실제 게시시각을 새로 조사해 확인한 결과가 아니다. 더 늦은 실제 게시가 있었을 수 있다는 한계가 남는다.

실제 시각이 미확인이면 actual_release_at/actual_available_at은 null이다. availability_basis,publication_status,vintage_status,assumption_policy_id를 분리한다. 가정 적격이어도 UNVERIFIED는 유지한다. 알려진 실제 늦은 발표·embargo를 가정으로 덮어쓰지 않는다.

F1의 전주 관측일과 assumed 게시 주는 다를 수 있다. 예를 들어 금요일 점수의 가정 시각은 다음 개장일08:00일 수 있으므로 ‘실제로 전주에 공개됐다’고 말하지 않는다. 추가1세션 민감도에서는 전주 각 목표 세션의 원천 날짜를 실제 US세션 한 칸 이전으로 옮기고 N_expected/80% 기준을 유지한다. 휴장일 점수를 정상 거래일로 옮기거나 유효점수를 찾을 때까지 이동하지 않는다. 상세는 LOCKED_SPEC.md와 JSON에 고정했다.

이 정책은 DGS10·저빈도자료의 공개지연을 면제하지 않는다. B10은 별도 D10 사전감사를 통과해야 한다. 본 연구는 ‘가정 기반 역사적 표본외 분석’이며 검증된 완전 실시간 PIT 실험이라고 주장하지 않는다.

## 7. D10 게이트

**PENDING_PHASE2_PREBUILD_AUDIT**, APPROVED_CONDITIONAL + GATE_PENDING, passed=false다. 이번에 공표시점 감사를 실행하지 않았다.

Phase2 명시 승인 뒤 첫 단계에서 H15 공식규칙/실제·가정 판정 방법, 기준주·전전주 관측, 결측·미확인, 공통표본 영향, 기존B10 정의 유지 가능성/정책변경 필요를 보고해야 한다. 주간X/Y 본격 생성보다 선행한다. 유지 불가이면 B10/핵심공통표본 생성을 중단하고 별도 승인받는다. B10 자동 삭제·대체·금요일 고정·보간은 금지한다.

## 8. D13 게이트

**PENDING_WEEKLY_MISSINGNESS_AUDIT**, 기본방향 승인/상세 DEFERRED_LOCK, passed=false다. 이번에 실제 결손감사를 하지 않았다.

미국 달력주 격자,8주블록,paired공동추출,매회 유효n 기록만 채택했다. 최소유효n·부족/빈반복 처리·최대재추출·실패 처리는 null로 남겼다. Phase2 실제 결손감사 후 별도 문서로 정하고 **Phase4 최종시험 예측오차·성능을 보기 전에** 잠가야 한다. 시험 결과를 보고 규칙을 바꾸지 않는다.

## 9. 자동 LOCK QC

**{auto['qc_status']}**, {auto['test_count']}개 검사. D01~14, 상태/필드 분리,Y/B10/FGI/분할/창/Ridge/18후보/검정, 미통과 게이트, 보호해시, Phase2 미실행을 검사했다. 상세 qc/PHASE1_LOCK_QC.json. 이 PASS는 승인 문서의 반영·정합성·보존 검사이며 D10/D13 사실 검증 통과가 아니다.

## 10. 독립 LOCK QC

**{ind['qc_status']}**, {ind['test_count']}개 별도 검사. 작성/자동QC를 import하지 않고 사용자원문·초안·원래사전·18후보·보호해시를 직접 대조했다. synthetic 시간/세션목록은 논리 확인만을 위한 예시이며 실제 as-of/X/Y는 만들지 않았다. 동일 에이전트의 별도 구현 검증으로 외부 연구자 심사라고 표현하지 않는다. qc/PHASE1_LOCK_INDEPENDENT_QC.md에 범위를 명시했다.

## 11. 기존 자료 불변

보호 snapshot {len(inp['protected_files'])}개에는 기존 RAW·freeze·Phase0·Phase1 원본31개·계획서 등이 포함된다. 허용된 인덱스 하단 경로/상태 추가를 제외한 무단 변경은 **{len(auto['unauthorized_changes'])}건**이다. 기존 인덱스 바이트도 그대로 유지했다. 입력/산출물 파일별 SHA-256은 inputs manifest와 qc/PHASE1_LOCK_OUTPUT_MANIFEST.json에 보존한다. 기존 Phase1 매니페스트를 새 결과로 덮어쓰지 않았다. D1/W1 아카이브·해시 문제를 다시 조사하지 않았다.

## 12. 미해결 사항

D10의 실제 공표 판정 및 B10/공통표본 영향, D13의 실제 결손 기반 반복표본 상세, 실제 주간 유효 표본 수, 보조 그룹 가용성 검증은 남아 있다. 역사적 게시시각·빈티지 미확인은 승인으로 해결되지 않았다. 기존 점수의 유효성 확인과 최초 공개시각 검증은 별개다. 이전 연구의 동일 시장기간 결과 노출 이력도 한계로 유지한다.

## 13. Phase2 진입조건

이번 승인은 **Phase2 실행 승인이 아니다**. 사용자가 별도로 지시하면 우선 v1.1 인수인계서·QC·게이트를 읽고 D10 사전감사부터 수행해야 한다. D10 유지 불가시 주간B10/핵심공통표본 생성을 중단하고 보고한다. D13 세부는 Phase2 결손패턴 확인 후 시험오차 열람 전에 잠근다. 어떤 후속 작업도 원본 RAW/freeze/기존 Phase 보고서를 덮어쓰지 않는다.

## 14. 최종 상태와 산출물

**PHASE1_DESIGN_LOCKED_WITH_GATES**. 승인된 결정 부분은 고정했고, D10/D13은 미통과다. Phase2폴더 미생성, RAW다운로드/수정·FGI수정·X/Y생성·실제as-of·학습·튜닝·예측·성과 계산은 모두0회다.

승인결정/LOCKED_SPEC JSON·MD/원래18후보/산식출처/게이트/변경이력/README, 입력manifest·원문, 자동·독립QC·보고서·인수인계·실행코드·출력해시를 이 버전 폴더에 보존했다. 원본v1.0을열람할때의미승인상태는과거기록이며현재승인은이v1.1이다.
''')
    write('reports/PHASE1_LOCK_HANDOFF.md','''# 연구 C Phase1 v1.1 인수인계

현재 상태 PHASE1_DESIGN_LOCKED_WITH_GATES. 승인일2026-10-17 KST. Phase2 실행은 별도 사용자 지시 전까지 금지한다. 이번 문서의 승인은 다음 단계 자동 실행 승인이 아니다.

## 먼저 읽을 자료

이폴더의 PHASE1_LOCKED_SPEC_v1_1.json/.md, PHASE1_APPROVED_DECISIONS.json, PHASE1_GATE_REGISTER.json, qc의자동/독립QC와입력manifest를읽는다. 원본계획서는프로젝트루트 Research_C_Study_Plan_v1_20261016.md다. 기존Phase1초안/보고서는역사기록으로그대로보존됐고승인범위는v1.1이우선한다.

## 승인된 설계

Y는02 Yahoo SOX Close의 미국 달력 주 비중첩 부호수익률 `100*(P_w/P_(w-1)-1)`이다. 미국 현지 월요일키,첫실제US세션09:00 America/New_York,strict实际/가정경계분리를유지한다. 당일D1이나rolling5일Y/PCA모형으로바꾸지않는다.

B1~B10 산식은기존그대로이며B3 ddof1 비연율화,B4 Wilder SMA seed/0분모규칙,B9 HYGAdjClose,B10 DGS10bp다. F1은전주적격일별점수평균0~100척도,ceil(.8*N_expected),100%민감도다. 자동LOCF·보간·미래참조금지. 현재03/12=21.15존재와10/06로컬우선이력은유지한다.

초기2011~16/개발2017~20/시험2021~마지막Y완료주를월요일기준배정한다. 현재마지막완료주후보는2026-10-05/10-09다. 실제유효주수는아직미산출이다. Expanding/5달력년Rolling/최소156주를유지하고260유효행을채우도록창을늘리지않는다.

주력은Ridge다. Ridge M0 개발pooledMAE로창을선택해Ridge M1에도공유하며동점Expanding이다. 다른4종은기존각M0기준공통창쌍비교를유지하고5종전부보고한다. 후보는 PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json의18개(1+5+4+4+4),seed20261016이다. 후보재추출/증설/시험결과를본주력교체금지다.

## D04 승인된 가정과 남은 불확실성

A안은승인됐다. 실제미확인timestamp는null이고 assumed_available_at/availability_basis/publication_status/vintage_status/assumption_policy_id를구별한다. 기본가정은완료된daily관측의다음실제US세션08:00 ET이며공식게시시각확인결과가아니다. 실제늦은발표증거를가정으로덮어쓰지않는다. FGI기본원천이동0세션,민감도는전주각대상세션의원천을실제이전US세션한칸이동이다. 주말/휴일점수의날짜를몰래옮기거나결측직전값을자동재사용하지않는다. 전주관측과가정게시주가다르면기록한다. 1세션추가지연은UNVERIFIED를VERIFIED로만들지않는다.

## Phase2에서 가장 먼저 수행할 D10

D10_GATE_STATUS=PENDING_PHASE2_PREBUILD_AUDIT. Phase2 실행을사용자가명시승인한후에도주간X/Y본격생성전에H15공표사전감사부터한다. 공식발표근거,실제/가정판정,전주·전전주유효관측,미확인/결측,공통주영향,B10정의유지가능성,정책변경필요를보고한다. D04 daily가정을B10에자동적용하지않는다. 기존B10유지가불가능하면삭제·대체하지말고B10/핵심공통표본생성을중단해별도승인받는다. 이게이트는통과되지않았다.

## 시험 전에 해결할 D13

D13_GATE_STATUS=PENDING_WEEKLY_MISSINGNESS_AUDIT. 원래달력주격자/8주블록/paired공동추출/유효n가변기록만승인됐다. 최소n,부족·빈반복처리,최대재추출/실패정책은null/DEFERRED_LOCK이다. Phase2 실제결손감사후별도문서로확정하고 **Phase4 최종시험예측오차·성능열람전에잠근다**. 이세부를임의로완료하지않는다.

## 지표/검정 및 금지

MAE(%p)주지표와RMSE/학습평균기준OOS R²/방향정확도,ΔMAE=M0−M1을유지한다. HAC4/민감도2·8,MBB8/민감도4·12/5000회,단측alpha.05/양측95%CI/Holm5종이다. Clark–West는전제충족중첩선형OLS의제곱오차만허용한다. 실제검정은아직실행하지않았다.

RAW/freeze/Phase0/기존Phase1/과거연구·아카이브수정금지. D10·D13통과로기록금지. Phase2~5자동시작금지. 시험성과를변수/창/모형/후보선택에사용금지. 현재작업은승인문서동결뿐이며실제X/Y/as-of/모형/예측/성과0회다. 추후각Phase는입력manifest/코드/결과/QC/보고서/handoff를전용경로에작성하고사용자검토뒤다음단계로간다.
''')
    write('qc/LOCK_WORK_LOG.md','''# 승인 LOCK 작업 기록

2026-10-17 KST: 사용자 승인 지시문과 로컬계획서 전체, 필수Phase1 문서/CSV/JSON/후보예산을 읽었다. 원본31개 Phase1 산출물의 매니페스트 대조 결과 불일치0건이었다.

입력 보호990개 파일의 현재해시를 새 버전 inputs에 보존했다. 새 폴더에 승인결정/사양/조건부게이트/변경이력/보고서/인수인계/검증코드만 작성했다. 기존Phase1 작성/검증코드는 원본을 덮어쓸 수 있으므로 재실행하지 않았다.

18개 후보는 기존algorithms 레코드를 그대로 채택했다. HAC2·8/Bootstrap4·12는 최신 승인값으로 명시 변경했다. D04 가정은 actual과별도표현하며 D10사전감사면제로사용하지않는다. D13 상세 n/반복처리는임의확정하지않고null로남겼다.

프로젝트인덱스에는 v1.1경로/상태만하단추가했고기존바이트를그대로유지했다. 외부사이트접속/RAW다운로드/환경설치/자료값재계산/모형실행/최종시험성과열람은없다. 독립검증의synthetic시각/세션/관측률검사는실제as-of표나연구X/Y생성이아니다.
''')
    write('qc/LOCK_ENVIRONMENT.json',json.dumps({'python':platform.python_version(),'implementation':platform.python_implementation(),'dependencies':'Python standard library only; existing Research C venv reused','client_date_KST':'2026-10-17'},indent=2))
    files=sorted(p for p in L.rglob('*') if p.is_file() and p.name!='PHASE1_LOCK_OUTPUT_MANIFEST.json')
    output={'overall_status':spec['status'],'file_count_including_this_manifest':len(files)+1,'self_excluded_from_hash':True,
       'files':[{'path':p.relative_to(L).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    write('qc/PHASE1_LOCK_OUTPUT_MANIFEST.json',json.dumps(output,indent=2,ensure_ascii=False))
    print(json.dumps({'status':spec['status'],'auto_qc':auto['qc_status'],'independent_qc':ind['qc_status'],'files':len(files)+1,'D10':spec['gate_status']['D10_GATE_STATUS'],'D13':spec['gate_status']['D13_GATE_STATUS'],'phase2_executed':False}))
if __name__=='__main__':main()
