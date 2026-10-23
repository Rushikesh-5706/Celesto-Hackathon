from nlp.tokenizer import tokenize_words

def test_single_space():
    assert tokenize_words('a b') == ['a', 'b']
