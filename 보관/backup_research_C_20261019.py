import csv, hashlib, json, os, re, shutil, stat, zipfile
from pathlib import Path

ROOT = Path('C:/fgi_pilot')
SRC = ROOT / 'research_C'
OUT = ROOT / 'archives'
tag = '20261019'
i = 0
while any((OUT / n).exists() for n in [f'research_C_Phase4_FINAL_{tag}.zip', f'research_C_BACKUP_MANIFEST_{tag}.csv', f'research_C_BACKUP_REPORT_{tag}.md']):
    i += 1
    tag = f'20261019_{i:02d}'
REPORT = OUT / f'research_C_BACKUP_REPORT_{tag}.md'
ZIP = OUT / f'research_C_Phase4_FINAL_{tag}.zip'
cache = {}
def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()
def hashed(p):
    key = str(p)
    if key not in cache: cache[key] = digest(p)
    return cache[key]
def savecsv(name, fields, rows):
    with (OUT / name).open('x', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

files, links, errors, directories = [], [], [], []
for base, ds, fs in os.walk(SRC, followlinks=False):
    for n in list(ds):
        p = Path(base)/n
        if p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            links.append(str(p)); ds.remove(n)
        else: directories.append(p)
    for n in fs:
        p = Path(base)/n
        try:
            st = p.lstat()
            if st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT: links.append(str(p)); continue
            if not stat.S_ISREG(st.st_mode): errors.append(str(p)); continue
            files.append({'path': str(p.relative_to(ROOT)).replace('\\','/'), 'bytes': st.st_size, 'sha256': hashed(p)})
        except Exception as e: errors.append(f'{p}: {e}')
print(f'Inventory: {len(files)} files, {sum(x["bytes"] for x in files)} bytes, links={len(links)}, errors={len(errors)}', flush=True)
savecsv(f'research_C_PREBACKUP_INVENTORY_{tag}.csv', ['path','bytes','sha256'], files)

checks = []
def check(manifest, rel, expected, base):
    p = Path(rel.replace('\\','/'))
    if not p.is_absolute(): p = base/p
    try: actual = hashed(p); status = 'PASS' if actual.lower()==expected.lower() else 'MISMATCH'
    except Exception as e: actual = str(e); status = 'UNREADABLE_OR_MISSING'
    checks.append({'manifest':str(manifest.relative_to(ROOT)), 'path':str(p), 'expected_sha256':expected, 'actual_sha256':actual, 'result':status})

for m in SRC.rglob('*.json'):
    if not ('MANIFEST' in m.name.upper() or ('PROTECTED' in m.name.upper() and 'HASH' in m.name.upper())): continue
    d = json.loads(m.read_text(encoding='utf-8-sig'))
    if not isinstance(d,dict): continue
    protected = d.get('protected_files', {})
    if not protected and 'PROTECTED' in m.name.upper(): protected = d
    if isinstance(protected,dict):
        for rel, v in protected.items():
            h = v.get('sha256') if isinstance(v,dict) else v
            if isinstance(h,str) and re.fullmatch('[0-9a-fA-F]{64}', h): check(m,rel,h,ROOT)
    entries = d.get('files',[])
    base = m.parent.parent if m.parent.name in ('qc','inputs') else m.parent
    if isinstance(entries,list):
        for v in entries:
            if isinstance(v,dict) and v.get('path') and v.get('sha256'): check(m,v['path'],v['sha256'],base)
for m in SRC.rglob('*.sha256'):
    for line in m.read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'^([0-9a-fA-F]{64})\s+\*?(.+)$',line)
        if match: check(m,match[2],match[1],m.parent)
savecsv(f'research_C_PROTECTED_HASH_AUDIT_{tag}.csv', ['manifest','path','expected_sha256','actual_sha256','result'], checks)
bad = [c for c in checks if c['result']!='PASS']
external = {}
for c in checks:
    p = Path(c['path'])
    if not p.is_relative_to(SRC): external[str(p)] = {'path':str(p), 'sha256':c['actual_sha256'], 'bytes':p.stat().st_size if p.is_file() else '', 'included_in_zip':False}
savecsv(f'research_C_EXTERNAL_DEPENDENCIES_{tag}.csv', ['path','sha256','bytes','included_in_zip'], list(external.values()))
total = sum(x['bytes'] for x in files)
free = shutil.disk_usage(OUT).free
summary = {'source':str(SRC),'files':len(files),'bytes':total,'free_bytes':free,'protected_checks':len(checks),'protected_failures':len(bad),'links':links,'errors':errors,'external_files':len(external)}
print(json.dumps(summary,ensure_ascii=True),flush=True)
if bad or errors or links or free < total*1.1 + 100*1024*1024:
    REPORT.write_text('# 연구 C 백업 결과: FAIL\n\n압축 전 무결성 확인에서 중단했습니다. ZIP은 생성하지 않았습니다. 원본 수정·이동·삭제 및 연구 재실행은 수행하지 않았습니다.\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n\n보호 해시 불일치·누락 상세: `research_C_PROTECTED_HASH_AUDIT_'+tag+'.csv`\n\n외부 의존성: `research_C_EXTERNAL_DEPENDENCIES_'+tag+'.csv`\n\n기존 보호 매니페스트와 현재 파일이 하나라도 다르면 중단하라는 사용자 지시를 적용했습니다. 역사적 승인 변경 여부를 이유로 불일치를 임의 면제하지 않았습니다.\n',encoding='utf-8')
    raise SystemExit(2)

