import re, unicodedata

def slugify(text: str) -> str:
    norm = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '-', norm.lower()).strip('-')
