def parse_csv_rows(content: str) -> list[list[str]]:
    lines = content.strip().split('\n')
    return [line.split(',') for line in lines]