tmp = ZIP.with_suffix('.zip.partial')
with zipfile.ZipFile(tmp,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
    for p in [SRC]+directories: z.write(p,p.relative_to(ROOT).as_posix()+'/')
    for row in files: z.write(ROOT/row['path'],row['path'])
print('ZIP created; independently checking CRC and decompressed SHA-256',flush=True)
with zipfile.ZipFile(tmp) as z:
    if z.testzip() is not None: raise RuntimeError('CRC failed')
    names = [x.filename for x in z.infolist() if not x.is_dir()]
    expected = {x['path'] for x in files}
    if len(names)!=len(set(names)) or set(names)!=expected: raise RuntimeError('ZIP paths/count mismatch')
    for row in files:
        h=hashlib.sha256()
        with z.open(row['path']) as f:
            for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
        if h.hexdigest()!=row['sha256']: raise RuntimeError('ZIP SHA mismatch: '+row['path'])
print('Rehashing original files',flush=True)
for row in files:
    if digest(ROOT/row['path'])!=row['sha256']: raise RuntimeError('Original changed: '+row['path'])
current = {p.relative_to(ROOT).as_posix() for p in SRC.rglob('*') if p.is_file()}
if current != expected: raise RuntimeError('Original file set changed')
for c in checks:
    if digest(Path(c['path'])) != c['actual_sha256']: raise RuntimeError('Protected file changed: '+c['path'])
tmp.rename(ZIP)
zh=digest(ZIP)
savecsv(f'research_C_BACKUP_MANIFEST_{tag}.csv',['original_relative_path','bytes','original_sha256','zip_relative_path','verification'],[{'original_relative_path':x['path'],'bytes':x['bytes'],'original_sha256':x['sha256'],'zip_relative_path':x['path'],'verification':'PASS'} for x in files])
REPORT.write_text(f'''# 연구 C 백업 결과: PASS

- 실제 원본: {SRC}
- ZIP: {ZIP}
- 원본 파일 수: {len(files)}
- ZIP 일반 파일 수: {len(names)}
- 원본 전체 크기: {total} bytes
- ZIP 크기: {ZIP.stat().st_size} bytes
- ZIP SHA-256: {zh}
- CRC 검사 / 경로·중복·누락 검사 / 압축 해제 내용 SHA-256 전수 비교: PASS
- 원본 압축 전후 SHA-256 변경: 0개
- 보호 해시 대조: {len(checks)}건 PASS; 압축 후 재확인 PASS
- 숨김파일 및 내부 가상환경 포함. 원본 변경·이동·삭제 없음.
- 링크: {len(links)}; 읽기 불가: {len(errors)}
- 사전 저장공간: {free} bytes

## 외부 의존성과 복원

연구 폴더 외부 참조 파일 {len(external)}개는 ZIP에 포함되지 않았습니다. 실제 경로·파일명·현재 SHA-256은 research_C_EXTERNAL_DEPENDENCIES_{tag}.csv에 기록했습니다. data/raw, 루트 연구계획서, 설정, freeze 등 외부 보호 입력도 별도 보관해야 합니다. 이 ZIP만으로 원천 RAW부터 전체 재현이 가능하다고 판정하지 않습니다.

ZIP을 프로젝트 루트에 풀어 research_C 하위 구조를 복원하고 외부 파일은 의존성 목록의 원래 경로에 복원해야 합니다. 내부 실행환경·패키지 기록은 보존했지만 가상환경은 다른 PC에서 재생성이 필요할 수 있습니다. 코드의 절대경로도 확인해야 합니다. 학습모델·전처리 직렬화 파일의 존재만으로 모든 원점의 모델이 저장됐다고 보장하지 않습니다. 이번 검토에서는 기존 실험을 재실행하지 않았습니다.

원본 전체 목록은 PREBACKUP_INVENTORY, 보호 대조는 PROTECTED_HASH_AUDIT, ZIP 대조 결과는 BACKUP_MANIFEST CSV를 참조하십시오. 모든 신규 산출물은 archives 아래에만 생성했습니다. 최종 백업 무결성 PASS는 연구 폴더 보존을 의미하며 외부 의존성의 ZIP 포함을 의미하지 않습니다.
''',encoding='utf-8')
print(json.dumps({'result':'PASS','zip':str(ZIP),'files':len(files),'zip_bytes':ZIP.stat().st_size,'zip_sha256':zh},ensure_ascii=True),flush=True)
