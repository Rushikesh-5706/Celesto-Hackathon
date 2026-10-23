from pkg.text import clean_line

def test_clean_newlines():
    assert clean_line('hello\n') == 'hello'
