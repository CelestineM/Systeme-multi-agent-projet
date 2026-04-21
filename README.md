# Systeme multi-agent - Robot Mission MAS 2026

Ce depot contient la simulation, le pipeline de benchmark et l'analyse des versions `v0.0.1`, `v0.0.2`, `v0.0.3` et `v0.0.4`.

## Dashboard interactif

Le README GitHub ne peut pas executer une vraie interface dynamique.  
Le projet genere donc une page HTML autonome a partir des logs TensorBoard :

```bash
pip install -r requirements.txt
python3 generate_benchmark_dashboard.py --report benchmark_outputs/benchmark_report.json --output docs/index.html
```

Ouvre ensuite `docs/index.html` localement, ou publie `docs/` avec GitHub Pages.

Cette interface permet de :

- choisir le scenario et les parametres `g / y / r`,
- comparer automatiquement les quatre versions sur le variant correspondant,
- afficher toutes les metriques disponibles pour le variant choisi.

## Lancer les benchmarks

Benchmark complet (toutes les versions configurees) :

```bash
python3 benchmark_pipeline.py --config benchmark_config.example.json --output-dir benchmark_outputs
```

Benchmark d'une seule version sans ecraser les resultats existants :

```bash
python3 benchmark_pipeline.py --config benchmark_config.example.json --output-dir benchmark_outputs --version v0.0.4 --append-existing
```

Fusionner tous les `benchmark_report*.json` existants dans `benchmark_outputs/` :

```bash
python3 benchmark_pipeline.py --output-dir benchmark_outputs --merge-only --merge-pattern "benchmark_report*.json"
```

Regenerer ensuite le dashboard :

```bash
python3 generate_benchmark_dashboard.py --report benchmark_outputs/benchmark_report.json --output docs/index.html
```

## Analyse detaillee

Le rapport d'analyse statique est disponible dans [README_ANALYSE_RESULTATS.md](README_ANALYSE_RESULTATS.md).
