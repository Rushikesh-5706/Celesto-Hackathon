"""Unit tests for statistical calculations per Section 16.1."""

from reprobox.harness.stats import compute_median, compute_p90, compute_summary_stats


def test_median_odd_and_even():
    # Odd count: exact middle
    assert compute_median([1.0, 3.0, 2.0]) == 2.0
    # Even count: mean of two middle
    assert compute_median([1.0, 2.0, 4.0, 5.0]) == 3.0
    assert compute_median([5.0, 1.0, 2.0, 4.0]) == 3.0  # unsorted


def test_p90_twenty_rows():
    # 20 items: 1-based rank ceil(0.90 * 20) = 18th item
    vals = list(range(1, 21))  # 1 to 20
    # 18th item is 18
    assert compute_p90(vals) == 18.0

    # Unsorted input
    import random
    shuffled = vals.copy()
    random.seed(42)
    random.shuffle(shuffled)
    assert compute_p90(shuffled) == 18.0


def test_summary_stats_calculation():
    runs = [
        {
            "sandbox_name": f"sbx-test{i:05d}",
            "fresh": True,
            "success": (i % 2 == 0),  # 10 successes out of 20
            "wall_clock_s": float(i * 10),
            "boot_to_ready_s": float(i),
            "cost_usd": 0.001,
        }
        for i in range(1, 21)
    ]

    stats = compute_summary_stats(runs)
    assert stats["run_count"] == 20
    assert stats["success_rate"] == 0.5
    # Wall clock median for 10..200: (100 + 110) / 2 = 105.0
    assert stats["median_wall_clock_s"] == 105.0
    # p90 for 10..200: 18th is 180.0
    assert stats["p90_wall_clock_s"] == 180.0
    # Boot median for 1..20: (10 + 11) / 2 = 10.5
    assert stats["median_boot_to_ready_s"] == 10.5
    assert stats["total_cost_usd"] == round(20 * 0.001, 6)
