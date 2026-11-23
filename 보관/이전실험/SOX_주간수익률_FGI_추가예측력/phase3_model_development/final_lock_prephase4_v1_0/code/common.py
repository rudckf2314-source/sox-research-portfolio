"""Phase3 최종 LOCK/사전감사 전용. 실증 모델/시험자료 로더 없음."""
import csv,hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
DEV=OUT.parent/'development_v1_0'
BUILD=ROOT/'research_C/phase2_weekly_dataset/build_v1_1'
P1=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
D13=ROOT/'research_C/phase2_weekly_dataset/d13_bootstrap_policy_v1_0/approval_lock_v1_0'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(rel,x):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def csvread(p):
    assert 'sealed_test' not in p.parts
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
