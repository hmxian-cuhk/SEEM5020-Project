from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .common import tokenize, weighted_choice

PACKET_LINE_RE = re.compile(r"^\S+\s+(IP6?|ARP)\s+(\S+)\s+>\s+(\S+):")
WEIGHTED_UPDATE_VALUES = (1, 2, 4, 8)
WEIGHTED_UPDATE_PROBS = (8, 4, 2, 1)


@dataclass
class StreamRealization:
    stream: list[tuple[int, int]]
    final_frequencies: Counter[int]
    insertion_updates: int
    deletion_updates: int
    insertion_mass: int
    deletion_mass: int
    final_mass: int
    update_mode: str
    weight_model: str


def synthetic_distribution(kind: str, universe_size: int) -> dict[int, int]:
    if universe_size <= 0:
        raise ValueError("universe_size must be positive")
    if kind == "balanced":
        return {item: 1 for item in range(universe_size)}
    if kind == "skewed":
        return {item: max(1, int(1000 / ((item + 1) ** 1.15))) for item in range(universe_size)}
    raise ValueError(f"unknown synthetic distribution: {kind}")


def _sample_update_weight(
    rng,
    update_mode: str,
    min_weight: int = 1,
    max_weight: int | None = None,
) -> int:
    if min_weight <= 0:
        raise ValueError("min_weight must be positive")
    if update_mode == "unit":
        if max_weight is not None and max_weight < 1:
            raise ValueError("max_weight must allow a unit update")
        if min_weight > 1:
            raise ValueError("unit updates cannot exceed weight 1")
        return 1
    if update_mode != "weighted":
        raise ValueError(f"unknown update_mode: {update_mode}")
    if max_weight is not None and max_weight <= 0:
        raise ValueError("max_weight must be positive when provided")
    sampled = rng.choices(WEIGHTED_UPDATE_VALUES, weights=WEIGHTED_UPDATE_PROBS, k=1)[0]
    if max_weight is None:
        return max(sampled, min_weight)
    if max_weight < min_weight:
        raise ValueError("max_weight must be at least min_weight")
    return min(max(sampled, min_weight), max_weight)


def _deletion_event_count(total_operations: int, alpha: float) -> int:
    return int(total_operations * (alpha - 1.0) / (2.0 * alpha))


def _generate_insertion_events(
    rng,
    insertion_updates: int,
    weighted_distribution: dict[int, int],
    update_mode: str,
) -> tuple[list[tuple[int, int]], int]:
    population = list(weighted_distribution)
    weights = list(weighted_distribution.values())
    events: list[tuple[int, int]] = []
    insertion_mass = 0
    for _ in range(insertion_updates):
        item = rng.choices(population, weights=weights, k=1)[0]
        weight = _sample_update_weight(rng, update_mode=update_mode)
        events.append((item, weight))
        insertion_mass += weight
    return events, insertion_mass


def _allocate_weighted_deletions(
    rng,
    inserted_mass_by_item: Counter[int],
    deletion_updates: int,
    deletion_mass: int,
) -> dict[int, list[int]]:
    max_capacity = max(inserted_mass_by_item.values())
    for _ in range(64):
        deletion_weights: list[int] = []
        remaining_mass = deletion_mass
        remaining_events = deletion_updates
        while remaining_events > 0:
            future_events = remaining_events - 1
            min_weight = max(1, remaining_mass - future_events * max_capacity)
            max_weight = min(max_capacity, remaining_mass - future_events)
            weight = _sample_update_weight(
                rng,
                update_mode="weighted",
                min_weight=min_weight,
                max_weight=max_weight,
            )
            deletion_weights.append(weight)
            remaining_mass -= weight
            remaining_events -= 1

        available = Counter(inserted_mass_by_item)
        pending: dict[int, list[int]] = {}
        success = True
        for weight in sorted(deletion_weights, reverse=True):
            item = None
            for _ in range(8):
                candidate = weighted_choice(rng, available)
                if available[candidate] >= weight:
                    item = candidate
                    break
            if item is None:
                eligible = {candidate: mass for candidate, mass in available.items() if mass >= weight}
                if not eligible:
                    success = False
                    break
                item = weighted_choice(rng, eligible)
            pending.setdefault(item, []).append(weight)
            available[item] -= weight
            if available[item] == 0:
                del available[item]

        if success:
            for weights in pending.values():
                weights.sort(reverse=True)
            return pending

    raise RuntimeError("failed to allocate weighted deletions within item capacities")


