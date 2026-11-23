"""연구 C Phase2-B v1.1 공통 입출력. 원본 파일 쓰기 금지."""
import csv,hashlib,json,math
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[2]
BASE=OUT.parent
AUDIT=BASE/'calendar_evidence_remediation_v1_0'
APPROVAL=AUDIT/'approval_E3_v1_0'
LOCK=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
NY=ZoneInfo('America/New_York')
TIMING='C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1'
CALPOL='C_DGS10_H15_HISTORICAL_CALENDAR_E3_CONDITIONAL_v1'
DAILY='C_DAILY_EOD_NEXT_US_SESSION_0800_ET_v1_1'
INSTRUCTION=Path(r'C:\Users\rudck\.codex\attachments\4e659ec2-df60-4470-8412-cd8712ad4cf0\Pasted text.txt')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def readcsv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(line for line in f if not line.startswith('#')))
def save(rel,obj):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def csvout(rel,rows,fields=None):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def number(x):
    try:
        f=float(x);return f if math.isfinite(f) else None
    except (ValueError,TypeError):return None
def stamp(d,h=9,m=0):return datetime.combine(date.fromisoformat(str(d)),datetime.min.time()).replace(hour=h,minute=m,tzinfo=NY)
def monday(d):return d-timedelta(days=d.weekday())
def dates(a,b):
    while a<=b:yield a;a+=timedelta(days=1)
def core():
    old=load(BASE/'build_v1_0/inputs/RAW_VERSION_AUDIT.json')
    return {x['dataset_id'].split('_')[0]:{'path':ROOT/x['path'],'df':readcsv(ROOT/x['path']),'sha256':x['sha256']} for x in old['core_hashes']}

def prepare():
    for x in ['inputs/sources','calendar','availability','data/train_dev','data/sealed_test','qc','reports','logs']:(OUT/x).mkdir(parents=True,exist_ok=True)
    prior=load(APPROVAL/'INPUT_MANIFEST.json');protected=dict(prior['protected_files'])
    sealed=load(APPROVAL/'OUTPUT_MANIFEST.json')
    assert sha(APPROVAL/'OUTPUT_MANIFEST.json')==(APPROVAL/'OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for x in sealed['files']:assert sha(APPROVAL/x['path'])==x['sha256']
    for p in APPROVAL.rglob('*'):
        if p.is_file():protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    bad=[r for r,v in protected.items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    assert not bad,bad
    refs=[ROOT/'Research_C_Study_Plan_v1_20261016.md',LOCK/'PHASE1_LOCKED_SPEC_v1_1.md',
        LOCK/'PHASE1_LOCKED_SPEC_v1_1.json',LOCK/'PHASE1_APPROVED_DECISIONS.json',LOCK/'PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json',LOCK/'PHASE1_GATE_REGISTER.json',
        BASE/'prebuild_D10_audit/approval_v1_0/D10_APPROVED_POLICY.md',BASE/'prebuild_D10_audit/approval_v1_0/D10_APPROVED_POLICY.json',
        AUDIT/'reports/D10_CALENDAR_REMEDIATION_REPORT.md',*[AUDIT/'audit'/f for f in ['H15_PUBLICATION_CALENDAR_EVIDENCE.csv','H15_CALENDAR_GAP_REGISTER.csv','H15_EXCEPTION_AND_DELAY_REGISTER.csv']],
        *[APPROVAL/f for f in ['D10_E3_APPROVED_POLICY.md','D10_E3_APPROVED_POLICY.json','D10_E3_GATE_STATUS.json','D10_E3_APPROVAL_HANDOFF.md']],
        BASE/'build_v1_0/reports/PHASE2B_REPORT.md',BASE/'build_v1_0/qc/PHASE2B_INDEPENDENT_QC.md']
    log=[]
    for p in refs:
        text=p.read_text(encoding='utf-8-sig');log.append({'path':str(p),'sha256':sha(p),'entire_file_read':True,'characters':len(text)})
    save('inputs/USER_INSTRUCTION.txt',INSTRUCTION.read_text(encoding='utf-8-sig'))
    raw=load(BASE/'build_v1_0/inputs/RAW_VERSION_AUDIT.json')
    inventory=[]
    for x in raw['inventory']:
        path=ROOT/x['path'];assert sha(path)==x['sha256'],x['path']
        inventory.append({'path':x['path'],'sha256':sha(path),'rows':len(readcsv(path))})
    assert len(inventory)==48 and len({str(Path(x['path']).parent) for x in inventory})==47
    save('inputs/RAW_VERSION_AUDIT.json',{'canonical_folders':47,'canonical_csv':48,'inventory':inventory,'all_unchanged':True})
    save('qc/PHASE2B_INPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'protected_files':protected,'count':len(protected),'mismatches':bad,'full_read_log':log,
        'instruction_sha256':sha(INSTRUCTION),'authorization':'Phase2-B implementation only; gated weekly build; no modeling or performance access'})
    raw_qc()

def raw_qc():
    c=core();facts={}
    for k,v in c.items():
        rows=v['df'];ds=[r['Date'] for r in rows];assert len(ds)==len(set(ds))
        facts[k]={'rows':len(rows),'min_date':min(ds),'max_date':max(ds),'missing_cells':sum(number(val) is None for r in rows for col,val in r.items() if col!='Date'), 'columns':list(rows[0])}
    assert facts['02']['max_date']=='2026-10-09'
    fgi_col=next(k for k in c['11']['df'][0] if 'score' in k.lower() or k.lower() in {'fgi','value','fear greed'})
    assert [number(r[fgi_col]) for r in c['11']['df'] if r['Date']=='2026-03-12']==[21.15]
    assert 'Adj Close' in facts['10']['columns']
    save('qc/RAW_PREFLIGHT_QC.json',{'status':'PASS','core':facts,'FGI_20260312_present':True,'HYG_Adj_Close_present':True,
        'index_Volume_used':False,'FGI_column':fgi_col})
    print('입력 보호·RAW 확인 PASS; protected='+str(load(OUT/'qc/PHASE2B_INPUT_MANIFEST.json')['count']))

if __name__=='__main__':
    import sys
    raw_qc() if '--raw-only' in sys.argv else prepare()
