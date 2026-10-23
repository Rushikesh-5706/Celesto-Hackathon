def paginate(items: list, page: int, per_page: int) -> list:
    start = (page - 1) * per_page
    end = start + per_page - 1
    return items[start:end]
