from csvtool.parser import parse_csv_rows

def test_multiline_csv():
    content = 'id,text\n1,"line1\nline2"'
    rows = parse_csv_rows(content)
    assert len(rows) == 2
