"""D13 LOCK 전용 입출력; 기존 자료는 읽기/해시만 허용."""
import hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parents[2]
CAND=OUT.parent
ROOT=CAND.parents[2]
BUILD=CAND.parent/'build_v1_1'
PHASE1=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(rel,obj):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:
        f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
