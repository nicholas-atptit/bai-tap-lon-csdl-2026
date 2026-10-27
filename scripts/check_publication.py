"""Offline publication gate: exact allowlist, hashes, links, synthetic scope and secret patterns."""
from pathlib import Path
from urllib.parse import unquote,urlsplit
import argparse, csv, hashlib, json, re, subprocess, sys, xml.etree.ElementTree as ET, zipfile

ROOT=Path(__file__).resolve().parents[1]
GENERATED_PREFIXES=('tests/runs/','tests/generated/','tests/document_renders/')
CONTROLLED={'docs/PUBLICATION_ALLOWLIST.json','docs/PUBLICATION_AUDIT.md','tests/publication_evidence/offline_checks.json'}
def sha(data):return hashlib.sha256(data).hexdigest()
def files():
    return {p.relative_to(ROOT).as_posix():p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.relative_to(ROOT).parts and '__pycache__' not in p.parts and not p.relative_to(ROOT).as_posix().startswith(GENERATED_PREFIXES)}
def scan_text(text):
    patterns={
        'github_token':r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b',
        'aws_access_key':r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
        'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'api_secret':r'\bsk-[A-Za-z0-9_-]{24,}\b',
        'password_assignment':r'(?i)\b(?:password|pwd|api_key|client_secret)\s*[=:]\s*[\x22\x27][^\x22\x27\r\n]{6,}[\x22\x27]',
        'credential_url':r'https?://[^\s/@:]+:[^\s/@]+@',
    }
    return [name for name,pattern in patterns.items() if re.search(pattern,text)]
