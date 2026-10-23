from slugger.slug import slugify

def test_accented_slug():
    assert slugify('Café') == 'cafe'
