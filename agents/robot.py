from abc import ABC
from typing import Optional, cast

from communication.agent.CommunicatingAgent import CommunicatingAgent
from communication.message.Message import Message
from communication.message.MessagePerformative import MessagePerformative

from .policy import build_behavior
from collections import deque

from .knowledge import RobotKnowledge

NEXT_COLOR = {
    "green": None,
    "yellow": "green",
    "red": "yellow",
}


class Robot(CommunicatingAgent, ABC):
    _name_counter = 0

    def __init__(
        self,
        model,
        color,
        allowed_waste_types,
        home_zone,
        deposit_zone,
        can_deposit,
        split_result,
        max_carry,
        version: Optional[str] = "v0.0.1",
    ):
        agent_name = f"{color}_robot_{Robot._name_counter}"
        Robot._name_counter += 1

        super().__init__(model, agent_name)
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
        self.outbox = []
        self.inbox = []

    def _current_pos(self):
        return cast(tuple[int, int], self.pos)

    def step_agent(self):
        current_pos = self._current_pos()

        # Perception directe
        percepts = self.model.get_local_percepts(current_pos)
        self.knowledge.update_from_percepts(percepts, None, current_pos)

        # Les découvertes perçues génèrent des actions send_message
        discover_actions = self.behavior.communication.on_discover(self, percepts)

        # Délibération : retourne [sync_neighbors?, read_messages?, action_physique?]
        actions = self.behavior.deliberate(self)

        # Budget de communication pour ce tick (lu depuis le modèle)
        budget = self.model.comm_budget
        send_budget = budget.messages_out
        read_budget = budget.messages_in

        # Exécution des actions de communication découverte (budgétée)
        for action in discover_actions:
            if action["name"] == "send_message":
                if send_budget > 0:
                    self._do_send(action["to"], action["content"])
                    send_budget -= 1
                # silencieusement ignoré si budget épuisé

        # Exécution de la liste principale d'actions
        for action in actions:
            name = action.get("name")

            if name == "sync_neighbors":
                # Gratuit : pas de budget consommé
                self._sync_neighbors()

            elif name == "read_messages":
                # Budgété : lire au plus read_budget messages
                self.behavior.communication.process_messages(self, limit=read_budget)

            elif name == "send_message":
                if send_budget > 0:
                    self._do_send(action["to"], action["content"])
                    send_budget -= 1

            elif name in ("move", "pickup", "deposit"):
                new_percepts = self.model.do(self, action)
                new_pos = self._current_pos()
                self.knowledge.update_from_percepts(new_percepts, action, new_pos)

                for pos, info in new_percepts.items():
                    if pos in self.knowledge.map:
                        self.knowledge.map[pos]["wastes"] = info["wastes"]

                print(f"[DEBUG] {self.get_name()} action={name}")

                if name == "pickup":
                    post_actions = self.behavior.communication.on_pickup(
                        self, new_pos, self.color
                    )
                elif name == "deposit":
                    deposited_color = NEXT_COLOR.get(self.color)
                    post_actions = self.behavior.communication.on_deposit(
                        self, new_pos, deposited_color
                    )
                else:
                    post_actions = []

                for pa in post_actions:
                    if pa["name"] == "send_message" and send_budget > 0:
                        self._do_send(pa["to"], pa["content"])
                        send_budget -= 1

    def step(self):
        self.step_agent()

    def _sync_neighbors(self):
        """Fusion locale de cartes avec les voisins immédiats (gratuite)."""
        current_pos = self._current_pos()
        neighbors = self.model.grid.get_neighbors(
            current_pos, moore=False, include_center=False, radius=1
        )
        for other in neighbors:
            if other is self or not hasattr(other, "knowledge"):
                continue
            self.knowledge.merge_shared_map(other.knowledge.map)

    def _do_send(self, to: str, content: dict):
        """Envoie effectivement un message (consomme 1 crédit send_budget)."""
        print(f"[MSG] {self.get_name()} → {to} : {content.get('type')} @ {content.get('position')}")
        self.send_message(Message(
            self.get_name(),
            to,
            MessagePerformative.INFORM_REF,
            content,
        ))

    @property
    def knowledge_dict(self):
        return self.knowledge.as_dict()

    def known_allowed_wastes(self):
        known_positions = set(self.knowledge.map.keys()) | set(self.knowledge.known_wastes.keys())

        result = []
        for pos in known_positions:
            if not self.model.can_enter(self, pos):
                continue

            local_info = self.knowledge.map.get(pos, {})
            shared_info = self.knowledge.known_wastes.get(pos, {})

            wastes = list(local_info.get("wastes", []))
            for w in shared_info.get("wastes", []):
                if w not in wastes:
                    wastes.append(w)

            if any(w in self.allowed_waste_types for w in wastes):
                result.append(pos)

        return result

    def closest_allowed_waste(self):
        current_pos = self._current_pos()
        return min(
            self.known_allowed_wastes(),
            key=lambda pos: self.shortest_path_distance(pos, current_pos),
            default=None,
        )

    def shortest_path_distance(self, start, goal):
        if start == goal:
            return 0
        visited = set()
        queue = deque([(start, 0)])
        while queue:
            pos, dist = queue.popleft()
            if pos == goal:
                return dist
            if pos in visited:
                continue
            visited.add(pos)
            x, y = pos
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nxt = (x + dx, y + dy)
                if nxt in visited:
                    continue
                if not self.model.can_enter(self, nxt):
                    continue
                queue.append((nxt, dist + 1))
        return float("inf")

    def closest_known_deposit_cell(self):
        current_pos = self._current_pos()
        if self.deposit_zone == 1:
            candidates = set()
            for pos, info in self.knowledge.map.items():
                if info.get("disposal"):
                    candidates.add(pos)
            for pos in self.knowledge.known_disposals.keys():
                candidates.add(pos)
            if not candidates:
                return None
            return min(candidates, key=lambda pos: self.shortest_path_distance(pos, current_pos))

        candidates = set()
        for pos, info in self.knowledge.map.items():
            if info.get("zone") == self.deposit_zone:
                candidates.add(pos)
        for pos, info in self.knowledge.known_disposals.items():
            if info.get("zone") == self.deposit_zone:
                candidates.add(pos)
        if not candidates:
            return None
        return min(candidates, key=lambda pos: self.shortest_path_distance(pos, current_pos))


class greenAgent(Robot):
    def __init__(self, model, version: Optional[str] = "v0.0.1"):
        super().__init__(model, "green", ["green"], 1, 1, True, False, 2, version=version)


class yellowAgent(Robot):
    def __init__(self, model, version: Optional[str] = "v0.0.1"):
        super().__init__(model, "yellow", ["yellow"], 2, 1, False, "green", 2, version=version)


class redAgent(Robot):
    def __init__(self, model, version: Optional[str] = "v0.0.1"):
        super().__init__(model, "red", ["red"], 3, 2, False, "yellow", 2, version=version)