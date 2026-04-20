from __future__ import annotations

from dataclasses import dataclass

from .common import deletion_share, median, stable_hash


class FrequencyEstimator:
    name = "base"

    def update(self, item: int, delta: int) -> None:
        raise NotImplementedError

    def estimate(self, item: int) -> int:
        raise NotImplementedError

    def space_bytes(self) -> int:
        raise NotImplementedError

    def config(self) -> str:
        return ""


class WeightedMisraGriesSummary:
    def __init__(self, capacity: int) -> None:
        self.capacity = max(1, capacity)
        self.counters: dict[int, int] = {}

    def update(self, item: int, weight: int = 1) -> None:
        if weight <= 0:
            return
        while weight > 0:
            if item in self.counters:
                self.counters[item] += weight
                return
            if len(self.counters) < self.capacity:
                self.counters[item] = weight
                return
            minimum = min(self.counters.values())
            delta = min(weight, minimum)
            for key in list(self.counters):
                self.counters[key] -= delta
                if self.counters[key] == 0:
                    del self.counters[key]
            weight -= delta

    def estimate(self, item: int) -> int:
        return self.counters.get(item, 0)

    def words(self) -> int:
        return 2 * self.capacity


class WeightedSpaceSavingSummary:
    def __init__(self, capacity: int) -> None:
        self.capacity = max(1, capacity)
        self.counters: dict[int, int] = {}
        self.errors: dict[int, int] = {}

    def update(self, item: int, weight: int = 1) -> None:
        if weight <= 0:
            return
        if item in self.counters:
            self.counters[item] += weight
            return
        if len(self.counters) < self.capacity:
            self.counters[item] = weight
            self.errors[item] = 0
            return
        victim = min(self.counters, key=self.counters.get)
        victim_count = self.counters[victim]
        del self.counters[victim]
        del self.errors[victim]
        self.counters[item] = victim_count + weight
        self.errors[item] = victim_count

    def estimate(self, item: int) -> int:
        return self.counters.get(item, 0)

    def words(self) -> int:
        return 3 * self.capacity


@dataclass
class DualSummaryAllocation:
    positive_slots: int
    negative_slots: int
    total_words: int


def _split_summary_budget(alpha: float, total_words: int, words_per_slot: int) -> DualSummaryAllocation:
    neg_ratio = deletion_share(alpha)
    negative_slots = max(1, int(total_words * neg_ratio / words_per_slot))
    positive_slots = max(1, int(total_words / words_per_slot) - negative_slots)
    used_words = (positive_slots + negative_slots) * words_per_slot
    return DualSummaryAllocation(
        positive_slots=positive_slots,
        negative_slots=negative_slots,
        total_words=used_words,
    )


