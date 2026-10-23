from collections_ext.casedict import CaseDict

def test_exact_lookup():
    cd = CaseDict()
    cd['key'] = 'val'
    assert cd['key'] == 'val'
