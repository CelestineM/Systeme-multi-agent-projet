from abc import ABC
from typing import Any, Optional, cast
import heapq
import random

import mesa


# ─── Knowledge ───────────────────────────────────────────────────────────────

class RobotKnowledge:
    def __init__(self):
        self.timestep = 0
        self.position = None
        self.last_action = None
        self.map: dict[tuple[int, int], dict[str, Any]] = {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestep": self.timestep,
            "position": self.position,
            "last_action": self.last_action,
            "map": self.map,
        }

    def update_from_percepts(self, percepts, action, position):
        self.timestep += 1
        self.position = position
        self.last_action = action
        current_time = self.timestep

        for pos, info in percepts.items():
            old_info = self.map.get(pos)
            new_info = {
                "zone": info["zone"],
                "wastes": list(info["wastes"]),
                "disposal": info["disposal"],
                "timestamp": current_time,
            }
            if old_info is None or old_info.get("timestamp", -1) <= current_time:
                self.map[pos] = new_info

    def merge_shared_map(self, other_map):
        for pos, info in other_map.items():
            other_ts = info.get("timestamp", -1)
            my_info = self.map.get(pos)
            my_ts = my_info.get("timestamp", -1) if my_info else -1

            if my_info is None or other_ts > my_ts:
                self.map[pos] = {
                    "zone": info["zone"],
                    "wastes": list(info["wastes"]),
                    "disposal": info["disposal"],
                    "timestamp": other_ts,
                }


# ─── Navigation ──────────────────────────────────────────────────────────────

class NaiveNavigator:
    def step_toward(self, robot, target):
        current_pos = robot._current_pos()
        dx = target[0] - current_pos[0]
        dy = target[1] - current_pos[1]
        candidates = []

        if dx != 0:
            candidates.append((1 if dx > 0 else -1, 0))
        if dy != 0:
            candidates.append((0, 1 if dy > 0 else -1))

        for step in candidates:
            next_pos = (current_pos[0] + step[0], current_pos[1] + step[1])
            if robot.model.can_enter(robot, next_pos):
                return step
        return None

    def exploration_move(self, robot):
        current_pos = robot._current_pos()
        possible_steps = [
            step for step in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if robot.model.can_enter(robot, (current_pos[0] + step[0], current_pos[1] + step[1]))
        ]
        return {"name": "move", "direction": random.choice(possible_steps)} if possible_steps else None


class AStarFrontierNavigator:
    def step_toward(self, robot, target):
        start = robot._current_pos()
        if start == target:
            return None

        def heuristic(pos):
            return abs(pos[0] - target[0]) + abs(pos[1] - target[1])

        open_heap = []
        heapq.heappush(open_heap, (heuristic(start), 0, start))

        came_from = {start: None}
        g_score = {start: 0}

        while open_heap:
            _, current_g, current = heapq.heappop(open_heap)
            if current == target:
                break

            x, y = current
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nxt = (x + dx, y + dy)
                if not robot.model.can_enter(robot, nxt):
                    continue

                tentative_g = current_g + 1
                if nxt not in g_score or tentative_g < g_score[nxt]:
                    g_score[nxt] = tentative_g
                    f_score = tentative_g + heuristic(nxt)
                    heapq.heappush(open_heap, (f_score, tentative_g, nxt))
                    came_from[nxt] = current

        if target not in came_from:
            return None

        current = target
        while came_from[current] != start:
            current = came_from[current]
            if current is None:
                return None

        dx = current[0] - start[0]
        dy = current[1] - start[1]
        return (dx, dy)

    def frontier_cells(self, robot):
        frontier = []
        for pos in robot.knowledge.map:
            if not robot.model.can_enter(robot, pos):
                continue

            x, y = pos
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                npos = (x + dx, y + dy)
                if npos not in robot.knowledge.map:
                    frontier.append(pos)
                    break
        return frontier

    def closest_frontier(self, robot):
        current_pos = robot._current_pos()
        frontiers = self.frontier_cells(robot)
        if not frontiers:
            return None
        return min(frontiers, key=lambda pos: robot.manhattan_distance(pos, current_pos))

    def exploration_move(self, robot):
        target = self.closest_frontier(robot)
        if target is not None:
            step = self.step_toward(robot, target)
            if step is not None:
                return {"name": "move", "direction": step}
        return NaiveNavigator().exploration_move(robot)


# ─── Communication ───────────────────────────────────────────────────────────

class NoKnowledgeSharing:
    def share(self, robot):
        return None


class LocalKnowledgeSharing:
    def share(self, robot):
        current_pos = robot._current_pos()
        neighbors = robot.model.grid.get_neighbors(
            current_pos, moore=False, include_center=True, radius=1
        )
        for other in neighbors:
            if other is robot or not isinstance(other, Robot):
                continue
            robot.knowledge.merge_shared_map(other.knowledge.map)


