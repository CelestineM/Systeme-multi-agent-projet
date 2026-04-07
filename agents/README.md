# Agents

Ce dossier contient la logique robotique modularisée, qui répartit les responsabilités entre des stratégies dédiées à la connaissance, à la navigation, à la communication et à la prise de décision.

## Structure des composants

- `knowledge.py` : mémoire de carte locale, perception spatiale et logique de fusion des cartes.
- `navigation.py` : exécution des mouvements et stratégies d'exploration.
- `communication.py` : politiques de communication modulaires contrôlant la manière dont les robots partagent les informations.
- `policy.py` : délibération de haut niveau mappant les croyances aux actions physiques, et logique de construction pour les versions.
- `robot.py` : classe de base `Robot` contenant l'état de l'agent, et agents concrets `Green`, `Yellow` et `Red`.

## Mise en œuvre globale

Quelle que soit la version, tous les agents fonctionnent selon un cycle logique unifié, étape par étape, défini dans `robot.py` :

1. **Perception** : le robot observe son environnement immédiat et met à jour sa mémoire interne.
2. **Discovery Hooks** : le robot génère des intentions de communication budgétisées (`on_discover`) s'il détecte une cible d'intérêt.
3. **Délibération** : La `DecisionPolicy` analyse l'état de croyance du robot pour produire une liste d'intentions ordonnée. Celle-ci comprend généralement la lecture des messages entrants (`read_messages`), les synchronisations d'état libres (`sync_neighbors`) et une seule intention physique logique (par exemple, `move` vers une cible, `pickup`, `deposit` ou explorer).
4. **Exécution** : Le robot épuise son budget de messages (le cas échéant) et exécute son déplacement physique dans l'environnement.
5. **Diffusion d'événements post-action** : Si un `pickup` ou un `deposit` aboutit physiquement, cela déclenche des hooks de communication spécifiques (`on_pickup` ou `on_deposit`) pour diffuser ces événements du cycle de vie aux pairs concernés sur la carte avant la fin du tour.


## Versions spécifiques d'agents

L'intelligence de l'agent est définie par la combinaison de ses politiques de navigation et de communication. Celles-ci sont regroupées en trois versions distinctes créées via `build_behavior` (dans `policy.py`) :

### Version 0.0.1 (Référence isolée)
- **Navigation** : `NaiveNavigator` — exploration aléatoire et ciblage direct par ligne de mire.
- **Communication** : `NoKnowledgeSharing` — les robots opèrent de manière totalement isolée, ne conservant que ce qu'ils voient personnellement.

### Version 0.0.2 (Consensus local)
- **Navigation** : `NaiveNavigator` — exploration aléatoire identique à celle de la v0.0.1.
- **Communication** : `LocalKnowledgeSharing` — les robots synchronisent silencieusement leurs cartes internes avec leurs voisins immédiats (rayon = 1). Il s'agit d'une fusion locale « gratuite » qui contourne le budget de messages.

### Version 0.0.3 (Intelligente et optimale)

Cette version introduit une logique déterministe avancée tant pour le déplacement que pour l'interaction, améliorant considérablement l'efficacité par rapport aux déplacements aléatoires et réduisant au minimum la charge de communication.

#### Navigation : `A* + Frontier Navigator`
- **Théorie** : 
  - **Ciblage** : pour se diriger vers un objectif explicite, l'algorithme de recherche de chemin A* garantit un itinéraire optimal en évaluant à la fois la distance parcourue et une heuristique (distance de Manhattan) par rapport à l'objectif, en contournant de manière fluide les obstacles connus.
  - **Exploration** : Au lieu de se déplacer à l'aveuglette, l'agent maintient une carte cognitive et identifie la « frontière » — les limites exactes séparant les cellules explorées des cellules inexplorées. En déterminant mathématiquement le bloc frontalier le plus proche et en s'y rendant directement, le robot explore de manière systématique, éliminant ainsi les traversées redondantes au-dessus d'espaces vides connus.
- **Implémentation** : 
  - `step_toward` utilise un algorithme A* basé sur `heapq` sur l'ensemble de `robot.knowledge.map`. 
  - `exploration_move` analyse la carte cognitive pour construire une liste de `frontier_cells` (cellules connues adjacentes à des coordonnées qui ne figurent pas encore dans les clés de la carte). Il effectue ensuite une recherche en largeur (`shortest_path_distance`) pour sélectionner la frontière la plus proche, puis réinjecte cette coordonnée dans l'algorithme A* pour tracer le chemin.

#### Communication : `SmartColorKnowledgeSharing`
- **Théorie** : Une politique hybride combinant un consensus local libre avec un modèle à budget limité et piloté par les événements (analogue au modèle publication/abonnement), strictement aligné sur les règles du cycle de vie des déchets. Elle empêche la saturation du réseau en limitant strictement l'accès à l'information aux seuls acteurs qui ont un « besoin d'en connaître ».
- **Mise en œuvre** : 
  - Au début de la délibération, les robots effectuent une opération `sync_neighbors` libre (rayon = 1) pour fusionner les dictionnaires de cartes locales sans consommer le budget de messages. 
  - Lors du traitement des messages, l'étape `read_messages` itère spécifiquement jusqu'à la limite du `read_budget`. 
  - Les messages sont strictement formatés via des charges utiles `MessagePerformative.INFORM_REF` décrivant les types d'événements (`discover`, `pickup`, `deposit`).
  - **Découverte locale** : Déclenchée via `on_discover`. Parcourt les déchets visibles. Les messages ne sont envoyés *que* si la couleur du voisin lui permet d'agir sur ce déchet spécifique.(i.e. un déchet vert découvert par un robot jaune est envoyés aux robots verts uniquement)
  - **Ramassage global** : déclenché via `on_pickup`. Informe *tous* les robots du réseau (`_get_all_robots`), mais filtre strictement la diffusion aux robots correspondant à la couleur du déchet ramassé, leur demandant d'invalider la cible de leur base de connaissances pour éviter tout déplacement inutile.
  - **Dépôt en chaîne** : déclenché via `on_deposit`. Lorsqu'un déchet est éliminé (par exemple, un déchet rouge devient jaune lors du dépôt), le système consulte un dictionnaire de mappage `NEXT_COLOR` et informe *tous les robots* du niveau de couleur émergent (par exemple, les agents rouges informent les jaunes, les jaunes informent les verts) pour lancer la phase suivante du pipeline.