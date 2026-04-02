from typing import Any


class RobotKnowledge:
    def __init__(self):
        self.timestep = 0
        self.position = None
        self.last_action = None

        self.map: dict[tuple[int, int], dict[str, Any]] = {}
        self.known_wastes: dict[tuple[int, int], dict[str, Any]] = {}
        self.known_deposits: dict[tuple[int, int], dict[str, Any]] = {}
        self.known_disposals: dict[tuple[int, int], dict[str, Any]] = {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestep": self.timestep,
            "position": self.position,
            "last_action": self.last_action,
            "map": self.map,
            "known_wastes": self.known_wastes,
            "known_deposits": self.known_deposits,
            "known_disposals": self.known_disposals,
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

            if info["disposal"]:
                self.register_disposal(
                    pos=pos,
                    timestamp=current_time,
                    zone=info["zone"],
                )

            if len(info["wastes"]) > 0:
                self.known_wastes[pos] = {
                    "wastes": list(info["wastes"]),
                    "timestamp": current_time,
                    "source": "percept",
                    "zone": info["zone"],
                }
            else:
                old_known = self.known_wastes.get(pos)
                if old_known is not None and old_known.get("timestamp", -1) <= current_time:
                    self.known_wastes.pop(pos, None)

    def merge_shared_map(self, other_map):
        """
        Local synchronization when robots are nearby.
        """
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

                if info.get("disposal"):
                    self.register_disposal(
                        pos=pos,
                        timestamp=other_ts,
                        zone=info["zone"],
                    )

                if len(info.get("wastes", [])) > 0:
                    self.known_wastes[pos] = {
                        "wastes": list(info["wastes"]),
                        "timestamp": other_ts,
                        "source": "merge",
                        "zone": info["zone"],
                    }

    def register_discover(self, pos, timestamp, waste_color=None, zone=None, disposal=False):
        if disposal:
            self.register_disposal(pos=pos, timestamp=timestamp, zone=zone)
            return

        current = self.known_wastes.get(pos)
        current_ts = current.get("timestamp", -1) if current else -1

        if current is None or timestamp >= current_ts:
            wastes = list(current.get("wastes", [])) if current else []

            if waste_color is not None and waste_color not in wastes:
                wastes.append(waste_color)

            self.known_wastes[pos] = {
                "wastes": wastes,
                "timestamp": timestamp,
                "source": "message",
                "zone": zone,
            }

    def register_pickup(self, pos, timestamp, waste_color=None):
        current = self.known_wastes.get(pos)
        current_ts = current.get("timestamp", -1) if current else -1

        if current is None or timestamp < current_ts:
            return

        if waste_color is None:
            self.known_wastes.pop(pos, None)
            return

        wastes = list(current.get("wastes", []))
        if waste_color in wastes:
            wastes.remove(waste_color)

        if len(wastes) == 0:
            self.known_wastes.pop(pos, None)
        else:
            self.known_wastes[pos] = {
                "wastes": wastes,
                "timestamp": timestamp,
                "source": "message",
                "zone": current.get("zone"),
            }

    def register_deposit(self, pos, timestamp, waste_color=None, zone=None):
        current = self.known_deposits.get(pos)
        current_ts = current.get("timestamp", -1) if current else -1

        if current is None or timestamp >= current_ts:
            self.known_deposits[pos] = {
                "waste_color": waste_color,
                "timestamp": timestamp,
                "zone": zone,
            }

        current_waste = self.known_wastes.get(pos)
        current_waste_ts = current_waste.get("timestamp", -1) if current_waste else -1

        if current_waste is None or timestamp >= current_waste_ts:
            wastes = [waste_color] if waste_color is not None else []
            self.known_wastes[pos] = {
                "wastes": wastes,
                "timestamp": timestamp,
                "source": "message",
                "zone": zone,
            }

    def register_disposal(self, pos, timestamp, zone=None):
        current = self.known_disposals.get(pos)
        current_ts = current.get("timestamp", -1) if current else -1

        if current is None or timestamp >= current_ts:
            self.known_disposals[pos] = {
                "timestamp": timestamp,
                "zone": zone,
            }