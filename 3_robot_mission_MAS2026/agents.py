# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, cast

import mesa
import random

from objects import WasteAgent


class Robot(mesa.Agent, ABC):
    def __init__(self, model, color, allowed_waste_types, home_zone, deposit_zone, can_deposit, split_result):
        super().__init__(model)
        self.carrying  = []
        self.knowledge = {
            "timestep": 0,
            "position": None,
            "last_action": None,
            "map": {}
        }
        self.color = color
        self.allowed_waste_types = allowed_waste_types
        self.home_zone = home_zone
        self.max_zone = home_zone
        self.deposit_zone = deposit_zone
        self.can_deposit = can_deposit
        self.split_result = split_result


    @abstractmethod
    def deliberate(self) -> dict | None:
        pass

    def _current_pos(self):
        return cast(tuple[int, int], self.pos)

    def step_agent(self):
        current_pos = self._current_pos()
        model = cast(Any, self.model)

        percepts = model.get_local_percepts(current_pos)
        self.update_knowledge(percepts, None, current_pos)

        action = self.deliberate()

        new_percepts = model.do(self, action)
        self.update_knowledge(new_percepts, action, self._current_pos())

    def update_knowledge(self, percepts, action, position):
        self.knowledge["timestep"] += 1
        self.knowledge["position"] = position
        self.knowledge["last_action"] = action

        for pos, info in percepts.items():
            self.knowledge["map"][pos] = info

    def known_allowed_wastes(self):
        result = []
        for pos, info in self.knowledge["map"].items():
            if self.model.can_enter(self, pos):
                if any(w in self.allowed_waste_types for w in info["wastes"]):
                    result.append(pos)
        return result

    def closest_allowed_waste(self):
        candidates = self.known_allowed_wastes()
        current_pos = self._current_pos()
        return min(
            candidates,
            key=lambda pos: self.manhattan_distance(pos, current_pos),
            default=None
        )

    def step(self):
        self.step_agent()
    
    def manhattan_distance(self, pos1, pos2):
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
    
    def one_step_toward(self, target):
        current_pos = self._current_pos()

        dx = target[0] - current_pos[0]
        dy = target[1] - current_pos[1]

        candidates = []
        if dx != 0:
            candidates.append((1 if dx > 0 else -1, 0))
        if dy != 0:
            candidates.append((0, 1 if dy > 0 else -1))

        for step in candidates:
            next_pos = (current_pos[0] + step[0], current_pos[1] + step[1])
            if self.model.can_enter(self, next_pos):
                return step

        return None

    def closest_known_deposit_cell(self):
        current_pos = self._current_pos()

        if self.deposit_zone == 1:
            # Green agents deposit on WasteDisposalZone cells (zone 1, rightmost column)
            candidates = [
                pos for pos, info in self.knowledge["map"].items()
                if info.get("disposal")
            ]
        else:
            # Yellow/red agents deposit on border cells between their home zone and the lower zone
            candidates = [
                pos for pos, info in self.knowledge["map"].items()
                if info.get("zone") == self.deposit_zone
            ]

        if not candidates:
            return None

        return min(candidates, key=lambda pos: self.manhattan_distance(pos, current_pos))

    def random_safe_move(self):
        current_pos = self._current_pos()

        possible_steps = []
        for step in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            next_pos = (current_pos[0] + step[0], current_pos[1] + step[1])
            if self.model.can_enter(self, next_pos):
                possible_steps.append(step)

        if possible_steps:
            return {"name": "move", "direction": random.choice(possible_steps)}

        return None

class greenAgent(Robot):
    def __init__(self, model):
        super().__init__(model, "green", ["green"], 1, 1, True, False)

    def deliberate(self) -> dict | None:
        current_pos = self._current_pos()
        here = self.knowledge["map"].get(current_pos, {"wastes": [], "disposal": False})

        # Deposit if carrying and standing on a disposal cell
        if self.carrying and here.get("disposal"):
            return {"name": "deposit"}

        # Move toward known disposal cell if carrying
        if self.carrying:
            target = self.closest_known_deposit_cell()
            if target is not None:
                direction = self.one_step_toward(target)
                if direction is not None:
                    return {"name": "move", "direction": direction}

        # Pick up green waste if not full
        if "green" in here.get("wastes", []) and len(self.carrying) < 2:
            return {"name": "pick_up"}

        # Move toward known green waste
        target = self.closest_allowed_waste()
        if target is not None:
            direction = self.one_step_toward(target)
            if direction is not None:
                return {"name": "move", "direction": direction}

        return self.random_safe_move()


class yellowAgent(Robot):
    def __init__(self, model):
        super().__init__(model, "yellow", ["yellow"], 2, 1, False, "green")

    def deliberate(self) -> dict | None:
        current_pos = self._current_pos()
        model = cast(Any, self.model)
        here = self.knowledge["map"].get(current_pos, {})

        if self.carrying:
            if model.can_deposit_yellow(self, current_pos):
                return {"name": "deposit"}

            target = self.closest_known_deposit_cell()
            if target:
                direction = self.one_step_toward(target)
                if direction is not None:
                    return {"name": "move", "direction": direction}

        if "yellow" in here.get("wastes", []):
            return {"name": "pick_up"}

        target = self.closest_allowed_waste()
        if target:
            direction = self.one_step_toward(target)
            if direction is not None:
                return {"name": "move", "direction": direction}

        return self.random_safe_move()

class redAgent(Robot):
    def __init__(self, model):
        super().__init__(model, "red", ["red"], 3, 2, False, "yellow")

    def deliberate(self) -> dict | None:
        current_pos = self._current_pos()
        model = cast(Any, self.model)
        here = self.knowledge["map"].get(current_pos, {})

        if self.carrying:
            if model.can_deposit_red(self, current_pos):
                return {"name": "deposit"}

            target = self.closest_known_deposit_cell()
            if target:
                direction = self.one_step_toward(target)
                if direction is not None:
                    return {"name": "move", "direction": direction}

        if "red" in here.get("wastes", []):
            return {"name": "pick_up"}

        target = self.closest_allowed_waste()
        if target:
            direction = self.one_step_toward(target)
            if direction is not None:
                return {"name": "move", "direction": direction}

        return self.random_safe_move()