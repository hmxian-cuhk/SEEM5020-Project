#!/usr/bin/env python3
from __future__ import annotations

import csv
import subprocess
from collections import defaultdict
from pathlib import Path


def load_rows(input_csv: Path) -> list[dict[str, str]]:
    with input_csv.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_tradeoff_data(rows: list[dict[str, str]], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "balanced_tradeoff_unit": output_dir / "balanced_tradeoff_unit_alpha4_stream50000.dat",
        "skewed_tradeoff_unit": output_dir / "skewed_tradeoff_unit_alpha4_stream50000.dat",
        "real_tradeoff_unit": output_dir / "real_world_tradeoff_unit_alpha4_stream50000.dat",
        "balanced_tradeoff_weighted": output_dir / "balanced_tradeoff_weighted_alpha4_stream50000.dat",
        "skewed_tradeoff_weighted": output_dir / "skewed_tradeoff_weighted_alpha4_stream50000.dat",
        "real_tradeoff_weighted": output_dir / "real_world_tradeoff_weighted_alpha4_stream50000.dat",
        "alpha_fixed_budget_unit": output_dir / "real_world_alpha_fixed_budget4096_unit_stream50000.dat",
        "alpha_fixed_budget_weighted": output_dir / "real_world_alpha_fixed_budget4096_weighted_stream50000.dat",
        "length_fixed_budget_unit": output_dir / "real_world_length_fixed_budget4096_unit_alpha4.dat",
        "length_fixed_budget_weighted": output_dir / "real_world_length_fixed_budget4096_weighted_alpha4.dat",
    }

    grouped = defaultdict(lambda: {"count": 0, "error": 0.0, "space": 0.0, "final_mass": 0.0})
    for row in rows:
        key = (
            row["update_mode"],
            row["dataset"],
            row["algorithm"],
            row["stream_length"],
            row["alpha"],
            row["budget_bytes"],
        )
        grouped[key]["count"] += 1
        grouped[key]["error"] += float(row["avg_relative_error_topk"])
        grouped[key]["space"] += float(row["space_bytes"])
        grouped[key]["final_mass"] += float(row["final_mass"])

    def write_file(path: Path, selector) -> None:
        with path.open("w", encoding="utf-8") as handle:
            handle.write("update_mode dataset algorithm stream_length alpha budget_bytes avg_error avg_space avg_final_mass\n")
            for key in sorted(grouped, key=lambda item: (item[0], item[1], item[2], int(item[3]), float(item[4]), int(item[5]))):
                update_mode, dataset, algorithm, stream_length, alpha, budget_bytes = key
                if not selector(update_mode, dataset, algorithm, stream_length, alpha, budget_bytes):
                    continue
                bucket = grouped[key]
                handle.write(
                    f"{update_mode} {dataset} \"{algorithm}\" {stream_length} {alpha} {budget_bytes} "
                    f"{bucket['error'] / bucket['count']:.6f} {bucket['space'] / bucket['count']:.2f} "
                    f"{bucket['final_mass'] / bucket['count']:.2f}\n"
                )

    for update_mode in ("unit", "weighted"):
        suffix = "unit" if update_mode == "unit" else "weighted"
        write_file(
            paths[f"balanced_tradeoff_{suffix}"],
            lambda row_mode, dataset, _algorithm, stream_length, alpha, _budget, mode=update_mode: row_mode == mode
            and dataset == "balanced"
            and stream_length == "50000"
            and alpha == "4.0",
        )
        write_file(
            paths[f"skewed_tradeoff_{suffix}"],
            lambda row_mode, dataset, _algorithm, stream_length, alpha, _budget, mode=update_mode: row_mode == mode
            and dataset == "skewed"
            and stream_length == "50000"
            and alpha == "4.0",
        )
        write_file(
            paths[f"real_tradeoff_{suffix}"],
            lambda row_mode, dataset, _algorithm, stream_length, alpha, _budget, mode=update_mode: row_mode == mode
            and dataset == "real_world"
            and stream_length == "50000"
            and alpha == "4.0",
        )
        write_file(
            paths[f"alpha_fixed_budget_{suffix}"],
            lambda row_mode, dataset, _algorithm, stream_length, _alpha, budget, mode=update_mode: row_mode == mode
            and dataset == "real_world"
            and stream_length == "50000"
            and budget == "4096",
        )
        write_file(
            paths[f"length_fixed_budget_{suffix}"],
            lambda row_mode, dataset, _algorithm, _stream_length, alpha, budget, mode=update_mode: row_mode == mode
            and dataset == "real_world"
            and alpha == "4.0"
            and budget == "4096",
        )

    return paths


