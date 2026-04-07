#!/usr/bin/env python3
"""
Génère un dashboard HTML interactif à partir des logs TensorBoard par variant.

Le README GitHub ne peut pas embarquer une vraie interface JS. La bonne approche
est donc :
1. lire les `.tfevents`,
2. construire une page HTML autonome avec sélecteurs,
3. lier cette page depuis le README.

Usage
-----
    python3 generate_benchmark_dashboard.py --logdir tb_logs --output docs/index.html
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
except ImportError as exc:
    raise SystemExit(
        "Le package `tensorboard` est requis. Installe-le avec "
        "`pip install -r requirements.txt` ou `pip install tensorboard`."
    ) from exc


VERSION_ORDER = ["v0.0.1", "v0.0.2", "v0.0.3"]
VERSION_META = {
    "v0.0.1": {
        "label": "v0.0.1",
        "subtitle": "Naive + NoKnowledgeSharing",
        "color": "#f59e0b",
    },
    "v0.0.2": {
        "label": "v0.0.2",
        "subtitle": "Naive + LocalKnowledgeSharing",
        "color": "#2563eb",
    },
    "v0.0.3": {
        "label": "v0.0.3",
        "subtitle": "A* + SmartColorKnowledgeSharing",
        "color": "#dc2626",
    },
}

METRIC_META = {
    "efficiency/total_steps": {
        "label": "Total steps",
        "category": "Efficacité",
        "lower_is_better": True,
        "format": "int",
    },
    "efficiency/first_deposit_step": {
        "label": "Premier depot",
        "category": "Efficacité",
        "lower_is_better": True,
        "format": "int",
    },
    "efficiency/avg_wait_between_deposits": {
        "label": "Attente moyenne entre depots",
        "category": "Efficacité",
        "lower_is_better": True,
        "format": "float2",
    },
    "efficiency/waste_cleared_per_step": {
        "label": "Dechets nettoyes par step",
        "category": "Efficacité",
        "lower_is_better": False,
        "format": "float3",
    },
    "efficiency/green_clear_step": {
        "label": "Step de nettoyage vert",
        "category": "Efficacité",
        "lower_is_better": True,
        "format": "int",
    },
    "efficiency/yellow_clear_step": {
        "label": "Step de nettoyage jaune",
        "category": "Efficacité",
        "lower_is_better": True,
        "format": "int",
    },
    "efficiency/red_clear_step": {
        "label": "Step de nettoyage rouge",
        "category": "Efficacité",
        "lower_is_better": True,
        "format": "int",
    },
    "efficiency/deposit_event_count": {
        "label": "Nombre de depots",
        "category": "Efficacité",
        "lower_is_better": False,
        "format": "int",
    },
    "movement/moves_total": {
        "label": "Mouvements totaux",
        "category": "Mouvements",
        "lower_is_better": True,
        "format": "int",
    },
    "movement/moves_avg_per_agent": {
        "label": "Mouvements moyens par robot",
        "category": "Mouvements",
        "lower_is_better": True,
        "format": "float2",
    },
    "movement/moves_avg_per_agent_per_step": {
        "label": "Mouvements moyens par robot et par step",
        "category": "Mouvements",
        "lower_is_better": True,
        "format": "float3",
    },
    "movement/moves_max": {
        "label": "Mouvements max d'un robot",
        "category": "Mouvements",
        "lower_is_better": True,
        "format": "int",
    },
    "movement/moves_min": {
        "label": "Mouvements min d'un robot",
        "category": "Mouvements",
        "lower_is_better": True,
        "format": "int",
    },
    "movement/pickups_total": {
        "label": "Ramassages totaux",
        "category": "Mouvements",
        "lower_is_better": False,
        "format": "int",
    },
    "movement/deposits_total": {
        "label": "Depots totaux",
        "category": "Mouvements",
        "lower_is_better": False,
        "format": "int",
    },
    "movement/idle_ratio": {
        "label": "Ratio d'inactivite",
        "category": "Mouvements",
        "lower_is_better": True,
        "format": "percent",
    },
    "communication/msg_sent_total": {
        "label": "Messages envoyes",
        "category": "Communication",
        "lower_is_better": None,
        "format": "int",
    },
    "communication/msg_received_total": {
        "label": "Messages recus",
        "category": "Communication",
        "lower_is_better": None,
        "format": "int",
    },
    "communication/msg_sent_per_step": {
        "label": "Messages envoyes par step",
        "category": "Communication",
        "lower_is_better": None,
        "format": "float3",
    },
    "communication/msg_received_per_step": {
        "label": "Messages recus par step",
        "category": "Communication",
        "lower_is_better": None,
        "format": "float3",
    },
    "communication/msg_out_budget_used_per_step": {
        "label": "Budget sortant utilise par step",
        "category": "Communication",
        "lower_is_better": None,
        "format": "percent",
    },
    "communication/msg_in_budget_used_per_step": {
        "label": "Budget entrant utilise par step",
        "category": "Communication",
        "lower_is_better": None,
        "format": "percent",
    },
    "communication/comm_out_overhead_ratio": {
        "label": "Overhead sortant",
        "category": "Communication",
        "lower_is_better": True,
        "format": "percent",
    },
    "communication/comm_in_overhead_ratio": {
        "label": "Overhead entrant",
        "category": "Communication",
        "lower_is_better": True,
        "format": "percent",
    },
    "communication/local_syncs_total": {
        "label": "Synchronisations locales",
        "category": "Communication",
        "lower_is_better": None,
        "format": "int",
    },
    "communication/local_syncs_avg_per_step": {
        "label": "Synchronisations locales par step",
        "category": "Communication",
        "lower_is_better": None,
        "format": "float3",
    },
    "completion/completed": {
        "label": "Taux de completion",
        "category": "Completion",
        "lower_is_better": False,
        "format": "percent",
    },
    "completion/remaining_wastes": {
        "label": "Dechets restants",
        "category": "Completion",
        "lower_is_better": True,
        "format": "int",
    },
    "completion/duration_sec": {
        "label": "Duree CPU",
        "category": "Completion",
        "lower_is_better": True,
        "format": "float2",
    },
}

METRIC_ORDER = list(METRIC_META.keys())
VARIANT_RE = re.compile(
    r"^(?P<scenario>.+)_robots_g(?P<green>\d+)_y(?P<yellow>\d+)_r(?P<red>\d+)$"
)


def _version_sort_key(version: str) -> tuple[int, str]:
    try:
        return (VERSION_ORDER.index(version), version)
    except ValueError:
        return (len(VERSION_ORDER), version)


def _variant_meta(name: str) -> dict:
    match = VARIANT_RE.match(name)
    if not match:
        return {
            "scenario": name,
            "green": None,
            "yellow": None,
            "red": None,
            "label": name,
        }

    scenario = match.group("scenario")
    green = int(match.group("green"))
    yellow = int(match.group("yellow"))
    red = int(match.group("red"))
    return {
        "scenario": scenario,
        "green": green,
        "yellow": yellow,
        "red": red,
        "label": f"{scenario} - g{green} / y{yellow} / r{red}",
    }


def _normalize_tag(tag: str, variant: str, version: str) -> str | None:
    prefix = f"{variant}/{version}/"
    if tag.startswith(prefix):
        normalized = tag[len(prefix) :]
        if normalized.endswith(("__mean", "__min", "__max")):
            return None
        return normalized
    return None


def _load_scalars(version_dir: Path, variant: str, version: str) -> dict[str, list[dict[str, float]]]:
    accumulator = EventAccumulator(str(version_dir), size_guidance={"scalars": 0})
    accumulator.Reload()

    metrics: dict[str, list[dict[str, float]]] = {}
    for tag in accumulator.Tags().get("scalars", []):
        normalized = _normalize_tag(tag, variant, version)
        if normalized is None:
            continue

        events = accumulator.Scalars(tag)
        if not events:
            continue

        metrics[normalized] = [
            {"step": int(event.step), "value": float(event.value)}
            for event in events
        ]
    return metrics


def load_dashboard_data(logdir: Path) -> dict:
    variants: dict[str, dict] = {}
    scenarios: set[str] = set()
    robot_values = {"green": set(), "yellow": set(), "red": set()}
    available_metrics: set[str] = set()
    versions_seen: set[str] = set()

    for variant_dir in sorted(logdir.iterdir()):
        if not variant_dir.is_dir() or variant_dir.name.startswith("_"):
            continue

        version_dirs = [
            child for child in variant_dir.iterdir()
            if child.is_dir() and child.name.startswith("v")
        ]
        if not version_dirs:
            continue

        version_dirs.sort(key=lambda path: _version_sort_key(path.name))
        variant_name = variant_dir.name
        variant_meta = _variant_meta(variant_name)
        scenarios.add(variant_meta["scenario"])
        for color in ("green", "yellow", "red"):
            value = variant_meta[color]
            if value is not None:
                robot_values[color].add(value)

        versions_payload = {}
        for version_dir in version_dirs:
            version = version_dir.name
            versions_seen.add(version)
            metrics = _load_scalars(version_dir, variant_name, version)
            available_metrics.update(metrics.keys())
            versions_payload[version] = metrics

        variants[variant_name] = {
            "meta": variant_meta,
            "versions": versions_payload,
        }

    ordered_metrics = [metric for metric in METRIC_ORDER if metric in available_metrics]
    ordered_metrics.extend(
        sorted(metric for metric in available_metrics if metric not in METRIC_ORDER)
    )

    ordered_versions = sorted(versions_seen, key=_version_sort_key)
    return {
        "generated_from": str(logdir),
        "versions": ordered_versions,
        "version_meta": {ver: VERSION_META.get(ver, {"label": ver, "subtitle": "", "color": "#64748b"}) for ver in ordered_versions},
        "metrics": ordered_metrics,
        "metric_meta": {
            metric: METRIC_META.get(
                metric,
                {
                    "label": metric.split("/")[-1].replace("_", " "),
                    "category": metric.split("/")[0].title(),
                    "lower_is_better": None,
                    "format": "float2",
                },
            )
            for metric in ordered_metrics
        },
        "variants": variants,
        "scenarios": sorted(scenarios),
        "robot_values": {
            color: sorted(values)
            for color, values in robot_values.items()
        },
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Benchmark Dashboard</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255, 252, 247, 0.92);
      --panel-strong: #fff9f0;
      --ink: #1f2937;
      --muted: #6b7280;
      --line: rgba(148, 163, 184, 0.35);
      --accent: #0f766e;
      --accent-soft: rgba(15, 118, 110, 0.12);
      --shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
      --radius: 20px;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.16), transparent 32%),
        radial-gradient(circle at top right, rgba(217, 119, 6, 0.16), transparent 28%),
        linear-gradient(180deg, #f7f2e9 0%, #f4efe6 46%, #efe8dc 100%);
      min-height: 100vh;
    }

    main {
      max-width: 1400px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }

    .hero {
      background: linear-gradient(135deg, rgba(255,255,255,0.84), rgba(255,249,240,0.92));
      border: 1px solid rgba(255,255,255,0.55);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 28px;
      margin-bottom: 22px;
      backdrop-filter: blur(10px);
    }

    .hero h1 {
      margin: 0 0 10px;
      font-size: clamp(2rem, 5vw, 3.4rem);
      line-height: 1.02;
      letter-spacing: -0.04em;
    }

    .hero p {
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
      max-width: 880px;
      line-height: 1.6;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
      gap: 22px;
      align-items: start;
    }

    .panel {
      background: var(--panel);
      border: 1px solid rgba(255, 255, 255, 0.75);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 18px;
      backdrop-filter: blur(10px);
    }

    .sidebar {
      position: sticky;
      top: 20px;
    }

    .section-title {
      margin: 0 0 14px;
      font-size: 0.96rem;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      color: var(--muted);
    }

    .control-grid {
      display: grid;
      gap: 12px;
    }

    label {
      display: grid;
      gap: 6px;
      font-size: 0.92rem;
      color: var(--muted);
    }

    select,
    input {
      width: 100%;
      padding: 11px 12px;
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.25);
      background: rgba(255,255,255,0.86);
      color: var(--ink);
      font: inherit;
    }

    input[type="range"] {
      padding: 0;
      accent-color: var(--accent);
      background: transparent;
      border: 0;
    }

    .range-label {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 0.92rem;
    }

    .range-value {
      min-width: 2ch;
      text-align: right;
      color: var(--ink);
      font-weight: 700;
    }

    .hint {
      margin-top: 12px;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.5;
    }

    .variant-meta {
      display: grid;
      gap: 10px;
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }

    .chips {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .chip {
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.84rem;
      font-weight: 600;
    }

    .version-strip {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }

    .version-card {
      border-radius: 18px;
      padding: 16px;
      background: var(--panel-strong);
      border: 1px solid rgba(255,255,255,0.7);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.45);
    }

    .version-card h3 {
      margin: 0 0 6px;
      font-size: 1rem;
    }

    .version-card p {
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.45;
    }

    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 16px;
    }

    .metric-card {
      background: rgba(255,255,255,0.78);
      border: 1px solid rgba(255,255,255,0.72);
      border-radius: 20px;
      box-shadow: var(--shadow);
      padding: 18px;
    }

    .metric-card header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
    }

    .metric-card header > div {
      min-width: 0;
    }

    .metric-card h2 {
      margin: 0;
      font-size: 1.12rem;
      line-height: 1.22;
      overflow-wrap: anywhere;
    }

    .metric-card .sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 0.84rem;
      overflow-wrap: anywhere;
      word-break: break-word;
    }

    .badge {
      padding: 6px 10px;
      border-radius: 999px;
      background: #f3f4f6;
      color: #475569;
      font-size: 0.78rem;
      font-weight: 700;
      white-space: normal;
      text-align: center;
      line-height: 1.25;
      max-width: 120px;
    }

    .direction {
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 0.83rem;
    }

    .swatch {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
      flex: 0 0 auto;
    }

    .chart-wrap {
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(248,250,252,0.96), rgba(241,245,249,0.86));
      border: 1px solid rgba(148, 163, 184, 0.18);
      overflow: hidden;
      min-height: 160px;
    }

    svg {
      width: 100%;
      height: auto;
      display: block;
    }

    .empty,
    .empty-metrics {
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.6;
      padding: 20px 2px 4px;
    }

    .footer-note {
      margin-top: 24px;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.6;
    }

    .metric-seed-note {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid rgba(148, 163, 184, 0.2);
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.55;
    }

    .metric-seed-label {
      margin-bottom: 8px;
    }

    .metric-seed-parts {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .metric-seed-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(241, 245, 249, 0.95);
      border: 1px solid rgba(148, 163, 184, 0.14);
    }

    .metric-seed-note strong {
      color: var(--ink);
    }

    @media (max-width: 1100px) {
      .layout {
        grid-template-columns: 1fr;
      }
      .sidebar {
        position: static;
      }
    }

    @media (max-width: 720px) {
      .version-strip {
        grid-template-columns: 1fr;
      }
      main {
        padding: 20px 14px 40px;
      }
      .hero {
        padding: 22px;
      }
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>Dashboard interactif des benchmarks</h1>
      <p>
        Cette page compare automatiquement <strong>v0.0.1</strong>, <strong>v0.0.2</strong>
        et <strong>v0.0.3</strong> pour un variant donne. Les selecteurs de gauche
        pilotent le choix du scenario et de la composition en robots, puis
        <strong>toutes les metriques</strong> du variant choisi sont affichees.
      </p>
    </section>

    <div class="layout">
      <aside class="panel sidebar">
        <h2 class="section-title">Parametres</h2>
        <div class="control-grid">
          <label>
            Scenario
            <select id="scenarioSelect"></select>
          </label>
          <label>
            <span class="range-label">
              <span>Robots verts</span>
              <span class="range-value" id="greenValue"></span>
            </span>
            <input id="greenRange" type="range">
          </label>
          <label>
            <span class="range-label">
              <span>Robots jaunes</span>
              <span class="range-value" id="yellowValue"></span>
            </span>
            <input id="yellowRange" type="range">
          </label>
          <label>
            <span class="range-label">
              <span>Robots rouges</span>
              <span class="range-value" id="redValue"></span>
            </span>
            <input id="redRange" type="range">
          </label>
        </div>

        <div class="variant-meta" id="variantMeta"></div>
      </aside>

      <section>
        <div class="version-strip" id="versionStrip"></div>
        <div class="metrics-grid" id="metricsGrid"></div>
        <p class="footer-note">
          Chaque graphique affiche 3 barres, une par version. La hauteur
          correspond a la moyenne sur les seeds disponibles et la barre de
          variation represente l'intervalle min-max. Si une metrique n'est pas
          definie pour certaines seeds, le compteur l'indique explicitement.
        </p>
      </section>
    </div>
  </main>

  <script>
    const DASHBOARD_DATA = __DATA__;

    const scenarioSelect = document.getElementById("scenarioSelect");
    const greenRange = document.getElementById("greenRange");
    const yellowRange = document.getElementById("yellowRange");
    const redRange = document.getElementById("redRange");
    const greenValue = document.getElementById("greenValue");
    const yellowValue = document.getElementById("yellowValue");
    const redValue = document.getElementById("redValue");
    const variantMeta = document.getElementById("variantMeta");
    const versionStrip = document.getElementById("versionStrip");
    const metricsGrid = document.getElementById("metricsGrid");

    const variantNames = Object.keys(DASHBOARD_DATA.variants);
    const variants = DASHBOARD_DATA.variants;
    const versionOrder = DASHBOARD_DATA.versions;

    function fillSelect(select, values, currentValue, formatter) {
      const current = String(currentValue ?? "");
      select.innerHTML = "";
      values.forEach((value) => {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = formatter ? formatter(value) : String(value);
        if (String(value) === current) {
          option.selected = true;
        }
        select.appendChild(option);
      });
    }

    function configureRange(input, output, values, currentValue) {
      const sortedValues = [...values].sort((a, b) => a - b);
      input.min = String(sortedValues[0]);
      input.max = String(sortedValues[sortedValues.length - 1]);
      input.step = "1";
      input.dataset.allowed = JSON.stringify(sortedValues);
      input.value = String(currentValue);
      output.textContent = String(currentValue);
    }

    function normalizeRangeValue(input, output) {
      const allowed = JSON.parse(input.dataset.allowed || "[]");
      const rawValue = Number(input.value);
      const nearest = allowed.reduce((best, candidate) => {
        if (best === null) {
          return candidate;
        }
        return Math.abs(candidate - rawValue) < Math.abs(best - rawValue) ? candidate : best;
      }, null);
      input.value = String(nearest);
      output.textContent = String(nearest);
      return nearest;
    }

    function scenarioLabel(name) {
      return name.replaceAll("_", " ");
    }

    function metricCategory(metric) {
      return DASHBOARD_DATA.metric_meta[metric]?.category || metric.split("/")[0];
    }

    function metricDirection(metric) {
      const value = DASHBOARD_DATA.metric_meta[metric]?.lower_is_better;
      if (value === true) return "Plus bas = meilleur";
      if (value === false) return "Plus haut = meilleur";
      return "Metrique descriptive";
    }

    function formatValue(metric, value) {
      if (value === null || value === undefined || Number.isNaN(value)) {
        return "n/a";
      }
      const style = DASHBOARD_DATA.metric_meta[metric]?.format || "float2";
      if (style === "percent") {
        return `${(value * 100).toFixed(1)} %`;
      }
      if (style === "int") {
        return String(Math.round(value));
      }
      if (style === "float3") {
        return value.toFixed(3);
      }
      return value.toFixed(2);
    }

    function stats(values) {
      if (!values.length) {
        return { mean: null, min: null, max: null, count: 0 };
      }
      const total = values.reduce((sum, current) => sum + current, 0);
      return {
        mean: total / values.length,
        min: Math.min(...values),
        max: Math.max(...values),
        count: values.length,
      };
    }

    function expectedSeedCount(variant, version) {
      const stableMetric =
        variant.versions[version]?.["efficiency/total_steps"] ||
        variant.versions[version]?.["completion/duration_sec"] ||
        [];
      if (stableMetric.length) {
        return stableMetric.length;
      }

      let maxCount = 0;
      Object.values(variant.versions[version] || {}).forEach((series) => {
        maxCount = Math.max(maxCount, series.length);
      });
      return maxCount;
    }

    function currentSelection() {
      return {
        scenario: scenarioSelect.value,
        green: Number(greenRange.value),
        yellow: Number(yellowRange.value),
        red: Number(redRange.value),
      };
    }

    function matchingVariants(filters) {
      return variantNames.filter((name) => {
        const meta = variants[name].meta;
        return (
          meta.scenario === filters.scenario &&
          meta.green === filters.green &&
          meta.yellow === filters.yellow &&
          meta.red === filters.red
        );
      });
    }

    function resolveVariant(filters) {
      const matching = matchingVariants(filters);
      if (matching.length) {
        return matching[0];
      }
      return variantNames.find((name) => variants[name].meta.scenario === filters.scenario) || variantNames[0];
    }

    function syncParamSelectsFromVariant(variantName) {
      const meta = variants[variantName].meta;
      scenarioSelect.value = meta.scenario;
      greenRange.value = String(meta.green);
      yellowRange.value = String(meta.yellow);
      redRange.value = String(meta.red);
      greenValue.textContent = String(meta.green);
      yellowValue.textContent = String(meta.yellow);
      redValue.textContent = String(meta.red);
    }

    function fillControlOptions(initialVariant) {
      fillSelect(
        scenarioSelect,
        DASHBOARD_DATA.scenarios,
        variants[initialVariant].meta.scenario,
        scenarioLabel
      );
      configureRange(greenRange, greenValue, DASHBOARD_DATA.robot_values.green, variants[initialVariant].meta.green);
      configureRange(yellowRange, yellowValue, DASHBOARD_DATA.robot_values.yellow, variants[initialVariant].meta.yellow);
      configureRange(redRange, redValue, DASHBOARD_DATA.robot_values.red, variants[initialVariant].meta.red);
    }

    function renderVariantMeta(variantName) {
      const meta = variants[variantName].meta;
      variantMeta.innerHTML = `
        <h2 class="section-title">Variant selectionne</h2>
        <div><strong>${meta.label}</strong></div>
        <div class="chips">
          <span class="chip">Scenario : ${scenarioLabel(meta.scenario)}</span>
          <span class="chip">g = ${meta.green}</span>
          <span class="chip">y = ${meta.yellow}</span>
          <span class="chip">r = ${meta.red}</span>
        </div>
        <div class="hint">Source des logs : <code>${DASHBOARD_DATA.generated_from}</code></div>
      `;
    }

    function renderVersionStrip() {
      versionStrip.innerHTML = versionOrder.map((version) => {
        const meta = DASHBOARD_DATA.version_meta[version];
        return `
          <article class="version-card">
            <h3><span class="swatch" style="background:${meta.color}"></span>${meta.label}</h3>
            <p>${meta.subtitle || ""}</p>
          </article>
        `;
      }).join("");
    }

    function chartSvg(metric, variant, seriesByVersion) {
      const width = 340;
      const height = 190;
      const left = 50;
      const right = 20;
      const top = 20;
      const bottom = 42;
      const innerWidth = width - left - right;
      const innerHeight = height - top - bottom;

      const summaries = versionOrder.map((version) => {
        const points = seriesByVersion[version] || [];
        const values = points.map((point) => point.value);
        return {
          version,
          color: DASHBOARD_DATA.version_meta[version].color,
          ...stats(values),
          expected: expectedSeedCount(variant, version),
        };
      }).filter((summary) => summary.count > 0);

      if (!summaries.length) {
        return `<div class="empty">Aucune valeur pour cette metrique sur ce variant.</div>`;
      }

      const maxValue = Math.max(...summaries.map((summary) => summary.max));
      const yMin = 0;
      const yMax = maxValue > 0 ? maxValue * 1.08 : 1;
      const ySpan = Math.max(1e-9, yMax - yMin);

      function x(index) {
        const slotWidth = innerWidth / Math.max(1, summaries.length);
        return left + slotWidth * index + slotWidth / 2;
      }

      function y(value) {
        return top + (1 - (value - yMin) / ySpan) * innerHeight;
      }

      const yTicks = [0, 0.5, 1].map((ratio) => {
        const value = yMin + ratio * ySpan;
        const yPos = y(value);
        return `
          <line x1="${left}" y1="${yPos}" x2="${width - right}" y2="${yPos}" stroke="rgba(148,163,184,0.18)" stroke-width="1" />
          <text x="${left - 8}" y="${yPos + 4}" text-anchor="end" font-size="11" fill="#64748b">${formatValue(metric, value)}</text>
        `;
      }).join("");

      const xTicks = summaries.map((summary, index) => {
        const xPos = x(index);
        return `
          <text x="${xPos}" y="${height - 10}" text-anchor="middle" font-size="11" fill="#64748b">${summary.version}</text>
        `;
      }).join("");

      const seriesMarkup = summaries.map((summary, index) => {
        const xPos = x(index);
        const slotWidth = innerWidth / Math.max(1, summaries.length);
        const barWidth = Math.min(56, slotWidth * 0.48);
        const meanY = y(summary.mean);
        const minY = y(summary.min);
        const maxY = y(summary.max);
        const baseY = y(0);
        const rectY = Math.min(meanY, baseY);
        const rectHeight = Math.max(1, Math.abs(baseY - meanY));

        return `
          <line x1="${xPos}" y1="${maxY}" x2="${xPos}" y2="${minY}" stroke="#334155" stroke-width="2.2" />
          <line x1="${xPos - 8}" y1="${maxY}" x2="${xPos + 8}" y2="${maxY}" stroke="#334155" stroke-width="2.2" />
          <line x1="${xPos - 8}" y1="${minY}" x2="${xPos + 8}" y2="${minY}" stroke="#334155" stroke-width="2.2" />
          <rect x="${xPos - barWidth / 2}" y="${rectY}" width="${barWidth}" height="${rectHeight}" rx="10" fill="${summary.color}" opacity="0.88">
            <title>${summary.version} | moyenne ${formatValue(metric, summary.mean)} | min ${formatValue(metric, summary.min)} | max ${formatValue(metric, summary.max)} | seeds ${summary.count}/${summary.expected}</title>
          </rect>
          <text x="${xPos}" y="${Math.max(meanY - 8, top + 12)}" text-anchor="middle" font-size="11" fill="#0f172a">${formatValue(metric, summary.mean)}</text>
        `;
      }).join("");

      return `
        <div class="chart-wrap">
          <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${metric}">
            ${yTicks}
            ${xTicks}
            <line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" stroke="rgba(71,85,105,0.45)" />
            <line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" stroke="rgba(71,85,105,0.45)" />
            ${seriesMarkup}
          </svg>
        </div>
      `;
    }

    function seedNoteMarkup(variant, seriesByVersion) {
      const parts = versionOrder.map((version) => {
        const count = (seriesByVersion[version] || []).length;
        const expected = expectedSeedCount(variant, version);
        return `<span class="metric-seed-chip"><strong>${version}</strong><span>${count}${expected ? ` / ${expected}` : ""}</span></span>`;
      });

      return `
        <div class="metric-seed-note">
          <div class="metric-seed-label">Seeds avec valeur pour cette metrique</div>
          <div class="metric-seed-parts">${parts.join("")}</div>
        </div>
      `;
    }

    function renderMetrics(variantName) {
      const variant = variants[variantName];

      const cards = DASHBOARD_DATA.metrics.map((metric) => {
        const seriesByVersion = {};
        let hasData = false;
        versionOrder.forEach((version) => {
          const series = variant.versions[version]?.[metric] || [];
          seriesByVersion[version] = series;
          if (series.length) {
            hasData = true;
          }
        });

        if (!hasData) {
          return "";
        }

        const metricMeta = DASHBOARD_DATA.metric_meta[metric] || {};
        return `
          <article class="metric-card">
            <header>
              <div>
                <h2>${metricMeta.label || metric}</h2>
                <div class="sub"><code>${metric}</code></div>
              </div>
              <span class="badge">${metricCategory(metric)}</span>
            </header>
            <p class="direction">${metricDirection(metric)}</p>
            ${chartSvg(metric, variant, seriesByVersion)}
            ${seedNoteMarkup(variant, seriesByVersion)}
          </article>
        `;
      }).filter(Boolean);

      metricsGrid.innerHTML = cards.length
        ? cards.join("")
        : `<div class="empty-metrics">Aucune metrique ne correspond au filtre courant.</div>`;
    }

    function updateFromVariant(variantName) {
      syncParamSelectsFromVariant(variantName);
      renderVariantMeta(variantName);
      renderMetrics(variantName);
    }

    function updateFromParams() {
      normalizeRangeValue(greenRange, greenValue);
      normalizeRangeValue(yellowRange, yellowValue);
      normalizeRangeValue(redRange, redValue);
      const selectedVariant = resolveVariant(currentSelection());
      updateFromVariant(selectedVariant);
    }

    function init() {
      const initialVariant = variantNames[0];
      fillControlOptions(initialVariant);
      renderVersionStrip();
      updateFromVariant(initialVariant);

      scenarioSelect.addEventListener("change", updateFromParams);
      greenRange.addEventListener("input", updateFromParams);
      yellowRange.addEventListener("input", updateFromParams);
      redRange.addEventListener("input", updateFromParams);
    }

    init();
  </script>
</body>
</html>
"""


def write_dashboard(payload: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = HTML_TEMPLATE.replace(
        "__DATA__",
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
    )
    output_path.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Genere un dashboard HTML a partir des logs TensorBoard."
    )
    parser.add_argument(
        "--logdir",
        type=Path,
        default=Path("tb_logs"),
        help="Dossier racine contenant un sous-dossier par variant.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/index.html"),
        help="Fichier HTML de sortie.",
    )
    args = parser.parse_args()

    if not args.logdir.exists():
        raise FileNotFoundError(f"Dossier de logs introuvable : {args.logdir}")

    payload = load_dashboard_data(args.logdir)
    write_dashboard(payload, args.output)

    print(f"Dashboard ecrit dans : {args.output.resolve()}")
    print(f"Variants : {len(payload['variants'])}")
    print(f"Metrics : {len(payload['metrics'])}")
    print(f"Versions : {', '.join(payload['versions'])}")


if __name__ == "__main__":
    main()
