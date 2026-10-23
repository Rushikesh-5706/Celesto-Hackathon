from game.ranking import rank_players

def test_tie_breaking():
    p = [{'name': 'Zara', 'score': 50}, {'name': 'Alex', 'score': 50}]
    assert rank_players(p) == ['Alex', 'Zara']
