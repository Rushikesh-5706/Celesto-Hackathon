from cache.lru import SimpleLRU

def test_basic_put():
    lru = SimpleLRU(2)
    lru.put('a', 1)
    assert lru.get('a') == 1
