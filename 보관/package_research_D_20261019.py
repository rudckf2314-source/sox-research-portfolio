"""Package existing research_D read-only and verify every archived byte."""
from pathlib import Path
import os,stat,json,hashlib,zipfile,shutil,csv,io
ROOT=Path('C:/fgi_pilot');SRC=ROOT/'research_D';OUT=ROOT/'archives'
tag='20261019';i=0
while any((OUT/f'research_D_COMPLETE_{tag}{ext}').exists() for ext in ['.zip','.zip.partial','_REPORT.md','_MANIFEST.csv']):
    i+=1;tag=f'20261019_{i:02d}'
ZIP=OUT/f'research_D_COMPLETE_{tag}.zip';PART=ZIP.with_suffix('.zip.partial')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
rows=[];dirs=[]
for base,ds,fs in os.walk(SRC,followlinks=False):
    for name in ds+fs:
        p=Path(base)/name;st=p.lstat()
        if st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:raise RuntimeError('Link/reparse point requires separate review: '+str(p))
    dirs.append(Path(base))
    for name in sorted(fs):
        p=Path(base)/name
        if not p.is_file():raise RuntimeError('Not a regular file '+str(p))
        rows.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
print('Inventory',len(rows),'files',sum(r['bytes'] for r in rows),'bytes',flush=True)
for m in [SRC/'OUTPUT_MANIFEST.csv',SRC/'development_revision_v1/OUTPUT_MANIFEST.csv']:
    seal=m.with_suffix('.sha256');assert sha(m)==seal.read_text(encoding='utf-8-sig').split()[0]
    with m.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):assert sha(m.parent/r['path'])==r['sha256'],r['path']
total=sum(r['bytes'] for r in rows);assert shutil.disk_usage(OUT).free>total*1.2+100*1024*1024
buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=['path','bytes','sha256']);writer.writeheader();writer.writerows(rows);manifest=buffer.getvalue().encode('utf-8-sig')
note='''# 연구 D 압축본 안내

research_D 전체를 원래 하위 구조로 포함했습니다. 최초 Phase0~2, 1D 수정 비교, 코드·개발 데이터셋·모델·예측·결과·QC·환경 기록·인수인계서가 포함됩니다.

시작 문서: research_D/HANDOFF_20261019.md
최근 결과: research_D/development_revision_v1/RESULTS_KO.md

원본은 삭제·수정하지 않았습니다. data/raw 등 research_D 밖의 공통 RAW와 기존 연구 C·archives는 이 ZIP에 포함하지 않았습니다. 따라서 원천자료부터 전체 감사 코드를 재실행하려면 인수인계서와 입력 매니페스트에 기록된 외부 파일이 별도로 필요합니다. 개발용 처리 데이터와 저장 모델·예측은 research_D 안에 포함돼 있습니다.

BACKUP_MANIFEST.csv는 research_D 원본 파일 전체의 상대경로·크기·SHA-256입니다. 압축 후 각 엔트리의 해제 내용 SHA-256과 원본 재해시를 전수 비교합니다. ZIP 자체 해시는 압축파일 밖의 동명 REPORT에 기록합니다.
'''
with zipfile.ZipFile(PART,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
    for p in dirs:z.write(p,p.relative_to(ROOT).as_posix()+'/')
    for r in rows:z.write(ROOT/r['path'],r['path'])
    z.writestr('BACKUP_MANIFEST.csv',manifest);z.writestr('BACKUP_README.md',note)
print('ZIP written; checking CRC and all SHA-256',flush=True)
with zipfile.ZipFile(PART) as z:
    assert z.testzip() is None
    names=[x.filename for x in z.infolist() if not x.is_dir()];expected={r['path'] for r in rows}|{'BACKUP_MANIFEST.csv','BACKUP_README.md'}
    assert len(names)==len(set(names)) and set(names)==expected
    for r in rows:
        with z.open(r['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==r['sha256'],r['path']
    assert z.read('BACKUP_MANIFEST.csv')==manifest and z.read('BACKUP_README.md').decode('utf-8')==note
for r in rows:assert sha(ROOT/r['path'])==r['sha256'],r['path']
current={p.relative_to(ROOT).as_posix() for p in SRC.rglob('*') if p.is_file()}
assert current=={r['path'] for r in rows}
PART.rename(ZIP);zh=sha(ZIP)
(OUT/f'research_D_COMPLETE_{tag}_MANIFEST.csv').write_bytes(manifest)
(OUT/f'research_D_COMPLETE_{tag}_REPORT.md').write_text(f'# 연구 D ZIP 검증: PASS\n\n- ZIP: {ZIP}\n- 원본 파일 수: {len(rows)}\n- ZIP 파일 수: {len(rows)+2} (신규 백업 안내·manifest 2개 포함)\n- 원본 크기: {total} bytes\n- ZIP 크기: {ZIP.stat().st_size} bytes\n- ZIP SHA-256: {zh}\n- CRC / 경로·중복·누락 / 원본·해제 내용 SHA-256 / 원본 압축 전후 해시: PASS\n- 기존 연구 D 두 매니페스트 대조: PASS\n- 원본 수정·삭제: 없음\n- 외부 공통 RAW·기존 연구 C는 미포함. 상세는 ZIP의 BACKUP_README.md 참조.\n',encoding='utf-8')
result={'status':'PASS','zip':str(ZIP),'source_files':len(rows),'zip_files':len(rows)+2,'zip_bytes':ZIP.stat().st_size,'sha256':zh}
(OUT/f'research_D_COMPLETE_{tag}_STATUS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
