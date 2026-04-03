import argparse
import contextlib
import copy
import csv
import io
import itertools
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from communication.message.MessageService import MessageService
from model import RobotMissionModel
from objects import WasteAgent

AVAILABLE_VERSIONS = ["v0.0.1", "v0.0.2", "v0.0.3"]
WASTE_COLORS = ["green", "yellow", "red"]
ROBOT_COLORS = ["green", "yellow", "red"]


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged


def _cells_per_zone(
    width: int,
    height: int,
    epicenters: list[tuple[int, int]],
    rayon_zone_3: float,
    rayon_zone_2: float,
) -> dict[int, int]:
    counts = {1: 0, 2: 0, 3: 0}
    for x in range(width):
        for y in range(height):
            min_dist = min(math.dist((x, y), ep) for ep in epicenters)
            if min_dist <= rayon_zone_3:
                counts[3] += 1
            elif min_dist <= rayon_zone_2:
                counts[2] += 1
            else:
                counts[1] += 1
    return counts


def check_map_feasibility(params: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    width = params["width"]
    height = params["height"]
    epicenters = [tuple(ep) for ep in params["epicenters"]]
    cells = _cells_per_zone(
        width,
        height,
        epicenters,
        params["rayon_zone_3"],
        params["rayon_zone_2"],
    )

    if any(cells[z] == 0 for z in (1, 2, 3)):
        errors.append(f"At least one radioactivity zone is empty: {cells}.")

    wastes = params.get("num_wastes", {})
    robots = params.get("num_robots", {})

    if wastes.get("green", 0) > 0 and robots.get("green", 0) == 0:
        errors.append("Green wastes require at least one green robot.")
    if wastes.get("yellow", 0) > 0 and (
        robots.get("yellow", 0) == 0 or robots.get("green", 0) == 0
    ):
        errors.append("Yellow wastes require at least one yellow robot and one green robot.")
    if wastes.get("red", 0) > 0 and (
        robots.get("red", 0) == 0
        or robots.get("yellow", 0) == 0
        or robots.get("green", 0) == 0
    ):
        errors.append("Red wastes require at least one red, yellow, and green robot.")

    if params["rayon_zone_3"] >= params["rayon_zone_2"]:
        errors.append("rayon_zone_3 must be lower than rayon_zone_2.")

    return len(errors) == 0, errors


def remaining_wastes(model: RobotMissionModel) -> dict[str, int]:
    counts = {"green": 0, "yellow": 0, "red": 0}
    for agent in model.agents:
        if isinstance(agent, WasteAgent):
            counts[agent.waste_type] += 1
    return counts


def _build_variants(config: dict[str, Any]) -> list[dict[str, Any]]:
    explicit_variants = config.get("variants", [{"name": "baseline", "updates": {}}])
    robot_sweep = config.get("robot_range_sweep")

    if not robot_sweep:
        return explicit_variants

    min_max = {
        color: robot_sweep.get(color, [0, 0])
        for color in ROBOT_COLORS
    }

    combined_variants = []

    for explicit_variant in explicit_variants:
        base_name = explicit_variant["name"]
        base_updates = explicit_variant.get("updates", {})

        for green_count, yellow_count, red_count in itertools.product(
            range(min_max["green"][0], min_max["green"][1] + 1),
            range(min_max["yellow"][0], min_max["yellow"][1] + 1),
            range(min_max["red"][0], min_max["red"][1] + 1),
        ):
            robot_updates = {
                "num_robots": {
                    "green": green_count,
                    "yellow": yellow_count,
                    "red": red_count,
                }
            }
            merged_updates = {
                **base_updates,
                **robot_updates,
            }
            combined_variants.append(
                {
                    "name": f"{base_name}_robots_g{green_count}_y{yellow_count}_r{red_count}",
                    "updates": merged_updates,
                }
            )

    return combined_variants


def _build_seed_list(config: dict[str, Any], base_params: dict[str, Any]) -> list[int]:
    if "seeds" in config:
        return list(config["seeds"])
    return [int(base_params.get("seed", 0))]


def _color_clear_steps(timeline: list[dict[str, int]]) -> dict[str, int | None]:
    clear_steps = {color: None for color in WASTE_COLORS}
    for point in timeline:
        for color in WASTE_COLORS:
            if clear_steps[color] is None and point[color] == 0:
                clear_steps[color] = point["step"]
    return clear_steps


def _waste_change_points(timeline: list[dict[str, int]]) -> list[dict[str, int]]:
    if not timeline:
        return []
    changes = [timeline[0]]
    previous = timeline[0]
    for point in timeline[1:]:
        if any(point[color] != previous[color] for color in WASTE_COLORS):
            changes.append(point)
            previous = point
    return changes


def run_single(params: dict[str, Any], version: str, max_steps: int) -> dict[str, Any]:
    MessageService._MessageService__instance = None
    model = RobotMissionModel(**params, version=version)
    started = time.perf_counter()

    steps = 0
    completed = False

    initial_counts = remaining_wastes(model)
    timeline = [
        {
            "step": 0,
            "green": initial_counts["green"],
            "yellow": initial_counts["yellow"],
            "red": initial_counts["red"],
            "total": sum(initial_counts.values()),
        }
    ]

    with contextlib.redirect_stdout(io.StringIO()):
        while steps < max_steps:
            current_counts = remaining_wastes(model)
            if sum(current_counts.values()) == 0:
                completed = True
                break

            model.step()
            steps += 1

            current_counts = remaining_wastes(model)
            timeline.append(
                {
                    "step": steps,
                    "green": current_counts["green"],
                    "yellow": current_counts["yellow"],
                    "red": current_counts["red"],
                    "total": sum(current_counts.values()),
                }
            )

    duration = time.perf_counter() - started
    final_wastes = remaining_wastes(model)

    deposit_events = list(model.deposit_events)
    first_deposit_step = deposit_events[0]["step"] if deposit_events else None
    deposit_wait_steps = [
        deposit_events[i]["step"] - deposit_events[i - 1]["step"]
        for i in range(1, len(deposit_events))
    ]

    color_clear_steps = _color_clear_steps(timeline)
    change_points = _waste_change_points(timeline)

    return {
        "version": version,
        "steps": steps,
        "completed": completed,
        "duration_sec": duration,
        "remaining_wastes": final_wastes,
        "remaining_total": sum(final_wastes.values()),
        "initial_wastes": initial_counts,
        "first_deposit_step": first_deposit_step,
        "deposit_event_count": len(deposit_events),
        "avg_wait_between_deposits": statistics.mean(deposit_wait_steps)
        if deposit_wait_steps
        else None,
        "color_clear_steps": color_clear_steps,
        "deposit_events": deposit_events,
        "waste_timeline": timeline,
        "waste_change_points": change_points,
    }


def _compact_run_row(row: dict[str, Any]) -> dict[str, Any]:
    clear_steps = row["color_clear_steps"]
    return {
        "variant": row["variant"],
        "version": row["version"],
        "run_index": row["run_index"],
        "seed": row["seed"],
        "completed": row["completed"],
        "steps": row["steps"],
        "duration_sec": row["duration_sec"],
        "remaining_total": row["remaining_total"],
        "initial_green": row["initial_wastes"]["green"],
        "initial_yellow": row["initial_wastes"]["yellow"],
        "initial_red": row["initial_wastes"]["red"],
        "first_deposit_step": row["first_deposit_step"],
        "deposit_event_count": row["deposit_event_count"],
        "avg_wait_between_deposits": row["avg_wait_between_deposits"],
        "green_clear_step": clear_steps["green"],
        "yellow_clear_step": clear_steps["yellow"],
        "red_clear_step": clear_steps["red"],
    }


def _analysis_for_variant(variant_summary: list[dict[str, Any]]) -> dict[str, Any]:
    comparable = [row for row in variant_summary if row.get("avg_steps") is not None]
    ranked_by_steps = sorted(comparable, key=lambda row: row["avg_steps"])
    ranked_by_first_deposit = sorted(
        [row for row in variant_summary if row.get("avg_first_deposit_step") is not None],
        key=lambda row: row["avg_first_deposit_step"],
    )
    return {
        "best_step_efficiency_version": ranked_by_steps[0]["version"] if ranked_by_steps else None,
        "best_first_deposit_version": ranked_by_first_deposit[0]["version"]
        if ranked_by_first_deposit
        else None,
        "ranked_by_avg_steps": [
            {"version": row["version"], "avg_steps": row["avg_steps"]}
            for row in ranked_by_steps
        ],
    }


def run_benchmark(config: dict[str, Any]) -> dict[str, Any]:
    base_params = config["base_params"]
    versions = config.get("versions", AVAILABLE_VERSIONS)
    variants = _build_variants(config)
    seeds = _build_seed_list(config, base_params)
    max_steps = int(config.get("max_steps", 500))

    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    variant_analysis: dict[str, Any] = {}

    for variant in variants:
        variant_name = variant["name"]
        merged_params = _deep_update(base_params, variant.get("updates", {}))

        feasible, errors = check_map_feasibility(merged_params)
        if not feasible:
            summary_rows.append(
                {
                    "variant": variant_name,
                    "version": "ALL",
                    "runs": 0,
                    "completed_runs": 0,
                    "success_rate": 0,
                    "avg_steps": None,
                    "avg_duration_sec": None,
                    "avg_first_deposit_step": None,
                    "avg_wait_between_deposits": None,
                    "avg_green_clear_step": None,
                    "avg_yellow_clear_step": None,
                    "avg_red_clear_step": None,
                    "marginal_gain_vs_baseline_steps_pct": None,
                    "feasible": False,
                    "errors": errors,
                }
            )
            continue

        variant_version_rows: dict[str, list[dict[str, Any]]] = {v: [] for v in versions}

        for run_index, run_seed in enumerate(seeds):
            run_params = copy.deepcopy(merged_params)
            run_params["seed"] = run_seed

            for version in versions:
                row = run_single(run_params, version, max_steps)
                row["variant"] = variant_name
                row["run_index"] = run_index
                row["seed"] = run_seed
                all_rows.append(row)
                variant_version_rows[version].append(row)

        baseline_version = versions[0]
        baseline_steps = [
            r["steps"]
            for r in variant_version_rows[baseline_version]
            if r["completed"]
        ]
        baseline_avg = statistics.mean(baseline_steps) if baseline_steps else None

        variant_summary_rows = []
        for version in versions:
            rows = variant_version_rows[version]
            completed_rows = [r for r in rows if r["completed"]]

            steps_values = [r["steps"] for r in completed_rows]
            duration_values = [r["duration_sec"] for r in rows]
            first_deposit_values = [
                r["first_deposit_step"]
                for r in rows
                if r["first_deposit_step"] is not None
            ]
            wait_values = [
                r["avg_wait_between_deposits"]
                for r in rows
                if r["avg_wait_between_deposits"] is not None
            ]
            green_clear_values = [
                r["color_clear_steps"]["green"]
                for r in rows
                if r["color_clear_steps"]["green"] is not None
            ]
            yellow_clear_values = [
                r["color_clear_steps"]["yellow"]
                for r in rows
                if r["color_clear_steps"]["yellow"] is not None
            ]
            red_clear_values = [
                r["color_clear_steps"]["red"]
                for r in rows
                if r["color_clear_steps"]["red"] is not None
            ]

            avg_steps = statistics.mean(steps_values) if steps_values else None
            avg_duration = statistics.mean(duration_values) if duration_values else None
            gain = None
            if baseline_avg and avg_steps is not None and baseline_avg > 0:
                gain = ((baseline_avg - avg_steps) / baseline_avg) * 100

            summary_row = {
                "variant": variant_name,
                "version": version,
                "runs": len(rows),
                "completed_runs": len(completed_rows),
                "success_rate": len(completed_rows) / len(rows) if rows else 0,
                "avg_steps": avg_steps,
                "avg_duration_sec": avg_duration,
                "avg_first_deposit_step": statistics.mean(first_deposit_values)
                if first_deposit_values
                else None,
                "avg_wait_between_deposits": statistics.mean(wait_values)
                if wait_values
                else None,
                "avg_green_clear_step": statistics.mean(green_clear_values)
                if green_clear_values
                else None,
                "avg_yellow_clear_step": statistics.mean(yellow_clear_values)
                if yellow_clear_values
                else None,
                "avg_red_clear_step": statistics.mean(red_clear_values)
                if red_clear_values
                else None,
                "marginal_gain_vs_baseline_steps_pct": gain,
                "feasible": True,
                "errors": [],
            }
            summary_rows.append(summary_row)
            variant_summary_rows.append(summary_row)

        variant_analysis[variant_name] = _analysis_for_variant(variant_summary_rows)

    compact_rows = [_compact_run_row(r) for r in all_rows]

    return {
        "meta": {
            "versions": versions,
            "seeds": seeds,
            "max_steps": max_steps,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "results": all_rows,
        "results_compact": compact_rows,
        "summary": summary_rows,
        "analysis": variant_analysis,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark robot policy versions on map variants."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("benchmark_config.example.json"),
        help="Path to benchmark JSON config.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmark_outputs"),
        help="Directory where output files are written.",
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = run_benchmark(config)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "benchmark_report.json"
    csv_path = args.output_dir / "benchmark_runs.csv"
    summary_csv_path = args.output_dir / "benchmark_summary.csv"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_csv(csv_path, report["results_compact"])
    _write_csv(summary_csv_path, report["summary"])

    print(f"Benchmark done. JSON: {json_path}")
    print(f"Runs CSV: {csv_path}")
    print(f"Summary CSV: {summary_csv_path}")


if __name__ == "__main__":
    main()
