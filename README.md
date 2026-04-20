# SEEM5020 Individual Project

This repository contains a complete implementation of the frequency-estimation project from `Project-description.pdf`, updated to use the provided network trace in `data/network/` as the real-world dataset.

## What is included

- Extended implementations of:
  - Misra-Gries
  - Space-Saving
  - Count-Min Sketch
  - Count-Sketch
- A strict-turnstile stream generator that enforces the `L1` `alpha`-bounded deletion property.
- Both unit-update and weighted-update experiment tracks.
- Three datasets:
  - balanced synthetic
  - skewed synthetic
  - real-world network trace derived from `data/network/200002091359.dump`
- A budget-sweep experiment pipeline for studying the error-space tradeoff.
- Generated CSV results, plots, and a report PDF.

## Project layout

- `src/frequency_estimation/algorithms.py`: extended algorithms with budget-aware sizing.
- `src/frequency_estimation/datasets.py`: synthetic generators, pcap preprocessing, and strict-turnstile stream construction.
- `src/frequency_estimation/experiments.py`: experiment driver and evaluation metrics.
- `scripts/prepare_real_dataset.py`: parses the pcap trace and writes `data/network/flow_distribution.json`.
- `scripts/run_experiments.py`: runs the full dataset/alpha/stream-length/budget grid.
- `scripts/generate_plots.py`: generates tradeoff and sensitivity plots in `results/plots/`.
- `scripts/summarize_results.py`: writes `results/csv/summary_by_dataset_alpha_budget.csv`.
- `report/report.tex`: LaTeX source for the final report.

## Reproduce the experiments

This project uses only the Python standard library plus system tools already available in this environment: `tcpdump`, `gnuplot`, and `pdflatex`.

1. Parse the network trace into a cached flow distribution:

```bash
python3 scripts/prepare_real_dataset.py
```

2. Run the full experiments:

```bash
python3 scripts/run_experiments.py
```

3. Generate plots and aggregated summaries:

```bash
python3 scripts/generate_plots.py
python3 scripts/summarize_results.py
```

4. Build the report PDF:

```bash
bash scripts/build_report.sh
```

## Experimental setup

- Update-event counts: `10000`, `25000`, `50000`
- Update modes: `unit`, `weighted`
- `alpha` values: `1.5`, `2`, `4`, `8`
- Budget sweep: `1024`, `2048`, `4096`, `8192`, `16384` logical bytes
- Replications: 3 random seeds
- Deletion policy:
  - unit mode: random deletions drawn from the currently active multiset
  - weighted mode: random weighted deletion schedules sampled from inserted mass and interleaved only when the corresponding item is active
- Weighted-update law: insertion magnitudes drawn from `{1, 2, 4, 8}` with probabilities proportional to `8:4:2:1`
- Accuracy metric: average relative error on the exact top-25 final-frequency items by final mass
- Space metric: logical bytes derived from maintained counters and tables, not Python heap overhead

## Real-world dataset

The real-world dataset is built from the pcap file `data/network/200002091359.dump`.
Download Link: https://mawi.wide.ad.jp/mawi/samplepoint-A/2000/200002091359.html
The preprocessing script uses `tcpdump` to extract directed endpoint-pair flow keys of the form:

```text
IP|source_endpoint>destination_endpoint
```

The cached metadata file `data/network/flow_distribution.json` stores:

- total parsable packets in the trace
- number of unique flow keys
- the top 1024 flow keys by packet count
- integer weights used by the experiment runner

## Design summary

- `Misra-Gries` extension:
  - one summary tracks insertions
  - one summary tracks deletion magnitudes
  - the final estimate is `max(0, positive - negative)`
- `Space-Saving` extension:
  - same dual-summary design as above
  - uses replacement-on-minimum within each summary
- `Count-Min Sketch` extension:
  - a single linear sketch processes signed updates directly
  - the standard `min` query is used because the project assumes the strict-turnstile model
- `Count-Sketch` extension:
  - a single signed sketch handles positive and negative updates natively
  - budget controls width directly while depth stays fixed

## Stream generator

Let `I` denote total insertion mass and `D` denote total deletion mass. The generator enforces

```text
I + D <= alpha (I - D)
```

so the final strict-turnstile mass is `||f||_1 = I - D`.

For a target update-event count `T` and deletion parameter `alpha`, the generator:

1. computes the insertion/deletion event split implied by `alpha`,
2. samples insertion items from the dataset distribution,
3. assigns update magnitudes:
   - `1` in unit mode
   - weighted magnitudes in `{1, 2, 4, 8}` in weighted mode
4. schedules deletions while preserving strict turnstile at every prefix,
5. records realized insertion mass, deletion mass, and final mass for every run.

This keeps the stream reproducible, random, and consistent with the assignment model in both unit and weighted settings.

## Outputs generated in this repository

- Raw experiment results:
  - `results/csv/experiment_results.csv`
- Aggregated summary:
  - `results/csv/summary_by_dataset_alpha_budget.csv`
- Tradeoff and sensitivity plots:
  - `results/plots/error_space_tradeoff_balanced.png`
  - `results/plots/error_space_tradeoff_skewed.png`
  - `results/plots/error_space_tradeoff_real_world.png`
  - `results/plots/error_space_tradeoff_balanced_weighted.png`
  - `results/plots/error_space_tradeoff_skewed_weighted.png`
  - `results/plots/error_space_tradeoff_real_world_weighted.png`
  - `results/plots/real_world_error_vs_alpha_fixed_budget.png`
  - `results/plots/real_world_error_vs_alpha_fixed_budget_weighted.png`
  - `results/plots/real_world_error_vs_stream_length_fixed_budget.png`
  - `results/plots/real_world_error_vs_stream_length_fixed_budget_weighted.png`
- Report:
  - `report/report.pdf`
