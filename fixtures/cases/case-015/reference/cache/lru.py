from collections import OrderedDict

class SimpleLRU:
    def __init__(self, capacity: int = 2):
        self.capacity = capacity
        self.cache = OrderedDict()
    def get(self, k):
        if k not in self.cache:
            return None
        self.cache.move_to_end(k)
        return self.cache[k]
    def put(self, k, v):
        if k in self.cache:
            self.cache.move_to_end(k)
        elif len(self.cache) >= self.capacity:
            self.cache.popitem(last=False)
        self.cache[k] = v
