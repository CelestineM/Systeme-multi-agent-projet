# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Optional, cast

from communication.agent.CommunicatingAgent import CommunicatingAgent
from communication.message.Message import Message
from communication.message.MessagePerformative import MessagePerformative

import mesa
import random

from objects import WasteAgent

def on_deposit_silent(robot):
    pass

def on_deposit_broadcast(robot):
    model = cast(Any, robot.model)

    if robot.color == "yellow":
        target_zone_color = "green"
    elif robot.color == "red":
        target_zone_color = "yellow"
    else:
        return

    deposited_count = len(robot.carrying)
    produced_color = robot.split_result      # "green" si yellow, "yellow" si red
    produced_count = deposited_count * 2

    content = {
        "position": robot._current_pos(),
        "produced_color": produced_color,
        "produced_count": produced_count,
        "timestep": robot.knowledge["timestep"],
    }

    for agent in model.agents:
        if hasattr(agent, "color") and agent.color == target_zone_color:
            message = Message(
                robot.get_name(),
                agent.get_name(),
                MessagePerformative.INFORM_REF,
                content
            )
            robot.send_message(message)

VERSIONS = {
    "v0.0.1": {
        "on_deposit":  on_deposit_silent,
    },
    "v0.1.0": {
        "on_deposit":  on_deposit_broadcast,
    }
}

class Robot(mesa.Agent, ABC, CommunicatingAgent):
    def __init__(self, model, color, allowed_waste_types, home_zone, deposit_zone, can_deposit, split_result, max_carry, version: Optional[str] = None):
        mesa.Agent.__init__(self, model)
        CommunicatingAgent.__init__(self, model, f"{color}_{self.unique_id}")
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
        self.max_carry = max_carry


    @abstractmethod
    def deliberate(self) -> dict | None:
        pass

    def _current_pos(self):
        return cast(tuple[int, int], self.pos)

    def step_agent(self):
        current_pos = self._current_pos()
        model = cast(Any, self.model)
        self.knowledge["timestep"] += 1

        self.process_messages()  

        percepts = model.get_local_percepts(current_pos)
        self.update_knowledge(percepts, None, current_pos)

        action = self.deliberate()
        new_percepts = model.do(self, action)
        self.update_knowledge(new_percepts, action, self._current_pos())

    def update_knowledge(self, percepts, action, position):
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
    
    def process_messages(self):
        for message in self.get_new_messages():
            if message.get_performative() == MessagePerformative.INFORM_REF:
                content = message.get_content()
                pos = content["position"]
                produced_color = content["produced_color"]
                produced_count = content["produced_count"]

                existing = self.knowledge["map"].get(pos, {"wastes": []})
                updated_wastes = existing["wastes"] + [produced_color] * produced_count

                self.knowledge["map"][pos] = {
                    **existing,
                    "wastes": updated_wastes,
                }

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
            candidates = [
                pos for pos, info in self.knowledge["map"].items()
                if info.get("disposal")
            ]
        else:
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
    

class VersionedRobot(Robot):
    def __init__(self, model, color, allowed_waste_types, home_zone, deposit_zone, can_deposit, split_result, max_carry, version: Optional[str] = None):
        super().__init__(model, color, allowed_waste_types, home_zone, deposit_zone, can_deposit, split_result, max_carry)
        self.set_version(version)

    def set_version(self, version):
        self.version = version
        self._config  = VERSIONS[version]

    def on_deposit(self):
        return self._config["on_deposit"](self)

    def deliberate(self) -> dict | None:
        current_pos = self._current_pos()
        model = cast(Any, self.model)
        here = self.knowledge["map"].get(current_pos, {"wastes": [], "disposal": False})

        can_deposit_now = (
            (self.color == "green"  and here.get("disposal")) or
            (self.color == "yellow" and model.can_deposit_yellow(self, current_pos)) or
            (self.color == "red"    and model.can_deposit_red(self, current_pos))
        )

        if self.carrying and can_deposit_now:
            self.on_deposit()
            return {"name": "deposit"}

        if len(self.carrying) >= self.max_carry:
            target = self.closest_known_deposit_cell()
            if target is not None:
                direction = self.one_step_toward(target)
                if direction is not None:
                    return {"name": "move", "direction": direction}
            return self.random_safe_move()

        if self.color in here.get("wastes", []):
            return {"name": "pick_up"}

        target = self.closest_allowed_waste()
        if target is not None:
            direction = self.one_step_toward(target)
            if direction is not None:
                return {"name": "move", "direction": direction}

        if self.carrying:
            target = self.closest_known_deposit_cell()
            if target is not None:
                direction = self.one_step_toward(target)
                if direction is not None:
                    return {"name": "move", "direction": direction}

        return self.random_safe_move()

class greenAgent(VersionedRobot):
    def __init__(self, model, version: Optional[str] = None):
        super().__init__(model, "green", ["green"], 1, 1, True, False, 2, version=version)

class yellowAgent(VersionedRobot):
    def __init__(self, model, version: Optional[str] = None):
        super().__init__(model, "yellow", ["yellow"], 2, 1, False, "green", 2, version=version)

class redAgent(VersionedRobot):
    def __init__(self, model, version: Optional[str] = None):
        super().__init__(model, "red", ["red"], 3, 2, False, "yellow", 2, version=version)