def gnuplot_script(data_paths: dict[str, Path], plot_dir: Path) -> str:
    def tradeoff_plot(path: Path, title: str, output_name: str) -> str:
        return f"""
set output '{(plot_dir / output_name).as_posix()}'
set title '{title}'
set xlabel 'Logical space (bytes)'
set ylabel 'Average relative error on Top-25'
plot \\
    '{path.as_posix()}' using (strcol(3) eq 'Misra-Gries' ? $8 : 1/0):7 with linespoints lw 2 title 'Misra-Gries', \\
    '{path.as_posix()}' using (strcol(3) eq 'Space-Saving' ? $8 : 1/0):7 with linespoints lw 2 title 'Space-Saving', \\
    '{path.as_posix()}' using (strcol(3) eq 'Count-Min Sketch' ? $8 : 1/0):7 with linespoints lw 2 title 'Count-Min Sketch', \\
    '{path.as_posix()}' using (strcol(3) eq 'Count-Sketch' ? $8 : 1/0):7 with linespoints lw 2 title 'Count-Sketch'
"""

    def alpha_plot(path: Path, title: str, output_name: str) -> str:
        return f"""
set output '{(plot_dir / output_name).as_posix()}'
set title '{title}'
set xlabel 'Alpha'
set ylabel 'Average relative error on Top-25'
plot \\
    '{path.as_posix()}' using (strcol(3) eq 'Misra-Gries' ? $5 : 1/0):7 with linespoints lw 2 title 'Misra-Gries', \\
    '{path.as_posix()}' using (strcol(3) eq 'Space-Saving' ? $5 : 1/0):7 with linespoints lw 2 title 'Space-Saving', \\
    '{path.as_posix()}' using (strcol(3) eq 'Count-Min Sketch' ? $5 : 1/0):7 with linespoints lw 2 title 'Count-Min Sketch', \\
    '{path.as_posix()}' using (strcol(3) eq 'Count-Sketch' ? $5 : 1/0):7 with linespoints lw 2 title 'Count-Sketch'
"""

    def length_plot(path: Path, title: str, output_name: str) -> str:
        return f"""
set output '{(plot_dir / output_name).as_posix()}'
set title '{title}'
set xlabel 'Stream length'
set ylabel 'Average relative error on Top-25'
plot \\
    '{path.as_posix()}' using (strcol(3) eq 'Misra-Gries' ? $4 : 1/0):7 with linespoints lw 2 title 'Misra-Gries', \\
    '{path.as_posix()}' using (strcol(3) eq 'Space-Saving' ? $4 : 1/0):7 with linespoints lw 2 title 'Space-Saving', \\
    '{path.as_posix()}' using (strcol(3) eq 'Count-Min Sketch' ? $4 : 1/0):7 with linespoints lw 2 title 'Count-Min Sketch', \\
    '{path.as_posix()}' using (strcol(3) eq 'Count-Sketch' ? $4 : 1/0):7 with linespoints lw 2 title 'Count-Sketch'
"""

    return f"""
set datafile separator whitespace
set terminal pngcairo size 1280,800 enhanced font 'Helvetica,12'
set key outside
set grid

{tradeoff_plot(data_paths["balanced_tradeoff_unit"], "Error-Space Tradeoff on Balanced Data (unit updates, alpha=4, events=50000)", "error_space_tradeoff_balanced.png")}

{tradeoff_plot(data_paths["skewed_tradeoff_unit"], "Error-Space Tradeoff on Skewed Data (unit updates, alpha=4, events=50000)", "error_space_tradeoff_skewed.png")}

{tradeoff_plot(data_paths["real_tradeoff_unit"], "Error-Space Tradeoff on Network Trace Data (unit updates, alpha=4, events=50000)", "error_space_tradeoff_real_world.png")}

{tradeoff_plot(data_paths["balanced_tradeoff_weighted"], "Error-Space Tradeoff on Balanced Data (weighted updates, alpha=4, events=50000)", "error_space_tradeoff_balanced_weighted.png")}

{tradeoff_plot(data_paths["skewed_tradeoff_weighted"], "Error-Space Tradeoff on Skewed Data (weighted updates, alpha=4, events=50000)", "error_space_tradeoff_skewed_weighted.png")}

{tradeoff_plot(data_paths["real_tradeoff_weighted"], "Error-Space Tradeoff on Network Trace Data (weighted updates, alpha=4, events=50000)", "error_space_tradeoff_real_world_weighted.png")}

{alpha_plot(data_paths["alpha_fixed_budget_unit"], "Real-World Error vs Alpha (unit updates, budget=4096, events=50000)", "real_world_error_vs_alpha_fixed_budget.png")}

{alpha_plot(data_paths["alpha_fixed_budget_weighted"], "Real-World Error vs Alpha (weighted updates, budget=4096, events=50000)", "real_world_error_vs_alpha_fixed_budget_weighted.png")}

{length_plot(data_paths["length_fixed_budget_unit"], "Real-World Error vs Stream Length (unit updates, budget=4096, alpha=4)", "real_world_error_vs_stream_length_fixed_budget.png")}

{length_plot(data_paths["length_fixed_budget_weighted"], "Real-World Error vs Stream Length (weighted updates, budget=4096, alpha=4)", "real_world_error_vs_stream_length_fixed_budget_weighted.png")}
"""


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    csv_dir = repo_root / "results" / "csv"
    plot_dir = repo_root / "results" / "plots"
    rows = load_rows(csv_dir / "experiment_results.csv")
    data_paths = write_tradeoff_data(rows, csv_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gnuplot"], input=gnuplot_script(data_paths, plot_dir), text=True, check=True)
    print(plot_dir)


if __name__ == "__main__":
    main()
