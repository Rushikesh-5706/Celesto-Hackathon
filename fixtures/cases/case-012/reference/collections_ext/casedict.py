class CaseDict:
    def __init__(self):
        self._d = {}
    def __setitem__(self, k, v):
        self._d[k.lower()] = v
    def __getitem__(self, k):
        return self._d[k.lower()]
    def get(self, k, default=None):
        return self._d.get(k.lower(), default)
