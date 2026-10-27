"""Evidence validators retained from the verified original verifier."""
import json

def parse_json_output(text):
    start=text.find('['); end=text.rfind(']')
    if start<0 or end<start:
        raise ValueError('SQL returned no JSON array; missing evidence is not an empty result')
    # FOR JSON emits chunks; only raw line separators between chunks are removed.
    value=json.loads(text[start:end+1].replace('\r','').replace('\n',''))
    if not isinstance(value,list):raise ValueError('Expected a JSON array from SQL')
    return value

def require_run_coverage(actual,expected_run_ids):
    ids=[m['RunId'] for m in actual]
    if len(ids)!=len(set(ids)) or set(ids)!=set(expected_run_ids):
        raise AssertionError(f'Missing or duplicate model metrics: got {ids}, expected {sorted(expected_run_ids)}')
