import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delivery_gates import require_terminal_helper_verification
class DeliveryGateTests(unittest.TestCase):
    def test_stale_or_missing_receipt_is_not_terminal(self):
        with self.assertRaises(AssertionError):require_terminal_helper_verification({'Status':'RUNNING'},{1,2})
    def test_live_worker_cannot_pass(self):
        with self.assertRaises(AssertionError):require_terminal_helper_verification({'method':'CIM process recheck','observed_utc':'now','query_succeeded':True,'scoped_worker_ids':[1,2],'matching_processes':[{'ProcessId':1}]},{1,2})
    def test_authoritative_absence_passes(self):
        require_terminal_helper_verification({'method':'CIM process recheck','observed_utc':'now','query_succeeded':True,'scoped_worker_ids':[1,2],'matching_processes':[]},{1,2})
    def test_other_helper_receipt_cannot_pass(self):
        with self.assertRaises(AssertionError):require_terminal_helper_verification({'method':'CIM process recheck','observed_utc':'now','query_succeeded':True,'scoped_worker_ids':[9,10],'matching_processes':[]},{1,2})
if __name__=='__main__':unittest.main(verbosity=2)
