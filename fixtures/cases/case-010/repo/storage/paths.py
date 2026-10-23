import os

def resolve_subpath(base: str, rel: str) -> str:
    return os.path.join(base, rel)
