"""Snapshot inputs before the approval lock. No RAW values/weekly data are processed."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,csv

LOCK=Path(__file__).resolve().parents[1];OLD=LOCK.parent;ROOT=OLD.parents[1]
APPROVAL=Path(r'C:\Users\rudck\.codex\attachments\769599b2-3e2f-4077-ab24-36f79e95b143\Pasted text.txt')
REQUIRED=['reports/PHASE1_REPORT.md','reports/PHASE1_HANDOFF.md','design/PHASE1_OPEN_DECISIONS.md',
 'design/PHASE1_FEATURE_DICTIONARY.csv','design/PHASE1_AVAILABILITY_MATRIX.csv','design/PHASE1_RESEARCH_SPEC_DRAFT.json',
 'design/PHASE1_WALKFORWARD_PROTOCOL.md','design/PHASE1_MODEL_COMPARISON_SPEC.md','design/PHASE1_STATISTICAL_TEST_PLAN.md',
 'design/PHASE1_SEARCH_BUDGET_DRAFT.json','qc/PHASE1_QC.json','qc/PHASE1_INDEPENDENT_QC.md']
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    for d in ['inputs','code','qc','reports']:(LOCK/d).mkdir(parents=True,exist_ok=True)
    dest=LOCK/'inputs/PHASE1_LOCK_INPUT_MANIFEST.json';assert not dest.exists(),'Existing initial snapshot must not be overwritten'
    before=json.loads((OLD/'qc/PHASE1_OUTPUT_MANIFEST.json').read_text(encoding='utf-8'))
    mismatches=[r['path'] for r in before['files'] if not (OLD/r['path']).is_file() or sha(OLD/r['path'])!=r['sha256']]
    assert not mismatches,('Original Phase1 files differ from their manifest',mismatches)
    prior=json.loads((OLD/'inputs/PHASE1_INPUT_MANIFEST.json').read_text(encoding='utf-8'))
    paths={ROOT/r for r in prior['protected_files']}
    paths.update(p for p in OLD.rglob('*') if p.is_file() and not p.is_relative_to(LOCK))
    records={p.relative_to(ROOT).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)}
    readlog=[]
    for p in [ROOT/'Research_C_Study_Plan_v1_20261016.md',*[OLD/r for r in REQUIRED]]:
        text=p.read_text(encoding='utf-8-sig') # Entire file, not just its first rows.
        if p.suffix=='.json':json.loads(text)
        if p.suffix=='.csv':list(csv.DictReader(text.splitlines()))
        readlog.append({'path':str(p.resolve()),'sha256':sha(p),'read_entire_file':True,'characters':len(text)})
    (LOCK/'inputs/USER_APPROVAL_INSTRUCTION.txt').write_bytes(APPROVAL.read_bytes())
    output={'created_at_utc':datetime.now(timezone.utc).isoformat(),'approval_date_kst':'2026-10-17',
       'approval_source_path':str(APPROVAL),'approval_source_sha256':sha(APPROVAL),
       'source_design_version':'phase1-draft-20261016','source_design_path':str(OLD/'design/PHASE1_RESEARCH_SPEC_DRAFT.json'),
       'source_plan_path':str(ROOT/'Research_C_Study_Plan_v1_20261016.md'),'full_read_log':readlog,
       'previous_phase1_manifest_mismatches':mismatches,'protected_files':records,
       'authorized_exception':'Optional RESEARCH_PROJECT_INDEX.md append only: v1.1 path/state; preserve all original bytes',
       'future_phase_dirs_present_before':[p.name for p in OLD.parent.iterdir() if p.is_dir() and p.name.startswith(('phase2_','phase3_','phase4_','phase5_'))]}
    dest.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'protected_files':len(records),'required_documents_read':len(readlog),'original_phase1_changed':len(mismatches),'future_phase_dirs':output['future_phase_dirs_present_before']}))
if __name__=='__main__':main()
