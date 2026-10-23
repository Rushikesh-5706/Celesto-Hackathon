from slugger.slug import slugify

def test_ascii_slug():
    assert slugify('Hello World') == 'hello-world'
