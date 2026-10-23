from storage.paths import resolve_subpath

def test_absolute_subpath_joined():
    assert resolve_subpath('/var/data', '/user/file.txt') == '/var/data/user/file.txt'