def _merge_weighted_stream(
    rng,
    insertion_events: list[tuple[int, int]],
    pending_deletions: dict[int, list[int]],
) -> tuple[list[tuple[int, int]], Counter[int]]:
    stream: list[tuple[int, int]] = []
    active = Counter()
    pending_mass = {item: sum(weights) for item, weights in pending_deletions.items()}
    eligible: dict[int, int] = {}

    def refresh_eligibility(item: int) -> None:
        weights = pending_deletions.get(item)
        if not weights:
            eligible.pop(item, None)
            pending_mass.pop(item, None)
            return
        if active[item] >= weights[-1]:
            eligible[item] = pending_mass[item]
        else:
            eligible.pop(item, None)

    insertion_index = 0
    deletion_events_remaining = sum(len(weights) for weights in pending_deletions.values())
    while insertion_index < len(insertion_events) or deletion_events_remaining > 0:
        remaining_insertions = len(insertion_events) - insertion_index
        if deletion_events_remaining == 0:
            choose_deletion = False
        elif remaining_insertions == 0:
            choose_deletion = True
        elif not eligible:
            choose_deletion = False
        else:
            remaining_events = remaining_insertions + deletion_events_remaining
            choose_deletion = rng.random() < (deletion_events_remaining / remaining_events)

        if choose_deletion:
            item = weighted_choice(rng, eligible)
            weight = pending_deletions[item].pop()
            stream.append((item, -weight))
            active[item] -= weight
            if active[item] == 0:
                del active[item]
            pending_mass[item] -= weight
            deletion_events_remaining -= 1
            if not pending_deletions[item]:
                del pending_deletions[item]
            refresh_eligibility(item)
        else:
            item, weight = insertion_events[insertion_index]
            insertion_index += 1
            stream.append((item, weight))
            active[item] += weight
            if item in pending_deletions:
                refresh_eligibility(item)

    if pending_deletions:
        raise RuntimeError("weighted deletion queues were not fully realized")
    return stream, Counter(active)