def _words_from_budget(budget_bytes: int, minimum_words: int) -> int:
    return max(minimum_words, budget_bytes // 8)


class AlphaAwareTurnstileMisraGries(FrequencyEstimator):
    name = "Misra-Gries"

    def __init__(self, alpha: float, budget_bytes: int = 4096) -> None:
        total_words = _words_from_budget(budget_bytes, minimum_words=16)
        allocation = _split_summary_budget(alpha, total_words, words_per_slot=2)
        self.positive = WeightedMisraGriesSummary(allocation.positive_slots)
        self.negative = WeightedMisraGriesSummary(allocation.negative_slots)
        self.allocation = allocation

    def update(self, item: int, delta: int) -> None:
        if delta >= 0:
            self.positive.update(item, delta)
        else:
            self.negative.update(item, -delta)

    def estimate(self, item: int) -> int:
        return max(0, self.positive.estimate(item) - self.negative.estimate(item))

    def space_bytes(self) -> int:
        return self.allocation.total_words * 8

    def config(self) -> str:
        return f"pos_slots={self.positive.capacity},neg_slots={self.negative.capacity}"


class AlphaAwareTurnstileSpaceSaving(FrequencyEstimator):
    name = "Space-Saving"

    def __init__(self, alpha: float, budget_bytes: int = 4096) -> None:
        total_words = _words_from_budget(budget_bytes, minimum_words=18)
        allocation = _split_summary_budget(alpha, total_words, words_per_slot=3)
        self.positive = WeightedSpaceSavingSummary(allocation.positive_slots)
        self.negative = WeightedSpaceSavingSummary(allocation.negative_slots)
        self.allocation = allocation

    def update(self, item: int, delta: int) -> None:
        if delta >= 0:
            self.positive.update(item, delta)
        else:
            self.negative.update(item, -delta)

    def estimate(self, item: int) -> int:
        return max(0, self.positive.estimate(item) - self.negative.estimate(item))

    def space_bytes(self) -> int:
        return self.allocation.total_words * 8

    def config(self) -> str:
        return f"pos_slots={self.positive.capacity},neg_slots={self.negative.capacity}"


class CountMinCore:
    def __init__(self, depth: int, width: int, seed_offset: int) -> None:
        self.depth = depth
        self.width = max(8, width)
        self.seed_offset = seed_offset
        self.tables = [[0 for _ in range(self.width)] for _ in range(self.depth)]

    def update(self, item: int, weight: int) -> None:
        for row in range(self.depth):
            column = stable_hash(item, self.seed_offset + row) % self.width
            self.tables[row][column] += weight

    def estimate(self, item: int) -> int:
        estimates = []
        for row in range(self.depth):
            column = stable_hash(item, self.seed_offset + row) % self.width
            estimates.append(self.tables[row][column])
        return min(estimates)

    def words(self) -> int:
        return self.depth * self.width


class AlphaAwareCountMinSketch(FrequencyEstimator):
    name = "Count-Min Sketch"

    def __init__(self, alpha: float, budget_bytes: int = 4096, depth: int = 5) -> None:
        del alpha
        total_words = _words_from_budget(budget_bytes, minimum_words=depth * 8)
        self.core = CountMinCore(depth, total_words // depth, seed_offset=101)
        self.total_words = self.core.words()

    def update(self, item: int, delta: int) -> None:
        self.core.update(item, delta)

    def estimate(self, item: int) -> int:
        return max(0, self.core.estimate(item))

    def space_bytes(self) -> int:
        return self.total_words * 8

    def config(self) -> str:
        return f"{self.core.depth}x{self.core.width}"


class AlphaAwareCountSketch(FrequencyEstimator):
    name = "Count-Sketch"

    def __init__(self, alpha: float, budget_bytes: int = 4096, depth: int = 5) -> None:
        total_words = _words_from_budget(budget_bytes, minimum_words=depth * 16)
        self.depth = depth
        self.width = max(16, total_words // depth)
        self.tables = [[0 for _ in range(self.width)] for _ in range(self.depth)]
        self.total_words = self.depth * self.width

    def update(self, item: int, delta: int) -> None:
        if delta == 0:
            return
        for row in range(self.depth):
            column = stable_hash(item, 2001 + row) % self.width
            sign = 1 if (stable_hash(item, 3001 + row) & 1) == 0 else -1
            self.tables[row][column] += delta * sign

    def estimate(self, item: int) -> int:
        row_estimates = []
        for row in range(self.depth):
            column = stable_hash(item, 2001 + row) % self.width
            sign = 1 if (stable_hash(item, 3001 + row) & 1) == 0 else -1
            row_estimates.append(self.tables[row][column] * sign)
        return max(0, int(round(median(row_estimates))))

    def space_bytes(self) -> int:
        return self.total_words * 8

    def config(self) -> str:
        return f"{self.depth}x{self.width}"


def build_algorithm_suite(alpha: float, budget_bytes: int = 4096) -> list[FrequencyEstimator]:
    return [
        AlphaAwareTurnstileMisraGries(alpha=alpha, budget_bytes=budget_bytes),
        AlphaAwareTurnstileSpaceSaving(alpha=alpha, budget_bytes=budget_bytes),
        AlphaAwareCountMinSketch(alpha=alpha, budget_bytes=budget_bytes),
        AlphaAwareCountSketch(alpha=alpha, budget_bytes=budget_bytes),
    ]
