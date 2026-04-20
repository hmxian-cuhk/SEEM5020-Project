from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Iterable

Update = tuple[int, int]


def stable_hash(value: int, seed: int) -> int:
    payload = f"{seed}:{value}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def median(values: list[float]) -> float:
    ordered = sorted(values)
    size = len(ordered)
    mid = size // 2
    if size % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def top_items(counter: Counter[int], k: int) -> list[tuple[int, int]]:
    return counter.most_common(k)


def relative_error(estimate: float, truth: float) -> float:
    if truth <= 0:
        return 0.0
    return abs(estimate - truth) / truth


def weighted_choice(rng, weighted_counts: dict[int, int] | Counter[int]) -> int:
    total = sum(weighted_counts.values())
    if total <= 0:
        raise ValueError("weighted_choice requires a positive total weight")
    threshold = rng.randrange(total)
    cumulative = 0
    for item, weight in weighted_counts.items():
        cumulative += weight
        if threshold < cumulative:
            return item
    raise RuntimeError("weighted_choice failed to select an item")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def average(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / max(1, len(values))


def deletion_share(alpha: float) -> float:
    theoretical = max(0.0, (alpha - 1.0) / (2.0 * alpha))
    return min(0.45, max(0.10, theoretical))
