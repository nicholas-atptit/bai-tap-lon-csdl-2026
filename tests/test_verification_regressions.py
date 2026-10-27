"""Regression tests for false-green evidence handling and chunked SQL JSON."""
import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verification_common import parse_json_output,require_run_coverage

class EvidenceTests(unittest.TestCase):
    def test_missing_json_is_not_empty_result(self):
        with self.assertRaises(ValueError):parse_json_output('Changed database context; no result emitted')
    def test_actual_empty_array_is_valid(self):
        self.assertEqual(parse_json_output('header\n[]\n'),[])
    def test_json_chunks_inside_unicode_string(self):
        expected=[{'text':'Đối chiếu '*600,'escaped_newline':'one\ntwo'}]
        encoded=json.dumps(expected,ensure_ascii=False)
        chunked='\r\n'.join(encoded[i:i+2033] for i in range(0,len(encoded),2033))
        self.assertEqual(parse_json_output(chunked),expected)
    def test_empty_metrics_cannot_pass(self):
        with self.assertRaises(AssertionError):require_run_coverage([],{1,2})
    def test_missing_run_cannot_pass(self):
        with self.assertRaises(AssertionError):require_run_coverage([{'RunId':1}],{1,2})
    def test_duplicate_run_cannot_pass(self):
        with self.assertRaises(AssertionError):require_run_coverage([{'RunId':1},{'RunId':1}],{1,2})
    def test_complete_run_set(self):
        require_run_coverage([{'RunId':2},{'RunId':1}],{1,2})

if __name__=='__main__':unittest.main(verbosity=2)
