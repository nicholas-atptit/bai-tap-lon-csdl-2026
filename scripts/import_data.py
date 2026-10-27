"""Verified conflict-detecting renderer; public build uses synthetic data only."""
from pathlib import Path
import json,re,argparse
ROOT=Path(__file__).resolve().parents[1]
TABLES=['Market', 'Industry', 'Stock', 'Dataset', 'TradingDay', 'DailyPrice', 'StockIndex', 'IndexMembership', 'ForecastModel', 'TargetDefinition', 'ModelRun', 'ForecastOrigin', 'Prediction']

KEYS={'Market':['MarketId'],'Industry':['IndustryId'],'Stock':['StockId'],'Dataset':['DatasetId'],'TradingDay':['DatasetId','TradeDate'],
 'DailyPrice':['DatasetId','StockId','TradeDate'],'StockIndex':['IndexId'],'IndexMembership':['IndexId','StockId','ValidFrom'],
 'ForecastModel':['ModelId'],'TargetDefinition':['TargetId'],'ModelRun':['RunId'],'ForecastOrigin':['RunId','OriginDate'],'Prediction':['RunId','StockId','OriginDate']}

def literal(x):
    if x is None: return 'NULL'
    if isinstance(x,(int,float)): return str(x)
    return "N'"+str(x).replace("'","''")+"'"

def render(d,database='MarketLabVN30_Demo'):
    if not re.fullmatch(r'MarketLabVN30_[A-Za-z0-9_]+',database): raise ValueError('Unsafe database name')
    lines=[f'USE [{database}];','GO','SET NOCOUNT ON; SET XACT_ABORT ON;','BEGIN TRY',' BEGIN TRANSACTION;',
       ' CREATE TABLE #ImportReceipt(TableName sysname,RowsInput int,RowsInserted int);',' DECLARE @Added int;']
    for t in TABLES:
        rows=d[t]
        if not rows: continue
        cols=list(rows[0]); qcols=','.join(f'[{c}]' for c in cols)
        join=' AND '.join(f'd.[{c}]=v.[{c}]' for c in KEYS[t])
        dc=','.join(f'd.[{c}]' for c in cols); vc=','.join(f'v.[{c}]' for c in cols)
        lines.append(' SET @Added=0;')
        for k in range(0,len(rows),200):
            vals=',\n'.join('('+','.join(literal(r[c]) for c in cols)+')' for r in rows[k:k+200])
            src=f'(VALUES\n{vals}\n) v({qcols})'
            lines.append(f" IF EXISTS(SELECT 1 FROM dbo.[{t}] d JOIN {src} ON {join} WHERE EXISTS(SELECT {dc} EXCEPT SELECT {vc})) THROW 51100,N'Import conflict: {t}',1;")
            lines.append(f' INSERT dbo.[{t}]({qcols}) SELECT {vc} FROM {src} WHERE NOT EXISTS(SELECT 1 FROM dbo.[{t}] d WITH(UPDLOCK,HOLDLOCK) WHERE {join});')
            lines.append(' SET @Added=@Added+@@ROWCOUNT;')
        lines.append(f" INSERT #ImportReceipt VALUES(N'{t}',{len(rows)},@Added);")
    lines += [' COMMIT;',' SELECT TableName,RowsInput,RowsInput-RowsInserted AS RowsAlreadyPresent,RowsInserted FROM #ImportReceipt ORDER BY TableName;',' DROP TABLE #ImportReceipt;','END TRY','BEGIN CATCH',' IF XACT_STATE()<>0 ROLLBACK;',' THROW;','END CATCH;','GO']
    return '\n'.join(lines)+'\n'

def main():
    parser=argparse.ArgumentParser(description='Rebuild the standalone synthetic SQL without replacing approved files')
    parser.add_argument('--output',type=Path,default=ROOT/'tests/generated/all_in_one.sql')
    args=parser.parse_args()
    demo=json.loads((ROOT/'data/sample/tables.json').read_text(encoding='utf-8'))
    if any(s['IsSynthetic']!=1 or not s['Ticker'].startswith('DEMO') for s in demo['Stock']):raise ValueError('Synthetic data required')
    sample='-- SYNTHETIC DATA ONLY. No actual VN30 prices or forecasts.\n'+render(demo)
    parts=['00_create_database.sql','01_create_tables.sql','02_constraints_indexes.sql','03_insert_sample_data.sql','04_functions.sql','05_views.sql','06_stored_procedures.sql']
    text='\n'.join('-- FILE: '+p+'\n'+(sample if p=='03_insert_sample_data.sql' else (ROOT/'sql'/p).read_text(encoding='utf-8-sig')) for p in parts)+'\nSET NOEXEC OFF;\n'
    if args.output.resolve()==(ROOT/'sql/all_in_one.sql').resolve():raise ValueError('Use a derivative output, preserve approved SQL')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():raise FileExistsError(args.output)
    args.output.write_text(text,encoding='utf-8-sig')
    if args.output.read_bytes()!=(ROOT/'sql/all_in_one.sql').read_bytes():raise AssertionError('Rebuilt SQL differs from approved standalone SQL')
    print('PASS: rebuilt SQL is byte-identical to approved all_in_one.sql')
if __name__=='__main__':main()
