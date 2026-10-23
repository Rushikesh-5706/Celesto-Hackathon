import csv, io

def parse_csv_rows(content: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(content))
    return list(reader)
