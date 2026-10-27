"""Safe regression on the existing synthetic demo; no deployment, reset, or research access."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import argparse, hashlib, json, math, re, subprocess, sys
from import_data import KEYS, ROOT, render
from verification_common import parse_json_output, require_run_coverage

DB='MarketLabVN30_Demo'
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()

class SQL:
    def __init__(self,server,out):
        self.server=server;self.out=out;self.calls=[]
        out.mkdir(parents=True,exist_ok=False)
    def execute(self,text,name,json_result=False,expected_code=None):
        path=self.out/(name+'.sql')
        if path.exists():raise FileExistsError(path)
        path.write_text(text,encoding='utf-8-sig')
        cmd=['sqlcmd','-S',self.server,'-E','-C','-No','-b','-l','8','-t','120','-f','65001','-w','65535','-i',str(path)]
        cmd+=['-y','0'] if json_result else ['-W','-s','|']
        p=subprocess.run(cmd,capture_output=True,encoding='utf-8',errors='strict')
        output=p.stdout+p.stderr
        self.calls.append({'name':name,'exit_code':p.returncode,'sql_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'expected_error':expected_code})
        (self.out/(name+'.log')).write_text(output,encoding='utf-8')
        if expected_code is not None:
            if not p.returncode or not re.search(rf'Msg {expected_code}\b',output):raise AssertionError(f'{name}: expected rejection {expected_code}')
        elif p.returncode:raise RuntimeError(f'{name}: sqlcmd exit {p.returncode}; retained log')
        return parse_json_output(p.stdout) if json_result else output
    def query(self,query,name):
        return self.execute(f"USE [{DB}];\nSET NOCOUNT ON;\nSELECT COALESCE(({query} FOR JSON PATH,INCLUDE_NULL_VALUES),N'[]') AS JsonPayload;\n",name,True)
    def snapshot(self,label):
        actual=self.query('SELECT name FROM sys.tables WHERE is_ms_shipped=0 ORDER BY name',label+'_tables')
        if {r['name'] for r in actual}!=set(KEYS):raise AssertionError('Unexpected table set')
        result={}
        for name,keys in KEYS.items():
            rows=self.query('SELECT * FROM dbo.['+name+'] ORDER BY '+','.join('['+k+']' for k in keys),label+'_'+name)
            result[name]={'rows':len(rows),'sha256_canonical_all_columns':digest(rows)}
        return result

def run(args):
    out=ROOT/'tests/runs'/('public_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    sql=SQL(args.server,out)
    receipt={'status':'RUNNING','scope':'Existing synthetic demo only; no schema deployment or research database operations','started_utc':datetime.now(timezone.utc).isoformat()}
    def save():
        receipt['sql_calls']=sql.calls
        (out/'PUBLIC_REGRESSION.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        # First operation is read-only scope verification. No writes are allowed before it succeeds.
        preflight=sql.execute((ROOT/'sql/10_preflight_live.sql').read_text(encoding='utf-8-sig'),'preflight')
        assert 'PREFLIGHT_PASS' in preflight
        receipt['engine']=sql.query("SELECT CAST(SERVERPROPERTY('Edition') AS nvarchar(100)) AS Edition,CAST(SERVERPROPERTY('ProductVersion') AS varchar(30)) AS Version",'engine')
        before=sql.snapshot('before')
        for n in (1,2):
            live=sql.execute((ROOT/'sql/09_live_demo.sql').read_text(encoding='utf-8-sig'),'live_demo_'+str(n))
            assert 'LIVE_DEMO_PASS' in live
        validation=sql.execute((ROOT/'sql/08_validation_tests.sql').read_text(encoding='utf-8-sig'),'validation_44')
        assert 'FAIL|' not in validation and re.search(r'PASS\|44\s',validation)
        queries=(ROOT/'sql/07_business_queries.sql').read_text(encoding='utf-8-sig')
        matches=list(re.finditer(r'-- (Q\d+) \| ([^\n]+)',queries));assert len(matches)==16
        query_receipts=[]
        for i,m in enumerate(matches):
            block=queries[m.start():matches[i+1].start() if i+1<len(matches) else len(queries)]
            block=re.sub(r'^GO\s*$','',block,flags=re.M)
            output=sql.execute(f'USE [{DB}];\nSET NOCOUNT OFF;\n'+block,'query_'+m[1])
            counts=re.findall(r'\((\d+) rows? affected\)',output);assert counts,(m[1],output)
            query_receipts.append({'id':m[1],'rows':int(counts[-1]),'status':'PASS'})
        fixture=json.loads((ROOT/'data/sample/tables.json').read_text(encoding='utf-8'))
        prices={(x['DatasetId'],x['StockId'],x['TradeDate']):float(x['ClosePrice']) for x in fixture['DailyPrice']}
        origins={(x['RunId'],x['OriginDate']):x['TargetDate'] for x in fixture['ForecastOrigin']}
        runs={x['RunId']:x for x in fixture['ModelRun']};datasets={x['DatasetId']:x for x in fixture['Dataset']}
        expected=defaultdict(list)
        for x in fixture['Prediction']:
            r=runs[x['RunId']];d=datasets[r['DatasetId']];target=origins[x['RunId'],x['OriginDate']]
            start=prices.get((r['DatasetId'],x['StockId'],x['OriginDate']));end=prices.get((r['DatasetId'],x['StockId'],target))
            if start is None or end is None or target>d['ObservedThrough'] or x['OriginDate']<=r['ValidationEnd']:continue
            y=int(end>start);p=float(x['ProbabilityPositive']);pred=int(p>=float(r['Threshold']))
            expected[x['RunId']].append((int(pred==y),(p-y)**2,-math.log(max(1e-12,p if y else 1-p))))
        actual=sql.query('SELECT RunId,EvaluatedRows,Accuracy,BrierScore,NaturalLogLoss FROM dbo.vw_ModelPerformance ORDER BY RunId','metrics')
        require_run_coverage(actual,runs.keys())
        metrics=[]
        for row in actual:
            data=expected[row['RunId']];assert row['EvaluatedRows']==len(data)==128
            independent={'RunId':row['RunId'],'EvaluatedRows':len(data)}
            for idx,key in enumerate(['Accuracy','BrierScore','NaturalLogLoss']):
                independent[key]=sum(v[idx] for v in data)/len(data)
                assert abs(row[key]-independent[key])<1e-9,(key,row,independent)
            metrics.append({'sql':row,'python':independent})
        # The same historical late-batch conflict fixture exercises complete rollback.
        import copy
        bad=copy.deepcopy(fixture)
        bad['Market'].append(dict(MarketId=90000,MarketCode='ROLLBACK_T',MarketName='Test',CurrencyCode='VND'))
        bad['Prediction'][0]['ProbabilityPositive']='0.1234567890123456'
        conflict=sql.execute(render(bad,DB),'controlled_import_conflict',expected_code=51100)
        assert 'Import conflict: Prediction' in conflict
        assert sql.query('SELECT MarketId FROM dbo.Market WHERE MarketId=90000','rollback_parent_check')==[]
        long=sql.query("SELECT REPLICATE(CAST(N'Đối chiếu ' AS nvarchar(max)),600) AS LongUnicode",'unicode_json_chunks')
        assert long==[{'LongUnicode':'Đối chiếu '*600}]
        after=sql.snapshot('after');assert before==after
        receipt.update(status='PASS',sql_cases=44,business_queries=query_receipts,preflight_runs=1,live_demo_runs=2,metrics=metrics,all_13_tables_unchanged=True,before=before,after=after,controlled_conflict_rollback='PASS',unicode_json_chunks='PASS',finished_utc=datetime.now(timezone.utc).isoformat())
        save();print(json.dumps({'status':'PASS','sql_cases':44,'queries':16,'live_demo_runs':2,'all_13_tables_unchanged':True,'evidence':str(out)},ensure_ascii=True))
    except BaseException as error:
        receipt.update(status='FAIL',error=repr(error));save();raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--server',default='.')
    run(parser.parse_args())
