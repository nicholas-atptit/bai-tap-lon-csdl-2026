"""Fail-closed checks for package acceptance evidence."""
def require_terminal_helper_verification(evidence,expected_ids):
    if evidence.get('method')!='CIM process recheck' or not evidence.get('observed_utc') or evidence.get('query_succeeded') is not True:
        raise AssertionError('Missing authoritative helper termination verification')
    if evidence.get('matching_processes')!=[]:
        raise AssertionError('Helper processes have not been proven absent')
    if set(evidence.get('scoped_worker_ids',[]))!=set(expected_ids):
        raise AssertionError('Termination verification belongs to a different helper')
