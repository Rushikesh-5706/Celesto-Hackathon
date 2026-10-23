from auth.validator import is_valid_username

def test_valid_user():
    assert is_valid_username('alice_123')
