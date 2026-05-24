from __future__ import annotations

import random


def choose_pivot(low: int, high: int, *, randomize: bool = True) -> int:
    """Choose a pivot index in [low, high)."""
    if low >= high:
        raise ValueError("low must be less than high")
    midpoint = (low + high) // 2
    if not randomize or high - low <= 2:
        return midpoint
    jitter = max(1, (high - low) // 6)
    start = max(low, midpoint - jitter)
    end = min(high - 1, midpoint + jitter)
    return random.randint(start, end)


def next_bounds(low: int, high: int, pivot: int, *, candidate_wins: bool) -> tuple[int, int]:
    if not low <= pivot < high:
        raise ValueError("pivot must be inside bounds")
    if candidate_wins:
        return low, pivot
    return pivot + 1, high
