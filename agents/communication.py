from communication.message.Message import Message
from communication.message.MessagePerformative import MessagePerformative


class NoKnowledgeSharing:
    def share(self, robot):
        return None

    def process_messages(self, robot):
        return None

    def on_discover(self, robot, percepts):
        return None

    def on_pickup(self, robot, position, waste_color=None):
        return None

    def on_deposit(self, robot, position, waste_color=None):
        return None


class LocalKnowledgeSharing:
    """Local sharing only: nearby robots merge their maps."""

    def share(self, robot):
        current_pos = robot._current_pos()
        neighbors = robot.model.grid.get_neighbors(
            current_pos, moore=False, include_center=False, radius=1
        )
        for other in neighbors:
            if other is robot or not hasattr(other, "knowledge"):
                continue
            robot.knowledge.merge_shared_map(other.knowledge.map)

    def process_messages(self, robot):
        return None

    def on_discover(self, robot, percepts):
        return None

    def on_pickup(self, robot, position, waste_color=None):
        return None

    def on_deposit(self, robot, position, waste_color=None):
        return None

NEXT_COLOR = {
        "green": None,
        "yellow": "green",
        "red": "yellow",
    }

class SmartColorKnowledgeSharing:
    """
    Hybrid communication:
    1) local proximity sync with merge_shared_map
    2) minimal event messages for discover / pickup / deposit
    """

    def share(self, robot):
        """
        Local opportunistic synchronization when robots are close.
        """
        current_pos = robot._current_pos()
        neighbors = robot.model.grid.get_neighbors(
            current_pos, moore=False, include_center=False, radius=1
        )
        for other in neighbors:
            if other is robot or not hasattr(other, "knowledge"):
                continue
            robot.knowledge.merge_shared_map(other.knowledge.map)

    def process_messages(self, robot):
        for message in robot.get_new_messages():
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
                    pos=pos,
                    timestamp=timestamp,
                    waste_color=waste_color,
                    zone=zone,
                    disposal=disposal,
                )

            elif event_type == "pickup":
                robot.knowledge.register_pickup(
                    pos=pos,
                    timestamp=timestamp,
                    waste_color=waste_color,
                )

            elif event_type == "deposit":
                robot.knowledge.register_deposit(
                    pos=pos,
                    timestamp=timestamp,
                    waste_color=waste_color,
                    zone=zone,
                )

    def on_discover(self, robot, percepts):
        """
        Triggered after direct perception.
        Send:
        - waste discoveries to relevant robots
        - disposal discoveries to everyone nearby
        """
        if not percepts:
            return

        receivers = self._get_receivers(robot)

        for pos, info in percepts.items():
            wastes = list(info.get("wastes", []))
            disposal = info.get("disposal", False)
            zone = info.get("zone")

            for waste_color in wastes:
                for other in receivers:
                    if self._can_send_discover(robot, other, waste_color):
                        self._send_event(
                            sender=robot,
                            receiver=other,
                            event_type="discover",
                            pos=pos,
                            waste_color=waste_color,
                            zone=zone,
                            disposal=False,
                        )

            if disposal:
                for other in receivers:
                    if self._can_send_disposal_info(robot, other):
                        self._send_event(
                            sender=robot,
                            receiver=other,
                            event_type="discover",
                            pos=pos,
                            waste_color=None,
                            zone=zone,
                            disposal=True,
                        )

    def _get_all_robots(self, robot):
        receivers = []
        for agent in robot.model.agents:
            if agent is robot:
                continue
            if not hasattr(agent, "get_name") or not hasattr(agent, "color"):
                continue
            receivers.append(agent)
        return receivers

    def on_pickup(self, robot, position, waste_color=None):
        zone_info = robot.knowledge.map.get(position, {})
        zone = zone_info.get("zone")    
        receivers = self._get_all_robots(robot)  # broadcast global
        for other in receivers:
            if self._can_send_pickup(robot, other, waste_color):
                self._send_event(
                    sender=robot,
                    receiver=other,
                    event_type="pickup",
                    pos=position,
                    waste_color=waste_color,
                    zone=zone,
                    disposal=False,
                )

    def on_deposit(self, robot, position, waste_color=None):
        zone_info = robot.knowledge.map.get(position, {})
        zone = zone_info.get("zone")
        receivers = self._get_all_robots(robot)  # broadcast global
        for other in receivers:
            if self._can_send_deposit(robot, other, waste_color):
                self._send_event(
                    sender=robot,
                    receiver=other,
                    event_type="deposit",
                    pos=position,
                    waste_color=waste_color,
                    zone=zone,
                    disposal=False,
                )

    def _get_receivers(self, robot):
        current_pos = robot._current_pos()
        neighbors = robot.model.grid.get_neighbors(
            current_pos, moore=False, include_center=False, radius=1
        )

        receivers = []
        for other in neighbors:
            if other is robot:
                continue
            if not hasattr(other, "get_name"):
                continue
            if not hasattr(other, "color"):
                continue
            receivers.append(other)
        return receivers

    def _send_event(
        self,
        sender,
        receiver,
        event_type,
        pos,
        waste_color=None,
        zone=None,
        disposal=False,
    ):
        print(f"{sender.get_name()} sends {event_type} info about {pos} (waste_color={waste_color}, zone={zone}, disposal={disposal}) to {receiver.get_name()}\n")
        sender.send_message(
            Message(
                sender.get_name(),
                receiver.get_name(),
                MessagePerformative.INFORM_REF,
                {
                    "type": event_type,
                    "position": pos,
                    "timestamp": sender.knowledge.timestep,
                    "waste_color": waste_color,
                    "zone": zone,
                    "disposal": disposal,
                },
            )
        )

    def _can_send_disposal_info(self, sender, receiver):
        return True

    def _can_send_discover(self, sender, receiver, waste_color):
        return receiver.color == waste_color

    def _can_send_pickup(self, sender, receiver, waste_color):
        if waste_color is None:
            return True
        return receiver.color == waste_color

    def _can_send_deposit(self, sender, receiver, waste_color):
        next_color = NEXT_COLOR.get(sender.color)
        if next_color is None:
            return False
        return receiver.color == next_color