# ─── Decision policy ─────────────────────────────────────────────────────────

class DecisionPolicy:
    def __init__(self, navigator, communication):
        self.navigator = navigator
        self.communication = communication

    def deliberate(self, robot) -> dict | None:
        self.communication.share(robot)

        current_pos = robot._current_pos()
        model = cast(Any, robot.model)
        here = robot.knowledge.map.get(
            current_pos,
            {"wastes": [], "disposal": False, "zone": None, "timestamp": -1},
        )

        can_deposit_now = (
            (robot.color == "green" and here.get("disposal")) or
            (robot.color == "yellow" and model.can_deposit_yellow(robot, current_pos)) or
            (robot.color == "red" and model.can_deposit_red(robot, current_pos))
        )

        if robot.carrying and can_deposit_now:
            return {"name": "deposit"}

        if len(robot.carrying) >= robot.max_carry:
            target = robot.closest_known_deposit_cell()
            if target is not None:
                direction = self.navigator.step_toward(robot, target)
                if direction is not None:
                    return {"name": "move", "direction": direction}
            return self.navigator.exploration_move(robot)

        if robot.color in here.get("wastes", []):
            return {"name": "pick_up"}

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


# ─── Version builder ─────────────────────────────────────────────────────────

def build_behavior(version: str):
    if version == "v0.0.1":
        return DecisionPolicy(NaiveNavigator(), NoKnowledgeSharing())
    if version == "v0.0.2":
        return DecisionPolicy(NaiveNavigator(), LocalKnowledgeSharing())
    if version == "v0.0.3":
        return DecisionPolicy(AStarFrontierNavigator(), LocalKnowledgeSharing())
    raise ValueError(f"Version inconnue : {version}. Disponibles : ['v0.0.1', 'v0.0.2', 'v0.0.3']")


# ─── Robot base ──────────────────────────────────────────────────────────────

class Robot(mesa.Agent, ABC):
    def __init__(self, model, color, allowed_waste_types, home_zone,
                 deposit_zone, can_deposit, split_result, max_carry,
                 version: Optional[str] = "v0.0.1"):
        super().__init__(model)
        self.carrying = []
        self.knowledge = RobotKnowledge()
        self.color = color
        self.allowed_waste_types = allowed_waste_types
        self.home_zone = home_zone
        self.max_zone = home_zone
        self.deposit_zone = deposit_zone
        self.can_deposit = can_deposit
        self.split_result = split_result
        self.max_carry = max_carry
        self.behavior = build_behavior(version or "v0.0.1")

    def deliberate(self) -> dict | None:
        return self.behavior.deliberate(self)

    def _current_pos(self):
        return cast(tuple[int, int], self.pos)

    def step_agent(self):
        current_pos = self._current_pos()
        percepts = self.model.get_local_percepts(current_pos)
        self.knowledge.update_from_percepts(percepts, None, current_pos)

        action = self.deliberate()
        new_percepts = self.model.do(self, action)
        self.knowledge.update_from_percepts(new_percepts, action, self._current_pos())

        for pos, info in new_percepts.items():
            self.knowledge.map[pos]["wastes"] = info["wastes"]

    def step(self):
        self.step_agent()

    @property
    def knowledge_dict(self):
        return self.knowledge.as_dict()

    def known_allowed_wastes(self):
        return [
            pos for pos, info in self.knowledge.map.items()
            if self.model.can_enter(self, pos)
            and any(w in self.allowed_waste_types for w in info["wastes"])
        ]

    def closest_allowed_waste(self):
        current_pos = self._current_pos()
        return min(
            self.known_allowed_wastes(),
            key=lambda pos: self.manhattan_distance(pos, current_pos),
            default=None,
        )

    def manhattan_distance(self, pos1, pos2):
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

    def closest_known_deposit_cell(self):
        current_pos = self._current_pos()
        if self.deposit_zone == 1:
            candidates = [pos for pos, info in self.knowledge.map.items() if info.get("disposal")]
        else:
            candidates = [pos for pos, info in self.knowledge.map.items() if info.get("zone") == self.deposit_zone]
        if not candidates:
            return None
        return min(candidates, key=lambda pos: self.manhattan_distance(pos, current_pos))


# ─── Agents ──────────────────────────────────────────────────────────────────

class greenAgent(Robot):
    def __init__(self, model, version: Optional[str] = "v0.0.1"):
        super().__init__(model, "green", ["green"], 1, 1, True, False, 2, version=version)


class yellowAgent(Robot):
    def __init__(self, model, version: Optional[str] = "v0.0.1"):
        super().__init__(model, "yellow", ["yellow"], 2, 1, False, "green", 2, version=version)


class redAgent(Robot):
    def __init__(self, model, version: Optional[str] = "v0.0.1"):
        super().__init__(model, "red", ["red"], 3, 2, False, "yellow", 2, version=version)
