from storage.paths import resolve_subpath

def test_relative():
    assert resolve_subpath('/base', 'file.txt') == '/base/file.txt'
