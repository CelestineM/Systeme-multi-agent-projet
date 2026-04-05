"""
Lit les fichiers benchmark_outputs/ et génère des logs TensorBoard propres.

Usage
-----
    pip install tensorboard

    python benchmark_tensorboard.py --input-dir benchmark_outputs --logdir tb_logs_clean

    # Dans un autre terminal :
    python -m tensorboard.main --logdir tb_logs_clean --host 127.0.0.1
    # Puis : http://127.0.0.1:6006

Structure TensorBoard générée
------------------------------
  Un writer par version (v0.0.1, v0.0.2, v0.0.3).
  L'axe X = index du variant (trié alphabétiquement) → un point par variant.

  Sections de scalaires :
    efficiency/   – steps, first_deposit_step, waste_cleared_per_step,
                    green/yellow/red_clear_step, deposit_event_count,
                    avg_wait_between_deposits
    movement/     – moves_total, moves_avg_per_agent, moves_avg_per_agent_per_step,
                    moves_max, moves_min, pickups_total, deposits_total
    communication/– msg_sent_total, msg_received_total, local_syncs_total,
                    comm_out_overhead_ratio, comm_in_overhead_ratio
    completion/   – completed (taux), remaining_total, duration_sec

  Pour chaque métrique on écrit TROIS valeurs (mean / min / max sur les seeds)
  → visible comme 3 courbes parallèles dans TensorBoard, ce qui donne
  l'équivalent d'un intervalle de confiance sans dépendre de numpy.

  En plus, le group `_by_version/` compare directement les 3 versions
  dans le même graphique (même tag, writers différents).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path

# ── Writer ────────────────────────────────────────────────────────────────────
from tensorboard.summary.writer.event_file_writer import EventFileWriter
from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary


class SimpleWriter:
    """Writer minimal utilisant uniquement le package tensorboard (sans torch)."""

    def __init__(self, log_dir: str):
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self._writer = EventFileWriter(log_dir)

    def add_scalar(self, tag: str, value: float, step: int):
        if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
            return
        sv = Summary.Value(tag=tag, simple_value=float(value))
        s  = Summary(value=[sv])
        e  = Event(step=step, summary=s, wall_time=time.time())
        self._writer.add_event(e)

    def flush(self):
        self._writer.flush()

    def close(self):
        self._writer.flush()
        self._writer.close()


# ── Métriques à exporter ──────────────────────────────────────────────────────
# (clé_csv, tag_tensorboard, lower_is_better)
METRICS = [
    # Efficiency
    ("steps",                       "efficiency/steps",                     True),
    ("first_deposit_step",          "efficiency/first_deposit_step",        True),
    ("waste_cleared_per_step",      "efficiency/waste_cleared_per_step",    False),
    ("deposit_event_count",         "efficiency/deposit_event_count",       False),
    ("avg_wait_between_deposits",   "efficiency/avg_wait_between_deposits", True),
    ("green_clear_step",            "efficiency/green_clear_step",          True),
    ("yellow_clear_step",           "efficiency/yellow_clear_step",         True),
    ("red_clear_step",              "efficiency/red_clear_step",            True),
    # Movement
    ("moves_total",                 "movement/moves_total",                 True),
    ("moves_avg_per_agent",         "movement/moves_avg_per_agent",         True),
    ("moves_avg_per_agent_per_step","movement/moves_avg_per_agent_per_step",True),
    ("moves_max",                   "movement/moves_max",                   True),
    ("moves_min",                   "movement/moves_min",                   True),
    ("pickups_total",               "movement/pickups_total",               False),
    ("deposits_total",              "movement/deposits_total",              False),
    ("idle_ratio",                  "movement/idle_ratio",                  True),
    # Communication
    ("msg_sent_total",              "communication/msg_sent_total",         None),
    ("msg_received_total",          "communication/msg_received_total",     None),
    ("local_syncs_total",           "communication/local_syncs_total",      None),
    ("local_syncs_avg_per_step",    "communication/local_syncs_avg_per_step", None),
    ("comm_out_overhead_ratio",     "communication/comm_out_overhead_ratio",None),
    ("comm_in_overhead_ratio",      "communication/comm_in_overhead_ratio", None),
    ("avg_msg_out_budget_used_per_step", "communication/msg_out_budget_per_step", None),
    ("avg_msg_in_budget_used_per_step",  "communication/msg_in_budget_per_step",  None),
    # Completion
    ("completed",                   "completion/success_rate",              False),
    ("remaining_total",             "completion/remaining_wastes",          True),
    ("duration_sec",                "completion/duration_sec",              True),
]


def _safe_float(v: str) -> float | None:
    if v in ("", "None", "nan", "inf", "-inf"):
        return None
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return None


def load_runs(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def aggregate(rows: list[dict]) -> dict[str, dict[str, dict[str, dict]]]:
    """
    Retourne :
        { variant -> { version -> { metric_key -> [float values] } } }
    """
    data: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for row in rows:
        variant = row["variant"]
        version = row["version"]
        for key, _, _ in METRICS:
            v = _safe_float(row.get(key, ""))
            if v is not None:
                data[variant][version][key].append(v)
    return data


def write_logs(data: dict, logdir: Path):
    versions  = sorted({v for var in data.values() for v in var})
    variants  = sorted(data.keys())

    # ── Un writer par version (pour comparer dans le même graphique) ──────────
    version_writers: dict[str, SimpleWriter] = {}
    for ver in versions:
        d = logdir / ver
        d.mkdir(parents=True, exist_ok=True)
        version_writers[ver] = SimpleWriter(str(d))

    # ── Écriture principale : 1 point par variant (X = index variant) ─────────
    for vi, variant in enumerate(variants):
        print(f"  [{vi+1}/{len(variants)}] {variant}")
        for ver in versions:
            w = version_writers[ver]
            metrics_for_ver = data[variant].get(ver, {})

            for key, tag, _ in METRICS:
                vals = metrics_for_ver.get(key, [])
                if not vals:
                    continue
                mean_v = statistics.mean(vals)
                min_v  = min(vals)
                max_v  = max(vals)

                # Valeur principale (mean)
                w.add_scalar(tag, mean_v, step=vi)
                # Enveloppes min/max (tag séparé pour éviter le bruit)
                w.add_scalar(f"{tag}__min", min_v, step=vi)
                w.add_scalar(f"{tag}__max", max_v, step=vi)

            w.flush()

    # ── Writer de ranking : meilleure version par métrique ────────────────────
    ranking_dir = logdir / "_ranking"
    ranking_dir.mkdir(parents=True, exist_ok=True)
    ranking_writers = {ver: SimpleWriter(str(ranking_dir / ver)) for ver in versions}

    for vi, variant in enumerate(variants):
        for key, tag, lower_is_better in METRICS:
            if lower_is_better is None:
                continue
            version_means = []
            for ver in versions:
                vals = data[variant].get(ver, {}).get(key, [])
                if vals:
                    version_means.append((ver, statistics.mean(vals)))
            if not version_means:
                continue
            version_means.sort(key=lambda x: x[1], reverse=not lower_is_better)
            for rank, (ver, mean_val) in enumerate(version_means):
                ranking_writers[ver].add_scalar(f"ranking/{tag}", mean_val, step=vi)

    for w in ranking_writers.values():
        w.flush(); w.close()

    # ── Writer global : une courbe par version × métrique agrégée sur TOUS les variants
    global_dir = logdir / "_global_summary"
    global_dir.mkdir(parents=True, exist_ok=True)
    global_writers = {ver: SimpleWriter(str(global_dir / ver)) for ver in versions}

    # Pour chaque version, agréger toutes les seeds de tous les variants
    for ver in versions:
        gw = global_writers[ver]
        all_by_key: dict[str, list[float]] = defaultdict(list)
        for variant in variants:
            for key, _, _ in METRICS:
                all_by_key[key].extend(data[variant].get(ver, {}).get(key, []))

        for step, variant in enumerate(variants):
            for key, tag, _ in METRICS:
                vals = data[variant].get(ver, {}).get(key, [])
                if vals:
                    gw.add_scalar(f"summary/{tag}", statistics.mean(vals), step=step)
        gw.flush(); gw.close()

    for ver, w in version_writers.items():
        w.flush(); w.close()

    print(f"\nLogs écrits dans : {logdir.resolve()}")
    print(f"Versions : {versions}")
    print(f"Variants : {len(variants)}")


def print_text_summary(data: dict):
    """Affiche un résumé texte des meilleures versions par métrique clé."""
    versions = sorted({v for var in data.values() for v in var})
    variants = sorted(data.keys())

    KEY_METRICS = [
        ("steps",              "Nb steps moyen",           True),
        ("moves_total",        "Mouvements totaux",         True),
        ("waste_cleared_per_step", "Déchets/step",          False),
        ("first_deposit_step", "1er dépôt (step)",          True),
        ("completed",          "Taux de complétion",        False),
        ("msg_sent_total",     "Messages envoyés",          None),
        ("local_syncs_total",  "Syncs locaux",              None),
    ]

    print("\n" + "="*70)
    print("RÉSUMÉ GLOBAL — moyenne sur tous les variants et seeds")
    print("="*70)

    for key, label, lower_is_better in KEY_METRICS:
        print(f"\n  {label}")
        version_means = []
        for ver in versions:
            all_vals = []
            for variant in variants:
                all_vals.extend(data[variant].get(ver, {}).get(key, []))
            if all_vals:
                m = statistics.mean(all_vals)
                version_means.append((ver, m))
                print(f"    {ver}: {m:.3f}")
            else:
                print(f"    {ver}: n/a")

        if lower_is_better is not None and len(version_means) > 1:
            version_means.sort(key=lambda x: x[1], reverse=not lower_is_better)
            best = version_means[0]
            worst = version_means[-1]
            delta = abs(best[1] - worst[1])
            pct = (delta / abs(worst[1]) * 100) if worst[1] != 0 else 0
            direction = "↓ moins" if lower_is_better else "↑ plus"
            print(f"    → Meilleur: {best[0]} ({direction} de {pct:.1f}% vs le pire)")

    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(
        description="Exporte les résultats benchmark vers TensorBoard (sans torch)."
    )
    parser.add_argument(
        "--input-dir", type=Path, default=Path("benchmark_outputs"),
        help="Dossier contenant benchmark_runs_tb.csv"
    )
    parser.add_argument(
        "--csv-file", type=str, default="benchmark_runs_tb.csv",
        help="Nom du fichier CSV de runs (dans --input-dir)"
    )
    parser.add_argument(
        "--logdir", type=Path, default=Path("tb_logs_clean"),
        help="Dossier de sortie TensorBoard"
    )
    args = parser.parse_args()

    csv_path = args.input_dir / args.csv_file
    if not csv_path.exists():
        # Essayer l'autre nom
        alt = args.input_dir / "benchmark_runs.csv"
        if alt.exists():
            csv_path = alt
        else:
            raise FileNotFoundError(f"CSV introuvable : {csv_path}")

    print(f"Lecture de {csv_path}...")
    rows = load_runs(csv_path)
    print(f"  {len(rows)} runs chargés")

    print("Agrégation...")
    data = aggregate(rows)

    print_text_summary(data)

    print(f"\nGénération des logs TensorBoard dans {args.logdir}...")
    write_logs(data, args.logdir)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Lance TensorBoard avec :                                    ║
║                                                              ║
║  python -m tensorboard.main --logdir {str(args.logdir):<24} ║
║                   --host 127.0.0.1                           ║
║                                                              ║
║  Puis ouvre : http://127.0.0.1:6006                          ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()