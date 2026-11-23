"""Independent design consistency audit. Does not import document builders or automatic QC."""
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import ast,csv,hashlib,json
P=Path(__file__).resolve().parents[1];ROOT=P.parents[1]
def load(n):return json.loads((P/n).read_text(encoding='utf-8'))
def main():
    tests=[]
    def record(name,ok,evidence):tests.append({'name':name,'pass':bool(ok),'evidence':evidence})
    with (P/'design/PHASE1_FEATURE_DICTIONARY.csv').open(encoding='utf-8-sig') as f:features={r['variable_id']:r for r in csv.DictReader(f)}
    spec=load('design/PHASE1_RESEARCH_SPEC_DRAFT.json')
    record('Y_is_signed_adjacent_calendar_week_price_ratio',spec['confirmed']['target']=='100*(P_sox[w]/P_sox[w-1]-1)','No abs, no rolling5, source02 Close. Formula inspected as text; no observed Y computed.')
    record('core_M0_plus_F1_only',set(spec['information_sets']['C-M1'])-set(spec['information_sets']['C-M0'])=={'F1'} and len(spec['information_sets']['C-M0'])==10,'Different check: set difference + explicit ten baseline count.')
    record('volatility_and_rate_units','ddof=1' in features['B3']['formula'] and features['B10']['unit']=='bp' and features['B10']['formula'].startswith('100*'),'Daily percent-return sample SD; DGS10 percentage-point difference times100 bp. No numeric X built.')
    record('Wilder_SMA_seed_and_recursion','sum(first14 gains)/14' in features['B4']['formula'] and '13*A_prev' in features['B4']['formula'],'Independent formula text check; min15 prices, no default pandas ewm seed substituted.')
    local=ZoneInfo('America/New_York')
    jan=datetime(2026,1,15,9,tzinfo=local).astimezone(timezone.utc).hour
    jul=datetime(2026,7,15,9,tzinfo=local).astimezone(timezone.utc).hour
    record('DST_09_ET_varies_UTC',jan==14 and jul==13,'Timezone-only synthetic checks: January14UTC vsJuly13UTC; not an actual financial-session mapping.')
    d=date(2020,12,31);mon=d-timedelta(days=d.weekday());same=date(2021,1,1)-timedelta(days=date(2021,1,1).weekday())
    record('year_crossing_week_not_split',mon==same==date(2020,12,28),'Calendar-only week identifier check. Does not inspect or calculate labels.')
    record('minimum_training_threshold_proposed',spec['proposed']['minimum_training_weeks']==156 and spec['phase_status']=='REQUIRES_APPROVAL','156 is a proposal, not actual achieved sample count.')
    record('rolling_calendar_window_not_row_count','calendar_years' in spec['proposed']['windows'][1],'Missing weeks must not extend window to collect260 usable rows.')
    docs={p.stem:p.read_text(encoding='utf-8') for p in (P/'design').glob('*.md')}
    record('label_maturity_not_fixed_overlap_purge','label_available_at' in docs['PHASE1_Y_DEFINITION'] and '비중첩' in docs['PHASE1_WALKFORWARD_PROTOCOL'],'No inherited5-row purge. Historical availability still not demonstrated.')
    stat=docs['PHASE1_STATISTICAL_TEST_PLAN']
    record('loss_direction_correct','abs(Y_w−f0_w)−abs(Y_w−f1_w)' in stat and 'H0:E[d]<=0' in docs['PHASE1_MODEL_COMPARISON_SPEC'],'Positive Δ favors FGI; one-sided hypothesis separated from two-sided CI.')
    record('CW_squared_error_conditional_only','MAE 손실에 일반 적용하지 않는다' in stat and '선형 중첩' in stat and 'e0_w²' in stat,'CW text independently inspected against original paper conditions; no test executed.')
    record('bootstrap_missing_weeks_not_filled','달력 슬롯' in stat and 'n0 resample' in stat,'Gap/calendar block rule and pending resample validity decision explicitly disclosed.')
    record('FGI_current_gap_conflict_disclosed','21.15' in docs['PHASE1_FGI_POLICY'] and 'C04' in docs['CONFLICT_REGISTER'],'Existing known gap vs actual current value distinguished; no RAW changes.')
    missing=[];header_errors=[]
    for f in features.values():
        for path in f['raw_paths'].split(';'):
            p=ROOT/path
            if not p.is_file():missing.append(path)
            else:
                with p.open(encoding='utf-8-sig') as stream:
                    first=stream.readline()
                    line=stream.readline() if first.startswith('#') else first
                cols=next(csv.reader([line.strip()]))
                if any(c not in cols for c in f['source_columns'].split(';')):header_errors.append((f['variable_id'],path))
    record('independent_actual_paths_and_columns',not missing and not header_errors,str({'missing':missing,'header_errors':header_errors}))
    manifest=load('inputs/PHASE1_INPUT_MANIFEST.json');changed=[];index_allowed=[]
    for path,r in manifest['protected_files'].items():
        p=ROOT/path
        if not p.exists():changed.append(path);continue
        with p.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=r['sha256']:
            if path=='RESEARCH_PROJECT_INDEX.md' and hashlib.sha256(p.read_bytes()[:r['bytes']]).hexdigest()==r['sha256']:index_allowed.append(path)
            else:changed.append(path)
    record('independent_protected_hashes',not changed,f"{len(manifest['protected_files'])} files; unexpected={changed}; authorized append={index_allowed}")
    forbidden=[]
    for p in P.rglob('*.py'):
        tree=ast.parse(p.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                forbidden += [str(p) for a in node.names if a.name.split('.')[0] in ('sklearn','statsmodels','xgboost','lightgbm','yfinance','requests')]
            elif isinstance(node,ast.ImportFrom) and (node.module or '').split('.')[0] in ('sklearn','statsmodels','xgboost','lightgbm','yfinance','requests'):forbidden.append(str(p))
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('fit','predict','pct_change','ewm','rolling','corr','download','history'):forbidden.append(str(p))
    record('no_learning_forecasting_collection_calls',not forbidden,str(forbidden)+'; AST and work log are design-scope evidence, not OS-wide access monitoring.')
    record('all_open_items_not_locked',len(spec['open_decisions'])>=14 and all(d['status']=='REQUIRES_APPROVAL' for d in spec['open_decisions']),'Includes origin,FGI,feature/splits,posting assumptions,algorithms/windows,inference/bootstrap boundary approval.')
    ok=all(t['pass'] for t in tests)
    result={'phase':1,'design_independent_qc':'QC_PASS' if ok else 'QC_FAIL','overall_phase_state':'REQUIRES_APPROVAL','checks':tests,
      'limits':'Independent design checks only. Historical publication/vintage, actual weekly common sample, performance and calendar per-row mapping NOT VERIFIED.'}
    (P/'qc/PHASE1_INDEPENDENT_QC.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    text='# Phase1 독립 설계 QC\n\n'+result['design_independent_qc']+'; 전체 Phase 상태 REQUIRES_APPROVAL.\n\n|검사|결과|근거/범위|\n|---|---|---|\n'
    text+='\n'.join(f"|{r['name']}|{'PASS' if r['pass'] else 'FAIL'}|{r['evidence']}|" for r in tests)
    text+='\n\n자동QC/문서생성 함수를 import하지 않고 실제 열·경로·해시·사양을 별도 검사했다. 검토자는 별도 코드 경로를 사용한 동일 에이전트이며 독립 외부 연구자 검토로 표현하지 않는다. 시점가용성 미검증과 사용자 미승인은 해소되지 않았다. 주간 X/Y·학습·예측·성과 측정은 수행하지 않았다.\n'
    (P/'qc/PHASE1_INDEPENDENT_QC.md').write_text(text,encoding='utf-8')
    print(json.dumps({'independent_design_qc':result['design_independent_qc'],'checks':len(tests),'failures':[t['name'] for t in tests if not t['pass']]}))
    assert ok
if __name__=='__main__':main()
