from collections import OrderedDict

class SimpleLRU:
    def __init__(self, capacity: int = 2):
        self.capacity = capacity
        self.cache = OrderedDict()
    def get(self, k):
        return self.cache.get(k, None)
    def put(self, k, v):
        if len(self.cache) >= self.capacity and k not in self.cache:
            self.cache.popitem(last=False)
        self.cache[k] = v
