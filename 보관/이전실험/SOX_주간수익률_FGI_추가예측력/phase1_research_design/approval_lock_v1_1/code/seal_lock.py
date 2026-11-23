"""Seal review outputs after passing checks; does not pass research data gates."""
from pathlib import Path
import hashlib,json
L=Path(__file__).resolve().parents[1]
def main():
    seal=L/'qc/LOCK_FINALIZATION.json';assert not seal.exists(),'Already sealed'
    a=json.loads((L/'qc/PHASE1_LOCK_QC.json').read_text(encoding='utf-8'))
    i=json.loads((L/'qc/PHASE1_LOCK_INDEPENDENT_QC.json').read_text(encoding='utf-8'))
    s=json.loads((L/'PHASE1_LOCKED_SPEC_v1_1.json').read_text(encoding='utf-8'))
    assert a['qc_status']==i['qc_status']=='QC_PASS'
    assert not s['phase2_execution_approved'] and not s['all_gates_passed']
    assert 'PENDING' not in (L/'reports/PHASE1_LOCK_REPORT.md').read_text(encoding='utf-8').replace('PENDING_PHASE2_PREBUILD_AUDIT','').replace('PENDING_WEEKLY_MISSINGNESS_AUDIT','').replace('GATE_PENDING','')
    data={'version':'1.1','approved_on_kst':'2026-10-17','status':'PHASE1_DESIGN_LOCKED_WITH_GATES',
          'approved_document_outputs_sealed':True,'D10_passed':False,'D13_passed':False,'phase2_execution_approved':False,
          'automatic_checks_passed':a['test_count'],'independent_checks_passed':i['test_count'],
          'note':'Document builders refuse overwrite once this marker exists; no data gate is passed by sealing documents.'}
    seal.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    files=sorted(p for p in L.rglob('*') if p.is_file() and p.name!='PHASE1_LOCK_OUTPUT_MANIFEST.json')
    manifest={'overall_status':data['status'],'file_count_including_this_manifest':len(files)+1,'self_excluded_from_hash':True,
              'files':[{'path':p.relative_to(L).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    (L/'qc/PHASE1_LOCK_OUTPUT_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'sealed_status':data['status'],'files':len(files)+1,'D10_passed':False,'D13_passed':False,'phase2_execution_approved':False}))
if __name__=='__main__':main()
