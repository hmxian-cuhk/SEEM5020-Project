from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .algorithms import build_algorithm_suite
from .common import average, relative_error, top_items
from .datasets import (
    build_real_world_distribution,
    generate_strict_turnstile_stream,
    prepare_real_world_dataset,
    synthetic_distribution,
)


@dataclass
class ExperimentConfig:
    dataset: str
    stream_length: int
    alpha: float
    budget_bytes: int
    seed: int
    update_mode: str


def evaluate_estimator(estimator, stream, exact_frequencies: Counter[int], top_k: int = 25) -> dict[str, float]:
    for item, delta in stream:
        estimator.update(item, delta)

    targets = top_items(exact_frequencies, top_k)
    per_item_errors = []
    weighted_errors = []
    exact_total = sum(exact_frequencies.values())
    estimated_total = 0

    for item, truth in targets:
        estimate = estimator.estimate(item)
        error = relative_error(estimate, truth)
        per_item_errors.append(error)
        weighted_errors.append(error * truth)
        estimated_total += estimate

    return {
        "avg_relative_error_topk": average(per_item_errors),
        "max_relative_error_topk": max(per_item_errors) if per_item_errors else 0.0,
        "weighted_relative_error_topk": sum(weighted_errors) / max(1, sum(freq for _, freq in targets)),
        "topk_mass_ratio": estimated_total / max(1, sum(freq for _, freq in targets)),
        "space_bytes": estimator.space_bytes(),
        "final_l1": exact_total,
    }


def _distribution_for_dataset(dataset: str, data_dir: Path) -> dict[int, int]:
    if dataset == "balanced":
        return synthetic_distribution("balanced", universe_size=512)
    if dataset == "skewed":
        return synthetic_distribution("skewed", universe_size=512)
    if dataset == "real_world":
        cache_path = data_dir / "network" / "flow_distribution.json"
        pcap_path = data_dir / "network" / "200002091359.dump"
        prepare_real_world_dataset(pcap_path=pcap_path, cache_path=cache_path, vocabulary_size=1024)
        return build_real_world_distribution(cache_path)
    raise ValueError(f"unknown dataset: {dataset}")


def run_experiment_grid(
    output_csv: Path,
    data_dir: Path,
    stream_lengths: list[int],
    alpha_values: list[float],
    budget_bytes_list: list[int],
    seeds: list[int],
    datasets: list[str],
    update_modes: list[str],
) -> list[dict[str, float | int | str]]:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, float | int | str]] = []

    for dataset in datasets:
        distribution = _distribution_for_dataset(dataset, data_dir)
        for stream_length in stream_lengths:
            for alpha in alpha_values:
                for update_mode in update_modes:
                    for seed in seeds:
                        import random

                        rng = random.Random(seed)
                        realization = generate_strict_turnstile_stream(
                            rng=rng,
                            total_operations=stream_length,
                            alpha=alpha,
                            weighted_distribution=distribution,
                            update_mode=update_mode,
                        )
                        for budget_bytes in budget_bytes_list:
                            for estimator in build_algorithm_suite(alpha=alpha, budget_bytes=budget_bytes):
                                metrics = evaluate_estimator(estimator, realization.stream, realization.final_frequencies)
                                rows.append(
                                    {
                                        "dataset": dataset,
                                        "update_mode": update_mode,
                                        "weight_model": realization.weight_model,
                                        "stream_length": stream_length,
                                        "alpha": alpha,
                                        "budget_bytes": budget_bytes,
                                        "seed": seed,
                                        "algorithm": estimator.name,
                                        "config": estimator.config(),
                                        "insertion_updates": realization.insertion_updates,
                                        "deletion_updates": realization.deletion_updates,
                                        "insertion_mass": realization.insertion_mass,
                                        "deletion_mass": realization.deletion_mass,
                                        "final_mass": realization.final_mass,
                                        **metrics,
                                    }
                                )

    fieldnames = list(rows[0]) if rows else []
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows
