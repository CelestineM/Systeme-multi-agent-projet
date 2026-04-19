import argparse
import concurrent.futures
import contextlib
import copy
import io
import itertools
import json
import math
import os
import statistics
import time
from pathlib import Path
from typing import Any

from communication.message.MessageService import MessageService
from model import RobotMissionModel
from objects import WasteAgent
from tqdm import tqdm

AVAILABLE_VERSIONS = ["v0.0.1", "v0.0.2", "v0.0.3", "v0.0.4"]
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
        while steps < max_steps and not completed:
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

    comm_metrics = model.collect_comm_metrics()

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
        "comm_metrics": comm_metrics,
    }


def _run_single_task(task: dict[str, Any]) -> dict[str, Any]:
    row = run_single(task["params"], task["version"], task["max_steps"])
    row["variant"] = task["variant"]
    row["run_index"] = task["run_index"]
    row["seed"] = task["seed"]
    return row


def _run_variant_tasks(
    variant_name: str,
    merged_params: dict[str, Any],
    versions: list[str],
    seeds: list[int],
    max_steps: int,
    max_workers: int,
    show_progress: bool,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for run_index, run_seed in enumerate(seeds):
        run_params = copy.deepcopy(merged_params)
        run_params["seed"] = run_seed
        for version in versions:
            tasks.append(
                {
                    "variant": variant_name,
                    "run_index": run_index,
                    "seed": run_seed,
                    "version": version,
                    "params": run_params,
                    "max_steps": max_steps,
                }
            )

    if not tasks:
        return []

    if max_workers <= 1:
        rows: list[dict[str, Any]] = []
        iterator = tqdm(
            tasks,
            total=len(tasks),
            desc=f"{variant_name}",
            leave=False,
            disable=not show_progress,
        )
        for task in iterator:
            rows.append(_run_single_task(task))
        return rows

    rows = []
    workers = min(max_workers, len(tasks))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_run_single_task, task) for task in tasks]
        progress = tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc=f"{variant_name}",
            leave=False,
            disable=not show_progress,
        )
        for future in progress:
            rows.append(future.result())

    version_order = {version: idx for idx, version in enumerate(versions)}
    rows.sort(key=lambda row: (row["run_index"], version_order.get(row["version"], 9999)))
    return rows


def _compact_run_row(row: dict[str, Any]) -> dict[str, Any]:
    clear_steps = row["color_clear_steps"]
    cm = row.get("comm_metrics", {})
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
        # Mouvements
        "moves_total": cm.get("moves_total"),
        "moves_max": cm.get("moves_max"),
        "moves_min": cm.get("moves_min"),
        "moves_avg_per_agent": cm.get("moves_avg_per_agent"),
        "moves_avg_per_agent_per_step": cm.get("moves_avg_per_agent_per_step"),
        # Actions de pickup/deposit
        "pickups_total": cm.get("pickups_total"),
        "deposits_total": cm.get("deposits_total"),
        "waste_cleared_per_step": cm.get("waste_cleared_per_step"),
        "idle_steps_total": cm.get("idle_steps_total"),
        "idle_ratio": cm.get("idle_ratio"),
        # Communication locale
        "local_syncs_total": cm.get("local_syncs_total"),
        "local_syncs_avg_per_step": cm.get("local_syncs_avg_per_step"),
        # Messages envoyés/reçus - si possible
        "msg_sent_total": cm.get("msg_sent_total"),
        "msg_received_total": cm.get("msg_received_total"),
        "msg_sent_per_step": cm.get("msg_sent_per_step"),
        "msg_received_per_step": cm.get("msg_received_per_step"),
        # Budget de communication consommé
        "avg_msg_out_budget_used_per_step": cm.get("avg_msg_out_budget_used_per_step"),
        "avg_msg_in_budget_used_per_step": cm.get("avg_msg_in_budget_used_per_step"),
        "comm_out_overhead_ratio": cm.get("comm_out_overhead_ratio"),
        "comm_in_overhead_ratio": cm.get("comm_in_overhead_ratio"),
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


def _merge_rows_by_key(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}

    for row in existing_rows:
        if not isinstance(row, dict):
            continue
        key = tuple(row.get(field) for field in key_fields)
        merged[key] = row

    for row in new_rows:
        if not isinstance(row, dict):
            continue
        key = tuple(row.get(field) for field in key_fields)
        merged[key] = row

    return list(merged.values())


