def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    if not intervals: return []
    sorted_i = sorted(intervals, key=lambda x: x[0])
    res = [sorted_i[0]]
    for cur in sorted_i[1:]:
        if cur[0] <= res[-1][1]:
            res[-1][1] = max(res[-1][1], cur[1])
        else:
            res.append(cur)
    return res
