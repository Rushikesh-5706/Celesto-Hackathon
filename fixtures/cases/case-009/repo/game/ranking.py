def rank_players(players: list[dict]) -> list[str]:
    sorted_p = sorted(players, key=lambda p: p['score'], reverse=True)
    return [p['name'] for p in sorted_p]
