def calculate_average(nums: list[float]) -> float:
    if not nums:
        return 0.0
    return sum(nums) / len(nums)
