from nlp.tokenizer import tokenize_words

def test_multiple_spaces():
    assert tokenize_words('hello   world') == ['hello', 'world']
