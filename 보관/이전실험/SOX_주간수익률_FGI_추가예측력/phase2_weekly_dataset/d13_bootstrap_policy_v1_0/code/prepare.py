"""D13 후보 전용 입력 보호/메타데이터 감사. 시험 X/Y를 파싱하지 않는다."""
import csv, hashlib, json, platform, shutil
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[2]
BUILD = OUT.parent / 'build_v1_1'
LOCK = ROOT / 'research_C/phase1_research_design/approval_lock_v1_1'
ATTACH = Path(r'C:\Users\rudck\.codex\attachments\9c20c85e-96e6-4833-b78c-36f20a01351c\Pasted text.txt')

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def save(rel, obj):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8', newline='\n') as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def main():
    for d in ['inputs','policy','qc','reports','logs']:
        (OUT/d).mkdir(exist_ok=True)
    prior = load(BUILD/'qc/PHASE2B_INPUT_MANIFEST.json')['protected_files']
    errors = [r for r,v in prior.items() if not (ROOT/r).exists() or sha(ROOT/r)!=v['sha256']]
    manifest = BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.json'
    assert sha(manifest)==(BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for v in load(manifest)['files']:
        if sha(BUILD/v['path']) != v['sha256']: errors.append(v['path'])
    assert not errors, errors
    protected = dict(prior)
    for p in BUILD.rglob('*'):
        if p.is_file(): protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    refs = [ROOT/'Research_C_Study_Plan_v1_20261016.md',
        *[LOCK/s for s in ['PHASE1_LOCKED_SPEC_v1_1.md','PHASE1_LOCKED_SPEC_v1_1.json','PHASE1_APPROVED_DECISIONS.json','PHASE1_GATE_REGISTER.json']],
        LOCK.parent/'design/PHASE1_STATISTICAL_TEST_PLAN.md',
        *[BUILD/'reports'/s for s in ['PHASE2B_REPORT.md','PHASE2B_MISSINGNESS_REPORT.md','PHASE2B_HANDOFF.md','PHASE2B_D13_PREPARATION_REPORT.md']],
        BUILD/'qc/PHASE2B_QC.json', BUILD/'qc/PHASE2B_D10_GATE_RESULT.json',
        BUILD/'data/WEEKLY_SAMPLE_COUNTS.json', BUILD/'data/PAIRED_COMMON_WEEK_MEMBERSHIP.csv',
        BUILD/'data/COMMON_WEEK_CONTIGUOUS_RUNS.csv']
    read = []
    for p in refs:
        text=p.read_text(encoding='utf-8-sig')
        if p.suffix=='.json': json.loads(text)
        read.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'characters_read':len(text),'access':'text_metadata_or_policy'})
    save('inputs/USER_INSTRUCTION.txt',ATTACH.read_text(encoding='utf-8-sig'))
    save('inputs/D13_INPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'protected_files':protected,'protected_count':len(protected),'references_read':read,
        'user_instruction_sha256':sha(ATTACH),'prior_hash_mismatches':errors,
        'sealed_test_access':'binary SHA-256 only; no CSV decode, Y parse, or statistics',
        'environment':{'python':platform.python_version(),'numpy':np.__version__}})
    # This is the sole numeric-data reader: the file contains only dates/split/boolean flags.
    p=BUILD/'data/PAIRED_COMMON_WEEK_MEMBERSHIP.csv'
    with p.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        assert reader.fieldnames==['week_start','split','paired_common_valid']
        rows=list(reader)
    dates=[date.fromisoformat(r['week_start']) for r in rows]
    flags=[r['paired_common_valid']=='True' for r in rows]
    assert all(r['paired_common_valid'] in ['True','False'] for r in rows)
    assert len(rows)==823 and sum(flags)==818
    assert all((b-a).days==7 for a,b in zip(dates,dates[1:]))
    assert not any(flags[:5]) and all(flags[5:])
    counts={s:sum(v for r,v in zip(rows,flags) if r['split']==s) for s in ['initial_train','development','sealed_test']}
    assert counts=={'initial_train':308,'development':209,'sealed_test':301}
    summary={'calendar_weeks':len(rows),'common_valid':sum(flags),'first':str(dates[5]),'last':str(dates[-1]),
        'initial_missing_weeks':[str(x) for x in dates[:5]],'internal_missing_after_first_valid':0,'valid_by_split':counts,
        'test_error_count_known':False,'test_Y_values_read':False,'metadata_columns':list(rows[0])}
    expected=load(BUILD/'data/WEEKLY_SAMPLE_COUNTS.json')
    assert expected['paired_common_valid']==summary['common_valid']
    assert expected['paired_first_week']==summary['first'] and expected['paired_last_week']==summary['last']
    save('inputs/WEEKLY_METADATA_RECHECK.json',summary)
    save('inputs/METADATA_ACCESS_LOG.json',{'allowed_csv_paths':[p.relative_to(ROOT).as_posix()],
        'allowed_columns':list(rows[0]),'sealed_data_csv_parsed':0,'actual_loss_values_read':0})
    spec=load(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json')
    save('inputs/INHERITED_D08_D13.json',{'inference':spec['inference'],
        'decisions':[d for d in load(LOCK/'PHASE1_APPROVED_DECISIONS.json')['decisions'] if d['decision_id'] in ['D08','D13']]})
    print(json.dumps({'preflight':'PASS','protected':len(protected),'metadata':summary},ensure_ascii=False))

if __name__=='__main__': main()