def check(staged=False):
    found=files()
    allow=json.loads((ROOT/'docs/PUBLICATION_ALLOWLIST.json').read_text(encoding='utf-8'))
    entries={x['path']:x for x in allow['files']}
    assert len(entries)==len(allow['files']),'Duplicate allowlist paths'
    assert set(found)==set(entries),{'unlisted':sorted(set(found)-set(entries)),'missing':sorted(set(entries)-set(found))}
    errors=[];review=[]
    for relative,path in sorted(found.items()):
        data=path.read_bytes();entry=entries[relative]
        assert not path.is_symlink(),relative
        assert entry['classification'] in {'implementation','synthetic_data','documentation','approved_reference','sanitized_evidence','verification','publication_control'},relative
        if relative not in CONTROLLED:
            assert len(data)==entry['bytes'] and sha(data)==entry['sha256'],relative+' hash mismatch'
        assert not any(part in {'private_prepared','raw','.env','.tools'} for part in path.relative_to(ROOT).parts),relative
        assert path.suffix.lower() not in {'.bak','.mdf','.ldf','.zip','.pyc','.tmp'},relative
        assert not path.name.startswith('~$'),relative
        texts=[]
        if path.suffix.lower() in {'.docx','.pptx'}:
            with zipfile.ZipFile(path) as z:
                assert z.testzip() is None
                assert not any(n.lower().endswith(('vbaproject.bin','.exe')) or '/embeddings/' in n for n in z.namelist()),relative
                for n in z.namelist():
                    if n.endswith(('.xml','.rels')):
                        raw=z.read(n).decode('utf-8');ET.fromstring(raw);texts.append(raw)
        elif path.suffix.lower() not in {'.pdf','.png'}:
            texts=[data.decode('utf-8-sig')]
        for text in texts:
            hits=scan_text(text)
            if hits:errors.append({'file':relative,'patterns':hits})
        review.append({'path':relative,'bytes':len(data),'sha256':sha(data),'text_or_office_parts_scanned':len(texts),'classification':entry['classification']})
    assert not errors,errors
    links=[]
    for relative,path in found.items():
        if path.suffix.lower()!='.md':continue
        content=path.read_text(encoding='utf-8')
        content=re.sub(r'```.*?```','',content,flags=re.S)
        for raw in re.findall(r'!?\[[^\]]*\]\(([^\n)]+)\)',content):
            target=raw.strip().split(' "',1)[0].strip('<>')
            parsed=urlsplit(target)
            if parsed.scheme or target.startswith('#'):continue
            resolved=(path.parent/unquote(parsed.path)).resolve()
            assert ROOT in resolved.parents or resolved==ROOT,(relative,target,'outside repository')
            assert resolved.exists(),(relative,target,'broken link')
            if parsed.fragment and resolved.suffix=='.md':
                # Headings are not used in the publication's internal links; report any future anchor for review.
                raise AssertionError((relative,target,'anchor requires explicit validation'))
            links.append({'from':relative,'to':target})
    ddl=(ROOT/'sql/01_create_tables.sql').read_text(encoding='utf-8-sig')
    table_names=re.findall(r'CREATE TABLE dbo\.(\w+)\s*\(',ddl,re.I)
    assert len(table_names)==len(set(table_names))==13
    assert 'TargetDate' not in re.search(r'CREATE TABLE dbo\.Prediction\((.*?)\n\);',ddl,re.S)[1]
    expected={
      '04_functions.sql':('FUNCTION',{'fn_CalculateReturn','fn_CheckPredictionDirection','fn_EligiblePredictions'}),
      '05_views.sql':('VIEW',{'vw_LatestStockPrice','vw_StudyUniverse','vw_VN30SnapshotJune2026','vw_ModelPerformance'}),
      '06_stored_procedures.sql':('PROCEDURE',{'usp_InsertDailyPrice','usp_AddPrediction','usp_GetModelPerformance','usp_CompareModels'})}
    for name,(kind,names) in expected.items():
        actual=set(re.findall(r'CREATE OR ALTER '+kind+r' dbo\.(\w+)',(ROOT/'sql'/name).read_text(encoding='utf-8-sig'),re.I))
        assert actual==names,(name,actual)
    defined=set(table_names)
    for name in ('02_constraints_indexes.sql',*expected):
        defined.update(re.findall(r'CREATE(?: OR ALTER)? (?:FUNCTION|VIEW|PROCEDURE|TRIGGER) dbo\.(\w+)',(ROOT/'sql'/name).read_text(encoding='utf-8-sig'),re.I))
    for path in (ROOT/'sql').glob('*.sql'):
        refs=set(re.findall(r'\bdbo\.\[?(\w+)\]?',path.read_text(encoding='utf-8-sig')))
        assert refs<=defined,(path.name,sorted(refs-defined))
    assert len(re.findall(r'^-- Q\d{2} \|',(ROOT/'sql/07_business_queries.sql').read_text(encoding='utf-8-sig'),re.M))==16
    parts=['00_create_database.sql','01_create_tables.sql','02_constraints_indexes.sql','03_insert_sample_data.sql','04_functions.sql','05_views.sql','06_stored_procedures.sql']
    joined='\n'.join('-- FILE: '+p+'\n'+(ROOT/'sql'/p).read_text(encoding='utf-8-sig') for p in parts)+'\nSET NOEXEC OFF;\n'
    assert (ROOT/'sql/all_in_one.sql').read_text(encoding='utf-8-sig')==joined,'Standalone SQL differs from components'
    demo=json.loads((ROOT/'data/sample/tables.json').read_text(encoding='utf-8'))
    assert set(demo)==set(table_names)
    assert len(demo['Stock'])==8 and len(demo['DailyPrice'])==280 and len(demo['Prediction'])==258 and len(demo['ForecastOrigin'])==34
    assert all(x['IsSynthetic']==1 and re.fullmatch('DEMO0[1-8]',x['Ticker']) for x in demo['Stock'])
    assert all(x['DataKind']=='SYNTHETIC' for x in demo['Dataset'])
    assert all(x['EvaluationClass']=='SYNTHETIC_TEST' for x in demo['ModelRun'])
    for table,rows in demo.items():
        with (ROOT/'data/sample'/(table+'.csv')).open(encoding='utf-8-sig',newline='') as handle:
            csvrows=list(csv.DictReader(handle))
        expected=[{k:'' if v is None else str(v) for k,v in row.items()} for row in rows]
        assert csvrows==expected,table+' CSV and JSON differ'
    columns=json.loads((ROOT/'tests/reference_evidence/schema_columns.json').read_text(encoding='utf-8'))
    foreign=json.loads((ROOT/'tests/reference_evidence/schema_foreign_keys.json').read_text(encoding='utf-8'))
    assert len(columns)==73 and {x['TableName'] for x in columns}==set(table_names)
    assert len(foreign)==18 and len({x['ForeignKey'] for x in foreign})==16
    manifest=json.loads((ROOT/'data/manifests/demo_manifest.json').read_text(encoding='utf-8'))
    for x in manifest['files']:
        assert (ROOT/x['path']).stat().st_size==x['bytes'] and sha((ROOT/x['path']).read_bytes())==x['sha256']
    ET.parse(ROOT/'docs/diagrams/marketlab_erd.svg')
    for path in [ROOT/'report/MarketLabVN30_Report.pdf',ROOT/'slides/MarketLabVN30_Presentation.pdf',ROOT/'docs/diagrams/marketlab_erd.pdf']:
        assert path.read_bytes().startswith(b'%PDF-')
    ppt=ROOT/'slides/MarketLabVN30_Presentation.pptx'
    with zipfile.ZipFile(ppt) as z:assert len([n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)])==14
    if staged:
        def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
        staged_names=git('ls-files','--stage','-z').decode('utf-8').split('\0')
        index={}
        for record in staged_names:
            if not record:continue
            metadata,name=record.split('\t',1);mode,oid,stage=metadata.split()
            assert mode=='100644' and stage=='0',(mode,name)
            data=git('cat-file','blob',oid)
            assert data==found[name].read_bytes(),name+' staged bytes differ from reviewed working bytes'
            index[name]={'blob_oid':oid,'bytes':len(data),'sha256':sha(data)}
        assert set(index)==set(entries),{'staged_extra':sorted(set(index)-set(entries)),'staged_missing':sorted(set(entries)-set(index))}
    result={'status':'PASS','scope':'Offline files and optional actual Git index; not SQL runtime or absolute secret assurance','file_count':len(found),'internal_markdown_links':len(links),'sql_tables':13,'queries':16,'procedures':4,'functions':3,'views':4,'secret_pattern_findings':0,'staged_index_verified':staged,'files_reviewed':review}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--staged',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args();result=check(a.staged)
    if a.output:
        if a.output.exists():raise FileExistsError(a.output)
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files_reviewed'},ensure_ascii=False))
