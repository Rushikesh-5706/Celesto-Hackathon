from game.ranking import rank_players

def test_distinct_scores():
    p = [{'name': 'A', 'score': 10}, {'name': 'B', 'score': 20}]
    assert rank_players(p) == ['B', 'A']
