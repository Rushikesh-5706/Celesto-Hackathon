"""Statistical calculations for evaluation runs."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def compute_median(values: Sequence[float]) -> float:
    """Compute median from sorted values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 1:
        return round(sorted_vals[n // 2], 3)
    # Even count: mean of two middle elements (1-based: n//2 and n//2 + 1)
    mid1 = sorted_vals[(n // 2) - 1]
    mid2 = sorted_vals[n // 2]
    return round((mid1 + mid2) / 2.0, 3)


def compute_p90(values: Sequence[float]) -> float:
    """Compute 90th percentile using rank ceil(0.90 * n) (1-based)."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    rank = math.ceil(0.90 * n)  # 1-based rank
    idx = max(0, min(rank - 1, n - 1))  # 0-based index
    return round(sorted_vals[idx], 3)


def compute_summary_stats(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Calculate summary metrics over a batch of evaluation runs."""
    run_count = len(runs)
    if run_count == 0:
        return {
            "run_count": 0,
            "success_rate": 0.0,
            "median_wall_clock_s": 0.0,
            "p90_wall_clock_s": 0.0,
            "median_boot_to_ready_s": 0.0,
            "total_cost_usd": 0.0,
        }

    successes = sum(1 for r in runs if r.get("success") is True)
    success_rate = round(successes / run_count, 4)

    wall_clocks = [float(r["wall_clock_s"]) for r in runs]
    boot_times = [float(r["boot_to_ready_s"]) for r in runs]
    total_cost = round(sum(float(r.get("cost_usd", 0.0)) for r in runs), 6)

    return {
        "run_count": run_count,
        "success_rate": success_rate,
        "median_wall_clock_s": compute_median(wall_clocks),
        "p90_wall_clock_s": compute_p90(wall_clocks),
        "median_boot_to_ready_s": compute_median(boot_times),
        "total_cost_usd": total_cost,
    }
