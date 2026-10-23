from csvtool.parser import parse_csv_rows

def test_simple_csv():
    assert parse_csv_rows('a,b\nc,d') == [['a', 'b'], ['c', 'd']]
