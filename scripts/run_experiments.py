#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from frequency_estimation.datasets import prepare_real_world_dataset
from frequency_estimation.experiments import run_experiment_grid


def main() -> None:
    data_dir = REPO_ROOT / "data"
    prepare_real_world_dataset(
        pcap_path=data_dir / "network" / "200002091359.dump",
        cache_path=data_dir / "network" / "flow_distribution.json",
        vocabulary_size=1024,
    )

    rows = run_experiment_grid(
        output_csv=REPO_ROOT / "results" / "csv" / "experiment_results.csv",
        data_dir=data_dir,
        stream_lengths=[10000, 25000, 50000],
        alpha_values=[1.5, 2.0, 4.0, 8.0],
        budget_bytes_list=[1024, 2048, 4096, 8192, 16384],
        seeds=[7, 19, 41],
        datasets=["balanced", "skewed", "real_world"],
        update_modes=["unit", "weighted"],
    )
    print(f"wrote {len(rows)} rows")


if __name__ == "__main__":
    main()
