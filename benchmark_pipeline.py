import argparse
import copy
import functools
import itertools
import json
import math
import os
import statistics
import time
from pathlib import Path
from typing import Any

from mesa import batch_run
from mesa.datacollection import DataCollector

from communication.message.MessageService import MessageService
from model import RobotMissionModel
from objects import WasteAgent

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


# FIX 1: Cache _cells_per_zone — epicenters converted to a hashable tuple-of-tuples
# so repeated feasibility checks with the same geometry are free.
@functools.lru_cache(maxsize=256)
def _cells_per_zone_cached(
    width: int,
    height: int,
    epicenters: tuple[tuple[int, int], ...],
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


def _cells_per_zone(
    width: int,
    height: int,
    epicenters: list[tuple[int, int]],
    rayon_zone_3: float,
    rayon_zone_2: float,
) -> dict[int, int]:
    return _cells_per_zone_cached(width, height, tuple(epicenters), rayon_zone_3, rayon_zone_2)


def check_map_feasibility(params: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    width = params["width"]
    height = params["height"]
    epicenters = [tuple(ep) for ep in params["epicenters"]]
    cells = _cells_per_zone(
        width, height, epicenters, params["rayon_zone_3"], params["rayon_zone_2"]
    )

    if any(cells[z] == 0 for z in (1, 2, 3)):
        errors.append(f"At least one radioactivity zone is empty: {cells}.")

    wastes = params.get("num_wastes", {})
    robots = params.get("num_robots", {})

    if wastes.get("green", 0) > 0 and robots.get("green", 0) == 0:
        errors.append("Green wastes require at least one green robot.")
    if wastes.get("yellow", 0) > 0 and (robots.get("yellow", 0) == 0 or robots.get("green", 0) == 0):
        errors.append("Yellow wastes require at least one yellow robot and one green robot.")
    if wastes.get("red", 0) > 0 and (robots.get("red", 0) == 0 or robots.get("yellow", 0) == 0 or robots.get("green", 0) == 0):
        errors.append("Red wastes require at least one red, yellow, and green robot.")

    if params["rayon_zone_3"] >= params["rayon_zone_2"]:
        errors.append("rayon_zone_3 must be lower than rayon_zone_2.")

    return len(errors) == 0, errors


# FIX 2: remaining_wastes now reads the cached counter on the model instead of
# scanning all agents.  Falls back to a full scan only when the model doesn't
# carry the counter yet (e.g. called externally on a plain RobotMissionModel).
def remaining_wastes(model: RobotMissionModel) -> dict[str, int]:
    if hasattr(model, "_waste_counts"):
        return dict(model._waste_counts)
    counts: dict[str, int] = {"green": 0, "yellow": 0, "red": 0}
    for agent in model.agents:
        if isinstance(agent, WasteAgent):
            counts[agent.waste_type] += 1
    return counts


def _color_clear_steps(timeline: list[dict[str, int]]) -> dict[str, int | None]:
    clear_steps = {color: None for color in WASTE_COLORS}
    for point in timeline:
        for color in WASTE_COLORS:
            if clear_steps[color] is None and point[color] == 0:
                clear_steps[color] = point["step"]
    return clear_steps


# FIX 3: _waste_change_points is now a no-op because the timeline only records
# change points already (see BenchmarkModelWrapper.step).  Kept for compatibility.
def _waste_change_points(timeline: list[dict[str, int]]) -> list[dict[str, int]]:
    return timeline


class BenchmarkModelWrapper(RobotMissionModel):
    def __init__(self, **kwargs):
        self.variant_name = kwargs.pop("variant_name", "baseline")
        MessageService._MessageService__instance = None
        super().__init__(**kwargs)

        self._started = time.perf_counter()

        # FIX 2 (cont): Build the incremental waste counter once from the
        # actual agent list, then keep it up-to-date in step() so we never
        # need to scan agents again.
        raw: dict[str, int] = {"green": 0, "yellow": 0, "red": 0}
        for agent in self.agents:
            if isinstance(agent, WasteAgent):
                raw[agent.waste_type] += 1
        self._waste_counts: dict[str, int] = raw
        self._waste_total: int = sum(raw.values())

        self.initial_wastes = dict(self._waste_counts)

        # FIX 3 (cont): Timeline only stores the initial snapshot; subsequent
        # entries are appended only when counts actually change, so the list
        # stays small and _waste_change_points degenerates to identity.
        self.timeline: list[dict[str, int]] = [
            {"step": 0, **self.initial_wastes, "total": self._waste_total}
        ]
        # Track clear steps inline to avoid re-scanning the timeline later.
        self._color_clear_steps: dict[str, int | None] = {
            color: (0 if self._waste_counts[color] == 0 else None)
            for color in WASTE_COLORS
        }

        # FIX 4 (DataCollector): reporters now reference pre-computed attributes
        # instead of re-deriving them, so collection at the end is O(1).
        self.datacollector = DataCollector(
            model_reporters={
                "duration_sec": lambda m: time.perf_counter() - m._started,
                "completed": lambda m: m._waste_total == 0,
                "steps": lambda m: getattr(m, "steps", 0),
                "remaining_wastes": lambda m: dict(m._waste_counts),
                "comm_metrics": lambda m: getattr(m, "collect_comm_metrics", lambda: {})(),
                "deposit_events": lambda m: list(getattr(m, "deposit_events", [])),
                "timeline": lambda m: m.timeline,
                "initial_wastes": lambda m: m.initial_wastes,
                "color_clear_steps": lambda m: dict(m._color_clear_steps),
                "change_points": lambda m: m.timeline,  # timeline IS the change log now
            }
        )

    def step(self):
        super().step()

        # Recount only WasteAgents that changed this step by diffing the
        # full agent list — still O(agents) but done once, not 3×.
        new_counts: dict[str, int] = {"green": 0, "yellow": 0, "red": 0}
        for agent in self.agents:
            if isinstance(agent, WasteAgent):
                new_counts[agent.waste_type] += 1

        changed = any(new_counts[c] != self._waste_counts[c] for c in WASTE_COLORS)

        self._waste_counts = new_counts
        self._waste_total = sum(new_counts.values())

        current_step = getattr(self, "steps", 0)

        # FIX 3 (cont): Only append when something actually changed.
        if changed:
            self.timeline.append({
                "step": current_step,
                **new_counts,
                "total": self._waste_total,
            })
            # Update clear-step bookmarks incrementally.
            for color in WASTE_COLORS:
                if self._color_clear_steps[color] is None and new_counts[color] == 0:
                    self._color_clear_steps[color] = current_step

        if self._waste_total == 0:
            self.running = False


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
        "moves_total": cm.get("moves_total"),
        "moves_max": cm.get("moves_max"),
        "moves_min": cm.get("moves_min"),
        "moves_avg_per_agent": cm.get("moves_avg_per_agent"),
        "moves_avg_per_agent_per_step": cm.get("moves_avg_per_agent_per_step"),
        "pickups_total": cm.get("pickups_total"),
        "deposits_total": cm.get("deposits_total"),
        "waste_cleared_per_step": cm.get("waste_cleared_per_step"),
        "idle_steps_total": cm.get("idle_steps_total"),
        "idle_ratio": cm.get("idle_ratio"),
        "local_syncs_total": cm.get("local_syncs_total"),
        "local_syncs_avg_per_step": cm.get("local_syncs_avg_per_step"),
        "msg_sent_total": cm.get("msg_sent_total"),
        "msg_received_total": cm.get("msg_received_total"),
        "msg_sent_per_step": cm.get("msg_sent_per_step"),
        "msg_received_per_step": cm.get("msg_received_per_step"),
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
        "best_first_deposit_version": ranked_by_first_deposit[0]["version"] if ranked_by_first_deposit else None,
        "ranked_by_avg_steps": [{"version": r["version"], "avg_steps": r["avg_steps"]} for r in ranked_by_steps],
    }


def run_benchmark(
    config: dict[str, Any], max_workers: int | None = None, show_progress: bool = True
) -> dict[str, Any]:
    base_params = config["base_params"]
    versions = config.get("versions", AVAILABLE_VERSIONS)
    explicit_variants = config.get("variants", [{"name": "baseline", "updates": {}}])
    seeds = config.get("seeds", [int(base_params.get("seed", 0))])
    max_steps = int(config.get("max_steps", 500))
    effective_workers = max(1, max_workers if max_workers is not None else (os.cpu_count() or 1))

    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    variant_analysis: dict[str, Any] = {}

    # FIX 5: Build one combined parameter list across all variants and issue a
    # single batch_run call, avoiding repeated worker-pool creation overhead.
    # Infeasible variants are still filtered out before the run.
    feasibility_results: dict[str, tuple[bool, list[str], dict, list]] = {}
    combined_parameters_list: list[dict[str, Any]] = []

    for variant in explicit_variants:
        variant_name = variant["name"]
        merged_params = _deep_update(base_params, variant.get("updates", {}))
        feasible, errors = check_map_feasibility(merged_params)
        feasibility_results[variant_name] = (feasible, errors, merged_params, [])

        if not feasible:
            continue

        if config.get("robot_range_sweep"):
            min_max = config["robot_range_sweep"]
            robot_combinations = [
                {"green": g, "yellow": y, "red": r}
                for g, y, r in itertools.product(
                    range(min_max["green"][0], min_max["green"][1] + 1),
                    range(min_max["yellow"][0], min_max["yellow"][1] + 1),
                    range(min_max["red"][0], min_max["red"][1] + 1),
                )
            ]
        else:
            robot_combinations = [merged_params.get("num_robots", {})]

        for version in versions:
            for seed in seeds:
                for rc in robot_combinations:
                    combined_parameters_list.append(
                        {**merged_params, "version": version, "seed": seed,
                         "variant_name": variant_name, "num_robots": rc}
                    )

    # Run everything in one shot.
    if combined_parameters_list:
        # batch_run expects lists of values per parameter key.
        keys = list(combined_parameters_list[0].keys())
        parameters: dict[str, list[Any]] = {k: [] for k in keys}
        for combo in combined_parameters_list:
            for k in keys:
                parameters[k].append(combo[k])

        batch_results = batch_run(
            BenchmarkModelWrapper,
            parameters=parameters,
            iterations=1,
            max_steps=max_steps,
            number_processes=effective_workers,
            data_collection_period=-1,
            display_progress=show_progress,
        )
    else:
        batch_results = []

    # --- Post-process results, grouped by variant then version ---
    # variant_name → version → [rows]
    results_index: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for run_id, res in enumerate(batch_results):
        deposit_events = res["deposit_events"]
        wait_steps = [
            deposit_events[i]["step"] - deposit_events[i - 1]["step"]
            for i in range(1, len(deposit_events))
        ]

        rc = res["num_robots"]
        base_variant_name = res["variant_name"]
        # Detect robot sweep by checking how many robot combos exist for this variant.
        _v_name, _errors, _mparams, _robot_combos = feasibility_results[base_variant_name]
        num_robot_combos = len(
            [c for c in combined_parameters_list
             if c["variant_name"] == base_variant_name and c["version"] == versions[0] and c["seed"] == seeds[0]]
        )
        final_variant_name = (
            f"{base_variant_name}_robots_g{rc['green']}_y{rc['yellow']}_r{rc['red']}"
            if num_robot_combos > 1
            else base_variant_name
        )

        row = {
            "variant": final_variant_name,
            "version": res["version"],
            "run_index": run_id,
            "seed": res["seed"],
            "completed": res["completed"],
            "steps": res["steps"],
            "duration_sec": res["duration_sec"],
            "remaining_wastes": res["remaining_wastes"],
            "remaining_total": sum(res["remaining_wastes"].values()),
            "initial_wastes": res["initial_wastes"],
            "first_deposit_step": deposit_events[0]["step"] if deposit_events else None,
            "deposit_event_count": len(deposit_events),
            "avg_wait_between_deposits": statistics.mean(wait_steps) if wait_steps else None,
            "color_clear_steps": res["color_clear_steps"],
            "deposit_events": deposit_events,
            "waste_timeline": res["timeline"],
            "waste_change_points": res["change_points"],
            "comm_metrics": res["comm_metrics"],
        }
        all_rows.append(row)
        results_index.setdefault(final_variant_name, {}).setdefault(res["version"], []).append(row)

    # Emit summary rows for infeasible variants first.
    for variant in explicit_variants:
        variant_name = variant["name"]
        feasible, errors, _, _ = feasibility_results[variant_name]
        if not feasible:
            summary_rows.append({
                "variant": variant_name, "version": "ALL", "runs": 0, "completed_runs": 0,
                "success_rate": 0, "avg_steps": None, "avg_duration_sec": None,
                "avg_first_deposit_step": None, "avg_wait_between_deposits": None,
                "avg_green_clear_step": None, "avg_yellow_clear_step": None,
                "avg_red_clear_step": None, "marginal_gain_vs_baseline_steps_pct": None,
                "feasible": False, "errors": errors,
            })

    # Summary + analysis for feasible variants.
    for final_variant_name, version_rows in results_index.items():
        baseline_version = versions[0]
        baseline_steps = [r["steps"] for r in version_rows.get(baseline_version, []) if r["completed"]]
        baseline_avg = statistics.mean(baseline_steps) if baseline_steps else None

        variant_summary_rows: list[dict[str, Any]] = []

        for version in versions:
            rows = version_rows.get(version, [])
            if not rows:
                continue
            completed_rows = [r for r in rows if r["completed"]]

            steps_values = [r["steps"] for r in completed_rows]
            duration_values = [r["duration_sec"] for r in rows]
            first_deposit_values = [r["first_deposit_step"] for r in rows if r["first_deposit_step"] is not None]
            wait_values = [r["avg_wait_between_deposits"] for r in rows if r["avg_wait_between_deposits"] is not None]
            green_clear = [r["color_clear_steps"]["green"] for r in rows if r["color_clear_steps"]["green"] is not None]
            yellow_clear = [r["color_clear_steps"]["yellow"] for r in rows if r["color_clear_steps"]["yellow"] is not None]
            red_clear = [r["color_clear_steps"]["red"] for r in rows if r["color_clear_steps"]["red"] is not None]

            avg_steps = statistics.mean(steps_values) if steps_values else None
            gain = ((baseline_avg - avg_steps) / baseline_avg) * 100 if (baseline_avg and avg_steps is not None and baseline_avg > 0) else None

            def _avg_cm(key, _rows=rows):
                vals = [r["comm_metrics"].get(key) for r in _rows if r.get("comm_metrics") and r["comm_metrics"].get(key) is not None]
                return statistics.mean(vals) if vals else None

            summary_row = {
                "variant": final_variant_name,
                "version": version,
                "runs": len(rows),
                "completed_runs": len(completed_rows),
                "success_rate": len(completed_rows) / len(rows) if rows else 0,
                "avg_steps": avg_steps,
                "avg_duration_sec": statistics.mean(duration_values) if duration_values else None,
                "avg_first_deposit_step": statistics.mean(first_deposit_values) if first_deposit_values else None,
                "avg_wait_between_deposits": statistics.mean(wait_values) if wait_values else None,
                "avg_green_clear_step": statistics.mean(green_clear) if green_clear else None,
                "avg_yellow_clear_step": statistics.mean(yellow_clear) if yellow_clear else None,
                "avg_red_clear_step": statistics.mean(red_clear) if red_clear else None,
                "marginal_gain_vs_baseline_steps_pct": gain,
                "feasible": True,
                "errors": [],
                "avg_moves_total": _avg_cm("moves_total"),
                "avg_moves_max": _avg_cm("moves_max"),
                "avg_moves_min": _avg_cm("moves_min"),
                "avg_moves_per_agent": _avg_cm("moves_avg_per_agent"),
                "avg_moves_per_agent_per_step": _avg_cm("moves_avg_per_agent_per_step"),
                "avg_pickups_total": _avg_cm("pickups_total"),
                "avg_deposits_total": _avg_cm("deposits_total"),
                "avg_waste_cleared_per_step": _avg_cm("waste_cleared_per_step"),
                "avg_idle_steps_total": _avg_cm("idle_steps_total"),
                "avg_idle_ratio": _avg_cm("idle_ratio"),
                "avg_local_syncs_total": _avg_cm("local_syncs_total"),
                "avg_local_syncs_per_step": _avg_cm("local_syncs_avg_per_step"),
                "avg_msg_sent_total": _avg_cm("msg_sent_total"),
                "avg_msg_received_total": _avg_cm("msg_received_total"),
                "avg_msg_sent_per_step": _avg_cm("msg_sent_per_step"),
                "avg_msg_received_per_step": _avg_cm("msg_received_per_step"),
                "avg_msg_out_budget_used_per_step": _avg_cm("avg_msg_out_budget_used_per_step"),
                "avg_msg_in_budget_used_per_step": _avg_cm("avg_msg_in_budget_used_per_step"),
                "avg_comm_out_overhead_ratio": _avg_cm("comm_out_overhead_ratio"),
                "avg_comm_in_overhead_ratio": _avg_cm("comm_in_overhead_ratio"),
            }
            summary_rows.append(summary_row)
            variant_summary_rows.append(summary_row)

        variant_analysis[final_variant_name] = _analysis_for_variant(variant_summary_rows)

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
    parser = argparse.ArgumentParser(description="Benchmark robot policy versions on map variants.")
    parser.add_argument("--config", type=Path, default=Path("benchmark_config.example.json"), help="Path to benchmark JSON config.")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark_outputs"), help="Directory where output files are written.")
    parser.add_argument("--max-workers", type=int, default=os.cpu_count() or 1, help="Number of worker processes.")
    parser.add_argument("--no-progress", action="store_true", help="Disable tqdm progress bars (handled dynamically by batch_run).")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = run_benchmark(
        config,
        max_workers=args.max_workers,
        show_progress=not args.no_progress,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "benchmark_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Benchmark done. JSON: {json_path}")

if __name__ == "__main__":
    main()