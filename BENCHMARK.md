# Benchmark pipeline

This benchmark pipeline compares policy versions (`v0.0.1`, `v0.0.2`, `v0.0.3`, `v0.0.4`) on identical map conditions and controlled seeds.

## What you get per run

For each version / variant / seed, the pipeline records:

- total mission steps,
- runtime (`duration_sec`),
- completion status,
- first successful deposit step (`first_deposit_step`),
- average waiting time between deposits,
- clear step per waste color (`green`, `yellow`, `red`),
- initial and final waste counts by type,
- full waste timeline (`waste_timeline`) + reduced change points (`waste_change_points`),
- detailed deposit events (`deposit_events`) for curve/stat analysis.

A mission is complete when no `WasteAgent` remains.

## Feasibility checks

Each variant is validated before simulation. Invalid variants are skipped with explicit errors:

- missing zone coverage,
- impossible robot/waste chain constraints,
- invalid radius ordering (`rayon_zone_3 < rayon_zone_2`).

## Seed control

You can fully control randomness with explicit `seeds` in config. If absent, the script uses the single value from `base_params.seed`.

## Robot brute-force sweep

Use `robot_range_sweep` to generate many robot-composition variants automatically.

Example:

```json
"robot_range_sweep": {
  "green": [1, 4],
  "yellow": [1, 4],
  "red": [0, 4]
}
```

This creates variants like `robots_g1_y1_r0`, `robots_g4_y4_r4`, etc.

## Run

```bash
python benchmark_pipeline.py --config benchmark_config.example.json --output-dir benchmark_outputs
```

Run a single version (for example `v0.0.4`) and merge with existing results instead of overwriting:

```bash
python benchmark_pipeline.py --config benchmark_config.example.json --output-dir benchmark_outputs --version v0.0.4 --append-existing
```

Run an explicit list of versions:

```bash
python benchmark_pipeline.py --config benchmark_config.example.json --output-dir benchmark_outputs --versions v0.0.3,v0.0.4 --append-existing
```

Merge-only mode for split reports:

```bash
python benchmark_pipeline.py --output-dir benchmark_outputs --merge-only --merge-pattern "benchmark_report*.json"
```

`--append-existing` now merges all files matching `--merge-pattern` in the output directory (default: `benchmark_report*.json`) before inserting newly computed runs.

## Outputs

- `benchmark_report.json`
  - `results`: full rich per-run records (timelines, event details),
  - `results_compact`: flattened per-run metrics,
  - `summary`: aggregated stats per map variant and version,
  - `analysis`: automatic ranking by average steps / first deposit speed for each map.
- `benchmark_runs.csv`: flattened per-run metrics.
- `benchmark_summary.csv`: aggregate metrics.

## Typical analyses now enabled

- Compare versions on one map:
  - fastest first deposit,
  - best completion rate,
  - best average total steps,
  - average clear step for green/yellow/red waste.
- Compare one version across map variants:
  - sensitivity to robot composition,
  - sensitivity to heavier waste loads,
  - waste-curve dynamics from `waste_change_points`.
