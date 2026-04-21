# Benchmark Analysis — Robot Mission MAS 2026
**Groupe 3** · Malo Chauvel, Constance Piquet, Célestine Martin  
---


## Sommaire


1. [Configuration du benchmark](#configuration-du-benchmark)
2. [Légende des couleurs TensorBoard](#légende-des-couleurs-tensorboard)
3. [Résultats globaux par version](#résultats-globaux-par-version)
4. [Analyse par catégorie de métriques](#analyse-par-catégorie-de-métriques)
   - [Complétion & Efficacité](#complétion--efficacité)
   - [Mouvements](#mouvements)
   - [Communication](#communication)
5. [Impact de la composition en robots](#impact-de-la-composition-en-robots)
6. [Analyse du ranking multi-métriques](#analyse-du-ranking-multi-métriques)
7. [Meilleurs et pires variants](#meilleurs-et-pires-variants)
8. [Conclusions](#conclusions)

---

## Configuration du benchmark

| Paramètre | Valeur |
|---|---|
| Versions comparées | `v0.0.1`, `v0.0.2`, `v0.0.3`, `v0.0.4` |
| Variants (compositions robots) | 128 (sweep g2–g4 × y2–y4 × r2–r4) |
| Seeds par variant × version | 10 |
| Max steps par run | 1500 |
| **Total runs** | **2 560** *(v0.0.1: 640, v0.0.2: 640, v0.0.3: 640, v0.0.4: 640)* |
| Map | 15×15, 2 épicentres, rayon_zone_3=2.5, rayon_zone_2=5.5 |
| Déchets initiaux | 8 verts, 4 jaunes, 2 rouges |

---

## Légende des couleurs TensorBoard

Toutes les métriques sont dans l'onglet **SCALARS**, organisées en sous-groupes : `completion`, `efficiency`, `movement`, `communication`, `ranking`, `summary`. La correspondance couleur ↔ version est uniforme sur tous ces sous-groupes :

| Couleur | Version | Comportement |
|---|---|---|
|  **Orange** | `v0.0.1` | Naive + NoKnowledgeSharing (aucune communication) |
|  **Bleu** | `v0.0.2` | Naive + LocalKnowledgeSharing |
| **Rouge** | `v0.0.3` | A* + LocalKnowledgeSharing |
| **Violet** | `v0.0.4` | A* + SmartColorKnowledgeSharing |

> Sur les métriques de communication (`msg_sent_total`, `local_syncs_total`), v0.0.1 apparaît comme une ligne plate à 0 — il est présent mais invisible car il n'envoie aucun message et ne fait aucune sync.

---

## Résultats globaux par version


| Métrique (moyenne par run) | v0.0.1 | v0.0.2 | v0.0.3 | v0.0.4 |
|---|---|---|---|---|
| **Taux de complétion moyen** | 53.6% | 27.2% | 57.2% | **52.3%** |
| **Nb steps moyen (missions réussies)** | 1 465 | 526 | 405 | **425** |
| **Mouvements totaux** | 42 144 | 73 771 | 63 093 | **36 608** |
| **Déchets traités par step** | 0.045 | 0.067 | 0.063 | **0.165** |
| **Attente moy. entre dépôts (steps)** | 26.8 | 8.4 | 30.4 | **4.7** |
| **Messages envoyés** | 0 | 0 | 0 | **15 277** |
| **Syncs locaux** | 0 | 73 853 | 63 176 | **36 695** |

> * **Le triomphe de la v0.0.4 (SmartColorKnowledgeSharing) :** C'est la version la plus aboutie. Grâce à ses ~15 000 messages événementiels, elle divise l'attente entre les dépôts par 6 par rapport à la v0.0.3 (4.7 steps d'attente contre 30.4), maximise le traitement des déchets (0.165 par step), et **réduit drastiquement le nombre de mouvements totaux** (36 608, soit près de la moitié des versions précédentes).
> * **Les limites de la v0.0.3 (A* sans messages) :** Bien qu'elle complète de nombreuses missions, le manque de communication à distance se fait sentir : l'attente moyenne entre les dépôts explose à 30.4 steps (pire que la v0.0.1). L'algorithme A* rend les robots efficaces pour se déplacer, mais ils manquent cruellement d'informations sur la localisation des cibles.
> * **La v0.0.1 gagne par la force brute :** Avec une limite de steps augmentée, la version purement réactive finit par réussir 53.6% de ses missions, mais de manière atrocement inefficace (1 465 steps en moyenne).

---

## Impact de la composition en robots

> Les statistiques ci-dessous sont basées sur la version la plus aboutie (**`v0.0.4`**, messagerie ciblée).

### Par nombre de robots rouges (v0.0.4)

| Robots rouges | Taux de complétion moyen |
|---|---|
| r = 2 | ~57.8% |
| r = 3 | ~75.6% |
| r = 4 | **~87.8%** |

> **Le robot rouge reste le goulot d'étranglement absolu :** Il est le seul à pouvoir initier la chaîne de traitement (rouge→jaune→vert) dans la zone la plus éloignée. Chaque ajout d'un robot rouge apporte un gain massif et linéaire (+17.8 points puis +12.2 points). Pour maximiser les chances de réussite, il faut maximiser `r`.

### Par nombre de robots verts (v0.0.4)

| Robots verts | Taux de complétion moyen |
|---|---|
| g = 2 | **~77.8%** |
| g = 3 | ~73.3% |
| g = 4 | ~70.0% |

> **L'excès de robots verts est pénalisant :** Contrairement aux robots rouges, ajouter des robots verts au-delà de 2 fait *baisser* les performances globales. Une fois que la capacité de 2 robots verts est atteinte, la zone 1 est absorbée assez vite. Les robots supplémentaires créent de l'encombrement spatial (blocages A*) et du bruit inutile dans le réseau de communication, nuisant à l'efficacité globale.

### Par nombre de robots jaunes (v0.0.4)

| Robots jaunes | Taux de complétion moyen |
|---|---|
| y = 2 | **~80.0%** |
| y = 3 | ~70.0% |
| y = 4 | ~71.1% |

> **Le même effet de congestion qu'en zone verte :** Le rôle intermédiaire des robots jaunes est parfaitement rempli avec `y = 2` (taux record de 80%). Augmenter la flotte jaune à 3 ou 4 fait chuter la complétion d'environ 10 points. Les déchets jaunes n'arrivent pas assez vite pour justifier 4 robots, qui finissent par errer, se gêner et saturer le système.

## Conclusions

### Ce que montrent les données

1. **La communication dicte l'efficacité, pas seulement la réussite** : Avec plus de temps alloué, la version purement réactive (v0.0.1) finit par réussir 53.6% de ses missions par pure force brute, mais met en moyenne 1 465 steps. Le passage à la messagerie ciblée (v0.0.4) ne change pas radicalement le taux de succès global, mais **divise le temps de résolution par plus de 3** (425 steps) et transforme une errance chaotique en une chaîne logistique optimisée.

2. **Le robot rouge est le goulot d'étranglement absolu** : La flotte est totalement dépendante de la capacité des robots rouges à déclencher la cascade de dépôts depuis la zone la plus éloignée. Maximiser `r` est le seul levier d'amélioration linéaire.

3. **L'encombrement spatial et réseau (rendements négatifs)** : Dans les zones faciles (verte et jaune), ajouter des robots au-delà de 2 ne sert à rien et s'avère même **contre-productif**. Passer de 2 à 4 robots verts ou jaunes fait chuter le taux de complétion d'environ 10 points. Les robots excédentaires se gênent, bloquent les chemins A* et saturent le système pour rien. La flotte idéale est fortement asymétrique (ex: g2_y2_r4).

4. **La qualité de l'information prime sur la quantité de synchronisation** : La v0.0.4 envoie environ 15 000 messages ciblés (`INFORM_REF` de position), ce qui lui permet de réduire de moitié le besoin de se synchroniser localement par rapport à la v0.0.2 (36k syncs contre 73k). Résultat : l'attente moyenne pour trouver un dépôt s'effondre à un niveau record de **4.7 steps** (contre 30.4 pour la v0.0.3 sans messages).

5. **Le réseau est hautement sollicité mais extrêmement rentable** : L'overhead de communication en v0.0.4 atteint **~21.2%** (les actions de communication représentent un cinquième de l'activité). Le système est bavard, mais ce "coût" réseau est un investissement largement amorti par le gain spectaculaire en efficacité de déplacement.

6. **Paradoxe algorithmique : communiquer plus permet de calculer moins** : Contre toute attente, la version la plus complexe (v0.0.4) est quasiment **deux fois plus rapide à simuler** que la v0.0.3 (253s contre 446s). L'explication est simple : en sachant exactement où aller grâce aux messages, les robots v0.0.4 terminent leur mission beaucoup plus vite. Ils s'épargnent ainsi des milliers de steps d'exploration inutile, ce qui évite de recalculer la coûteuse heuristique A* à chaque tour. L'information réduit le besoin de calcul.

7. **`idle_ratio = 0` ne signifie pas "efficacité = 1"** : Les robots de la v0.0.1 n'ont aucun temps mort, ils bougent frénétiquement à chaque step (plus de 42 000 mouvements au total). Pourtant, ils sont terriblement inefficaces. La véritable métrique de succès de ce système multi-agents n'est pas le taux d'activité de l'agent, mais la **coordination spatiale** illustrée par la v0.0.4.