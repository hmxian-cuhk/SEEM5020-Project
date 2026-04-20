#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    input_csv = repo_root / "results" / "csv" / "experiment_results.csv"
    output_csv = repo_root / "results" / "csv" / "summary_by_dataset_alpha_budget.csv"

    grouped = defaultdict(lambda: {"count": 0, "error": 0.0, "space": 0.0, "final_mass": 0.0})
    with input_csv.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = (row["dataset"], row["update_mode"], row["algorithm"], row["alpha"], row["budget_bytes"])
            grouped[key]["count"] += 1
            grouped[key]["error"] += float(row["avg_relative_error_topk"])
            grouped[key]["space"] += float(row["space_bytes"])
            grouped[key]["final_mass"] += float(row["final_mass"])

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "dataset",
            "update_mode",
            "algorithm",
            "alpha",
            "budget_bytes",
            "avg_relative_error_topk",
            "avg_space_bytes",
            "avg_final_mass",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(grouped, key=lambda item: (item[0], item[1], item[2], float(item[3]), int(item[4]))):
            dataset, update_mode, algorithm, alpha, budget_bytes = key
            bucket = grouped[key]
            writer.writerow(
                {
                    "dataset": dataset,
                    "update_mode": update_mode,
                    "algorithm": algorithm,
                    "alpha": alpha,
                    "budget_bytes": budget_bytes,
                    "avg_relative_error_topk": bucket["error"] / bucket["count"],
                    "avg_space_bytes": bucket["space"] / bucket["count"],
                    "avg_final_mass": bucket["final_mass"] / bucket["count"],
                }
            )

    print(output_csv)


if __name__ == "__main__":
    main()
