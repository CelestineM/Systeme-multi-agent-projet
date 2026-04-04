from typing import Any, cast

from .communication import LocalKnowledgeSharing, NoKnowledgeSharing, SmartColorKnowledgeSharing
from .navigation import AStarFrontierNavigator, NaiveNavigator


class DecisionPolicy:
    def __init__(self, navigator, communication):
        self.navigator = navigator
        self.communication = communication

    def deliberate(self, robot) -> list[dict]:
        """
        Retourne une liste ordonnée d'actions pour ce tick :
          1. Actions de communication (share/read) — budgétées séparément
          2. Une action physique (move / pickup / deposit)
          3. Actions send_message issues de on_discover — budgétées séparément
        Les actions send_message issues de pickup/deposit sont ajoutées dans
        robot._execute() directement après l'exécution physique.
        """
        actions = []

        # 1. Communication entrante + sync locale
        actions.extend(self.communication.share(robot))

        # 2. Décision physique
        physical = self._decide(robot)
        if physical:
            actions.append(physical)

        return actions

    def _decide(self, robot) -> dict | None:
        current_pos = robot._current_pos()
        model = cast(Any, robot.model)
        here = robot.knowledge.map.get(
            current_pos,
            {"wastes": [], "disposal": False, "zone": None, "timestamp": -1},
        )

        can_deposit_now = (
            (robot.color == "green" and here.get("disposal"))
            or (robot.color == "yellow" and model.can_deposit_yellow(robot, current_pos))
            or (robot.color == "red" and model.can_deposit_red(robot, current_pos))
        )

        if robot.carrying and can_deposit_now:
            return {"name": "deposit", "waste_color": robot.carrying[0] if robot.carrying else None}

        if len(robot.carrying) >= robot.max_carry:
            target = robot.closest_known_deposit_cell()
            if target is not None:
                direction = self.navigator.step_toward(robot, target)
                if direction is not None:
                    return {"name": "move", "direction": direction}
            return self.navigator.exploration_move(robot)

        if robot.color in here.get("wastes", []):
            return {"name": "pickup", "waste_color": robot.color}

        target = robot.closest_allowed_waste()
        if target is not None:
            direction = self.navigator.step_toward(robot, target)
            if direction is not None:
                return {"name": "move", "direction": direction}

        if robot.carrying:
            target = robot.closest_known_deposit_cell()
            if target is not None:
                direction = self.navigator.step_toward(robot, target)
                if direction is not None:
                    return {"name": "move", "direction": direction}

        return self.navigator.exploration_move(robot)


def build_behavior(version: str):
    if version == "v0.0.1":
        return DecisionPolicy(NaiveNavigator(), NoKnowledgeSharing())
    if version == "v0.0.2":
        return DecisionPolicy(NaiveNavigator(), LocalKnowledgeSharing())
    if version == "v0.0.3":
        return DecisionPolicy(AStarFrontierNavigator(), SmartColorKnowledgeSharing())
    raise ValueError(f"Version inconnue : {version}. Disponibles : ['v0.0.1', 'v0.0.2', 'v0.0.3']")