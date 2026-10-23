from auth.validator import is_valid_username

def test_invalid_characters_rejected():
    assert not is_valid_username('john!@#')
