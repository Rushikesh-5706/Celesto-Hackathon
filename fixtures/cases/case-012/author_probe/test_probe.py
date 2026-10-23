from collections_ext.casedict import CaseDict

def test_case_insensitive_lookup():
    cd = CaseDict()
    cd['Host'] = 'localhost'
    assert cd['host'] == 'localhost'
