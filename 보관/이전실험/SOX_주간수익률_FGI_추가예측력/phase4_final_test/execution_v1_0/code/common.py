"""Phase4 전용 입출력. 실험 이전 파일 쓰기 금지."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import csv,json,hashlib,math
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
DEV=ROOT/'research_C/phase3_model_development/development_v1_0'
FINAL=ROOT/'research_C/phase3_model_development/final_lock_prephase4_v1_0'
BUILD=ROOT/'research_C/phase2_weekly_dataset/build_v1_1'
P1=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
D13=ROOT/'research_C/phase2_weekly_dataset/d13_bootstrap_policy_v1_0/approval_lock_v1_0'
FEATURES=[f'B{i}' for i in range(1,11)]+['F1'];FAMILY=['OLS','Ridge','ElasticNet','RandomForest','HistGradientBoosting']
NAME={'OLS':'OLS','Ridge':'Ridge','ElasticNet':'Elastic Net','RandomForest':'Random Forest','HistGradientBoosting':'HistGradientBoosting'}
UTC=timezone.utc;NY=ZoneInfo('America/New_York')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(rel,obj):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def csvout(rel,rows,fields=None):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def event(stage,**kwargs):
    with (OUT/'logs/STAGE_ACCESS_LOG.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps({'utc':datetime.now(UTC).isoformat(),'kst':datetime.now(NY).astimezone(ZoneInfo('Asia/Seoul')).isoformat(),'stage':stage,**kwargs},ensure_ascii=False)+'\n')
def code_hashes():return {p.relative_to(OUT).as_posix():sha(p) for p in sorted((OUT/'code').glob('*.py'))}
def ensure_gate():
    g=load(OUT/'config/PHASE4_EXECUTION_AUTHORIZATION.json')
    assert g['PHASE4_PREEXECUTION_GATE']=='PASS' and g['PHASE4_EXECUTION_AUTHORIZATION']=='USER_APPROVED'
    assert g['code_hashes']==code_hashes(),'CODE_CHANGED_AFTER_GATE'
    return g
