from cache.lru import SimpleLRU

def test_access_prevents_eviction():
    lru = SimpleLRU(2)
    lru.put('a', 1)
    lru.put('b', 2)
    lru.get('a')  # access 'a'
    lru.put('c', 3)  # should evict 'b'
    assert lru.get('a') == 1