def _rebuild_analysis_from_summary(summary_rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_variant: dict[str, list[dict[str, Any]]] = {}
    for row in summary_rows:
        if not isinstance(row, dict):
            continue
        if row.get("version") == "ALL":
            continue
        variant = row.get("variant")
        if not isinstance(variant, str):
            continue
        per_variant.setdefault(variant, []).append(row)

    return {
        variant: _analysis_for_variant(rows)
        for variant, rows in per_variant.items()
    }


def _merge_reports(existing: dict[str, Any], new_report: dict[str, Any]) -> dict[str, Any]:
    existing_meta = existing.get("meta", {}) if isinstance(existing.get("meta"), dict) else {}
    new_meta = new_report.get("meta", {}) if isinstance(new_report.get("meta"), dict) else {}

    merged_results = _merge_rows_by_key(
        existing.get("results", []) if isinstance(existing.get("results"), list) else [],
        new_report.get("results", []) if isinstance(new_report.get("results"), list) else [],
        ("variant", "version", "run_index", "seed"),
    )
    merged_results_compact = _merge_rows_by_key(
        existing.get("results_compact", []) if isinstance(existing.get("results_compact"), list) else [],
        new_report.get("results_compact", []) if isinstance(new_report.get("results_compact"), list) else [],
        ("variant", "version", "run_index", "seed"),
    )

    merged_summary = _merge_rows_by_key(
        existing.get("summary", []) if isinstance(existing.get("summary"), list) else [],
        new_report.get("summary", []) if isinstance(new_report.get("summary"), list) else [],
        ("variant", "version"),
    )

    versions = sorted(
        {
            str(v)
            for v in (existing_meta.get("versions", []) + new_meta.get("versions", []))
            if isinstance(v, str)
        },
        key=lambda v: AVAILABLE_VERSIONS.index(v) if v in AVAILABLE_VERSIONS else len(AVAILABLE_VERSIONS),
    )
    seeds = sorted(
        {
            int(s)
            for s in (existing_meta.get("seeds", []) + new_meta.get("seeds", []))
            if isinstance(s, int)
        }
    )

    return {
        "meta": {
            "versions": versions,
            "seeds": seeds,
            "max_steps": new_meta.get("max_steps", existing_meta.get("max_steps")),
            "max_workers": new_meta.get("max_workers", existing_meta.get("max_workers")),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "results": merged_results,
        "results_compact": merged_results_compact,
        "summary": merged_summary,
        "analysis": _rebuild_analysis_from_summary(merged_summary),
    }


def run_benchmark(
    config: dict[str, Any],
    max_workers: int | None = None,
    show_progress: bool = True,
) -> dict[str, Any]:
    base_params = config["base_params"]
    versions = config.get("versions", AVAILABLE_VERSIONS)
    variants = _build_variants(config)
    seeds = _build_seed_list(config, base_params)
    max_steps = int(config.get("max_steps", 500))
    effective_workers = max_workers if max_workers is not None else (os.cpu_count() or 1)
    effective_workers = max(1, int(effective_workers))

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
        variant_rows = _run_variant_tasks(
            variant_name=variant_name,
            merged_params=merged_params,
            versions=versions,
            seeds=seeds,
            max_steps=max_steps,
            max_workers=effective_workers,
            show_progress=show_progress,
        )
        for row in variant_rows:
            all_rows.append(row)
            variant_version_rows[row["version"]].append(row)

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

            def _avg_cm(key):
                vals = [r["comm_metrics"].get(key) for r in rows if r.get("comm_metrics") and r["comm_metrics"].get(key) is not None]
                return statistics.mean(vals) if vals else None

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
                # Mouvements
                "avg_moves_total": _avg_cm("moves_total"),
                "avg_moves_max": _avg_cm("moves_max"),
                "avg_moves_min": _avg_cm("moves_min"),
                "avg_moves_per_agent": _avg_cm("moves_avg_per_agent"),
                "avg_moves_per_agent_per_step": _avg_cm("moves_avg_per_agent_per_step"),
                # Actions de pickup/deposit
                "avg_pickups_total": _avg_cm("pickups_total"),
                "avg_deposits_total": _avg_cm("deposits_total"),
                "avg_waste_cleared_per_step": _avg_cm("waste_cleared_per_step"),
                "avg_idle_steps_total": _avg_cm("idle_steps_total"),
                "avg_idle_ratio": _avg_cm("idle_ratio"),
                # Communication locale
                "avg_local_syncs_total": _avg_cm("local_syncs_total"),
                "avg_local_syncs_per_step": _avg_cm("local_syncs_avg_per_step"),
                # Messages envoyés/reçus - si possible
                "avg_msg_sent_total": _avg_cm("msg_sent_total"),
                "avg_msg_received_total": _avg_cm("msg_received_total"),
                "avg_msg_sent_per_step": _avg_cm("msg_sent_per_step"),
                "avg_msg_received_per_step": _avg_cm("msg_received_per_step"),
                # Budget de communication consommé
                "avg_msg_out_budget_used_per_step": _avg_cm("avg_msg_out_budget_used_per_step"),
                "avg_msg_in_budget_used_per_step": _avg_cm("avg_msg_in_budget_used_per_step"),
                "avg_comm_out_overhead_ratio": _avg_cm("comm_out_overhead_ratio"),
                "avg_comm_in_overhead_ratio": _avg_cm("comm_in_overhead_ratio"),
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
            "max_workers": effective_workers,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "results": all_rows,
        "results_compact": compact_rows,
        "summary": summary_rows,
        "analysis": variant_analysis,
    }


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
    parser.add_argument(
        "--max-workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Number of worker processes used to run simulations asynchronously.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars.",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Run benchmark for a single version only (e.g. v0.0.4).",
    )
    parser.add_argument(
        "--versions",
        type=str,
        default=None,
        help="Comma-separated versions to run (e.g. v0.0.3,v0.0.4).",
    )
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help="Append/merge into existing benchmark_report.json instead of overwriting it.",
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))

    if args.version and args.versions:
        raise ValueError("Use either --version or --versions, not both.")

    selected_versions = None
    if args.version:
        selected_versions = [args.version.strip()]
    elif args.versions:
        selected_versions = [v.strip() for v in args.versions.split(",") if v.strip()]

    if selected_versions is not None:
        invalid_versions = [v for v in selected_versions if v not in AVAILABLE_VERSIONS]
        if invalid_versions:
            raise ValueError(
                f"Unknown versions: {invalid_versions}. Available: {AVAILABLE_VERSIONS}"
            )
        config["versions"] = selected_versions

    report = run_benchmark(
        config,
        max_workers=args.max_workers,
        show_progress=not args.no_progress,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "benchmark_report.json"

    if args.append_existing and json_path.exists():
        existing = json.loads(json_path.read_text(encoding="utf-8"))
        report = _merge_reports(existing, report)

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Benchmark done. JSON: {json_path}")


if __name__ == "__main__":
    main()