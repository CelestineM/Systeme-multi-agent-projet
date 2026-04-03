from communication.message.Message import Message
from communication.message.MessagePerformative import MessagePerformative

NEXT_COLOR = {
    "green": None,
    "yellow": "green",
    "red": "yellow",
}


class NoKnowledgeSharing:
    def share(self, robot) -> list[dict]:
        return []

    def process_messages(self, robot, limit: int = 0) -> None:
        return None

    def on_discover(self, robot, percepts) -> list[dict]:
        return []

    def on_pickup(self, robot, position, waste_color=None) -> list[dict]:
        return []

    def on_deposit(self, robot, position, waste_color=None) -> list[dict]:
        return []


class LocalKnowledgeSharing:
    """Fusion locale de cartes uniquement — pas de messages, pas de budget consommé."""

    def share(self, robot) -> list[dict]:
        return [{"name": "sync_neighbors"}]

    def process_messages(self, robot, limit: int = 0) -> None:
        return None

    def on_discover(self, robot, percepts) -> list[dict]:
        return []

    def on_pickup(self, robot, position, waste_color=None) -> list[dict]:
        return []

    def on_deposit(self, robot, position, waste_color=None) -> list[dict]:
        return []


class SmartColorKnowledgeSharing:
    """
    Communication hybride :
    1) sync locale via merge_shared_map (gratuite)
    2) messages événementiels pour discover / pickup / deposit (budgétés)
    """

    def share(self, robot) -> list[dict]:
        return [
            {"name": "sync_neighbors"},
            {"name": "read_messages"},
        ]

    def process_messages(self, robot, limit: int) -> None:
        count = 0
        for message in robot.get_new_messages():
            if limit > 0 and count >= limit:
                break

            if message.get_performative() != MessagePerformative.INFORM_REF:
                continue

            content = message.get_content()
            if not isinstance(content, dict):
                continue

            event_type = content.get("type")
            pos = content.get("position")
            timestamp = content.get("timestamp", -1)
            waste_color = content.get("waste_color")
            zone = content.get("zone")
            disposal = content.get("disposal", False)

            if event_type is None or pos is None:
                continue

            if event_type == "discover":
                robot.knowledge.register_discover(
                    pos=pos, timestamp=timestamp,
                    waste_color=waste_color, zone=zone, disposal=disposal,
                )
            elif event_type == "pickup":
                robot.knowledge.register_pickup(
                    pos=pos, timestamp=timestamp, waste_color=waste_color,
                )
            elif event_type == "deposit":
                robot.knowledge.register_deposit(
                    pos=pos, timestamp=timestamp,
                    waste_color=waste_color, zone=zone,
                )

            count += 1

    def on_discover(self, robot, percepts) -> list[dict]:
        if not percepts:
            return []

        actions = []
        receivers = self._get_local_receivers(robot)

        for pos, info in percepts.items():
            wastes = list(info.get("wastes", []))
            disposal = info.get("disposal", False)
            zone = info.get("zone")

            for waste_color in wastes:
                for other in receivers:
                    if self._can_send_discover(robot, other, waste_color):
                        actions.append(self._make_send_action(
                            robot, other,
                            event_type="discover",
                            pos=pos,
                            waste_color=waste_color,
                            zone=zone,
                        ))

            if disposal:
                for other in receivers:
                    if self._can_send_disposal_info(robot, other):
                        actions.append(self._make_send_action(
                            robot, other,
                            event_type="discover",
                            pos=pos,
                            waste_color=None,
                            zone=zone,
                            disposal=True,
                        ))

        return actions

    def on_pickup(self, robot, position, waste_color=None) -> list[dict]:
        actions = []
        zone = robot.knowledge.map.get(position, {}).get("zone")
        for other in self._get_all_robots(robot):
            if self._can_send_pickup(robot, other, waste_color):
                actions.append(self._make_send_action(
                    robot, other,
                    event_type="pickup",
                    pos=position,
                    waste_color=waste_color,
                    zone=zone,
                ))
        return actions

    def on_deposit(self, robot, position, waste_color=None) -> list[dict]:
        actions = []
        zone = robot.knowledge.map.get(position, {}).get("zone")
        for other in self._get_all_robots(robot):
            if self._can_send_deposit(robot, other, waste_color):
                actions.append(self._make_send_action(
                    robot, other,
                    event_type="deposit",
                    pos=position,
                    waste_color=waste_color,
                    zone=zone,
                ))
        return actions

    def _make_send_action(
        self, robot, receiver,
        event_type, pos,
        waste_color=None, zone=None, disposal=False,
    ) -> dict:
        return {
            "name": "send_message",
            "to": receiver.get_name(),
            "content": {
                "type": event_type,
                "position": pos,
                "timestamp": robot.knowledge.timestep,
                "waste_color": waste_color,
                "zone": zone,
                "disposal": disposal,
            },
        }

    def _get_local_receivers(self, robot):
        pos = robot._current_pos()
        neighbors = robot.model.grid.get_neighbors(
            pos, moore=False, include_center=False, radius=1
        )
        return [
            a for a in neighbors
            if a is not robot and hasattr(a, "get_name") and hasattr(a, "color")
        ]

    def _get_all_robots(self, robot):
        return [
            a for a in robot.model.agents
            if a is not robot and hasattr(a, "get_name") and hasattr(a, "color")
        ]

    def _can_send_disposal_info(self, sender, receiver):
        return True

    def _can_send_discover(self, sender, receiver, waste_color):
        return receiver.color == waste_color

    def _can_send_pickup(self, sender, receiver, waste_color):
        return waste_color is None or receiver.color == waste_color

    def _can_send_deposit(self, sender, receiver, waste_color):
        next_color = NEXT_COLOR.get(sender.color)
        return next_color is not None and receiver.color == next_color