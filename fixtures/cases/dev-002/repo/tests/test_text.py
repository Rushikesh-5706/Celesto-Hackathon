from pkg.text import clean_line

def test_clean_spaces():
    assert clean_line('  hello  ') == 'hello'