def generate_strict_turnstile_stream(
    rng,
    total_operations: int,
    alpha: float,
    weighted_distribution: dict[int, int],
    update_mode: str = "unit",
) -> StreamRealization:
    if total_operations < 10:
        raise ValueError("total_operations must be at least 10")
    if alpha < 1.0:
        raise ValueError("alpha must be at least 1")

    deletion_updates = _deletion_event_count(total_operations, alpha)
    insertion_updates = total_operations - deletion_updates
    if insertion_updates <= deletion_updates:
        raise ValueError("parameter combination produced a non-positive final mass")
    if update_mode not in {"unit", "weighted"}:
        raise ValueError(f"unknown update_mode: {update_mode}")

    beta_alpha = (alpha - 1.0) / (alpha + 1.0)
    insertion_events, insertion_mass = _generate_insertion_events(
        rng=rng,
        insertion_updates=insertion_updates,
        weighted_distribution=weighted_distribution,
        update_mode=update_mode,
    )
    if update_mode == "weighted":
        while int(beta_alpha * insertion_mass) < deletion_updates:
            insertion_events, insertion_mass = _generate_insertion_events(
                rng=rng,
                insertion_updates=insertion_updates,
                weighted_distribution=weighted_distribution,
                update_mode=update_mode,
            )
    deletion_mass = deletion_updates if update_mode == "unit" else int(beta_alpha * insertion_mass)
    if update_mode == "unit":
        insertion_event_index = 0
        active = Counter()
        stream: list[tuple[int, int]] = []
        deletion_mass_remaining = deletion_mass
        deletion_updates_remaining = deletion_updates

        while insertion_event_index < insertion_updates or deletion_updates_remaining > 0:
            remaining_insertions = insertion_updates - insertion_event_index
            if remaining_insertions == 0:
                choose_deletion = True
            elif deletion_updates_remaining == 0:
                choose_deletion = False
            elif not active:
                choose_deletion = False
            else:
                remaining_ops = remaining_insertions + deletion_updates_remaining
                choose_deletion = rng.random() < (deletion_updates_remaining / remaining_ops)

            if choose_deletion:
                candidate = weighted_choice(rng, active)
                stream.append((candidate, -1))
                active[candidate] -= 1
                if active[candidate] == 0:
                    del active[candidate]
                deletion_updates_remaining -= 1
                deletion_mass_remaining -= 1
            else:
                item, weight = insertion_events[insertion_event_index]
                insertion_event_index += 1
                stream.append((item, weight))
                active[item] += weight

        if deletion_updates_remaining != 0 or deletion_mass_remaining != 0:
            raise RuntimeError("failed to realize the requested unit deletion schedule")
        final_frequencies = Counter(active)
    else:
        inserted_mass_by_item = Counter()
        for item, weight in insertion_events:
            inserted_mass_by_item[item] += weight
        pending_deletions = _allocate_weighted_deletions(
            rng=rng,
            inserted_mass_by_item=inserted_mass_by_item,
            deletion_updates=deletion_updates,
            deletion_mass=deletion_mass,
        )
        stream, final_frequencies = _merge_weighted_stream(
            rng=rng,
            insertion_events=insertion_events,
            pending_deletions=pending_deletions,
        )

    final_mass = sum(final_frequencies.values())
    if insertion_mass - deletion_mass != final_mass:
        raise RuntimeError("final frequency mass does not match tracked insertion/deletion mass")
    if insertion_mass + deletion_mass > alpha * final_mass + 1e-9:
        raise RuntimeError("generated stream violates the alpha-bounded deletion property")
    return StreamRealization(
        stream=stream,
        final_frequencies=final_frequencies,
        insertion_updates=insertion_updates,
        deletion_updates=deletion_updates,
        insertion_mass=insertion_mass,
        deletion_mass=deletion_mass,
        final_mass=final_mass,
        update_mode=update_mode,
        weight_model="unit" if update_mode == "unit" else "truncated_power_of_two_1_2_4_8",
    )


def tokenize_corpus(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def _packet_key_from_line(line: str) -> str | None:
    match = PACKET_LINE_RE.match(line)
    if not match:
        return None
    protocol, source, destination = match.groups()
    return f"{protocol}|{source}>{destination.rstrip(':')}"


def prepare_real_world_dataset(
    pcap_path: Path,
    cache_path: Path,
    vocabulary_size: int = 1024,
    rebuild: bool = False,
) -> Path:
    if cache_path.exists() and not rebuild and cache_path.stat().st_mtime >= pcap_path.stat().st_mtime:
        return cache_path

    if not pcap_path.exists():
        raise FileNotFoundError(f"pcap dataset not found: {pcap_path}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["tcpdump", "-nn", "-r", str(pcap_path)]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    counter: Counter[str] = Counter()
    parsed_packets = 0
    assert process.stdout is not None
    for line in process.stdout:
        key = _packet_key_from_line(line)
        if key is None:
            continue
        counter[key] += 1
        parsed_packets += 1

    stderr_text = process.stderr.read() if process.stderr is not None else ""
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"tcpdump failed while parsing {pcap_path}: {stderr_text.strip()}")

    top_flows = counter.most_common(vocabulary_size)
    if not top_flows:
        raise ValueError(f"no packet keys could be extracted from {pcap_path}")

    payload = {
        "pcap_path": str(pcap_path),
        "flow_key_type": "directed_endpoint_pair",
        "parsed_packets": parsed_packets,
        "unique_flow_keys": len(counter),
        "selected_vocabulary_size": len(top_flows),
        "vocabulary": [flow for flow, _ in top_flows],
        "weights": {str(index): count for index, (_, count) in enumerate(top_flows)},
    }
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return cache_path


def build_real_world_distribution(cache_path: Path) -> dict[int, int]:
    metadata = json.loads(cache_path.read_text(encoding="utf-8"))
    weights = metadata.get("weights", {})
    distribution = {int(index): int(count) for index, count in weights.items()}
    if not distribution:
        raise ValueError(f"cached real-world dataset is empty: {cache_path}")
    return distribution
