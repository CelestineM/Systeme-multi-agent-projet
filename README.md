# Systeme multi-agent - Robot Mission MAS 2026

Ce depot contient la simulation, le pipeline de benchmark et l'analyse des versions `v0.0.1`, `v0.0.2` et `v0.0.3`.

## Dashboard interactif

Le README GitHub ne peut pas executer une vraie interface dynamique.  
Le projet genere donc une page HTML autonome a partir des logs TensorBoard :

```bash
pip install -r requirements.txt
python3 generate_benchmark_dashboard.py --logdir tb_logs --output docs/index.html
```

Ouvre ensuite `docs/index.html` localement, ou publie `docs/` avec GitHub Pages.

Cette interface permet de :

- choisir le scenario et les parametres `g / y / r`,
- comparer automatiquement les trois versions sur le variant correspondant,
- afficher toutes les metriques disponibles pour le variant choisi.

## Analyse detaillee

Le rapport d'analyse statique est disponible dans [README_ANALYSE_RESULTATS.md](README_ANALYSE_RESULTATS.md).
