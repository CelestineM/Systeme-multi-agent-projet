# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

import mesa
import math
import statistics
from dataclasses import dataclass
from typing import Optional
from agents import greenAgent, yellowAgent, redAgent
from objects import WasteAgent, RadioactivityAgent, WasteDisposalZone
from communication.message.MessageService import MessageService


@dataclass
class CommBudget:
    """Budget de communication par tick pour chaque robot."""
    messages_out: int = 3  # messages envoyables par tick
    messages_in: int = 3   # messages lisibles par tick

AGENT_CLASSES = {
    'green': greenAgent,
    'yellow': yellowAgent,
    'red': redAgent
}

class RobotMissionModel(mesa.Model):
    def __init__(self, num_robots: dict, width: int, height: int, 
                 num_wastes: dict, epicenters: list, 
                 rayon_zone_3: float, rayon_zone_2: float,
                 enable_messaging: bool = False, 
                 seed: Optional[int] = None,
                 version: Optional[str] = None,
                 messages_out: int = 3,
                 messages_in: int = 3):
        
        super().__init__(seed=seed)
        self.running = True
        self.grid = mesa.space.MultiGrid(width, height, torus=False)
        self.current_step = 0
        self.deposit_events = []
        self.enable_messaging = enable_messaging
        self.comm_budget = CommBudget(messages_out=messages_out, messages_in=messages_in)
        MessageService.__instance = None
        self.__messages_service = MessageService(self)
        self.zone_cells = {1: [], 2: [], 3: []}

        for x in range(width):
            for y in range(height):
                min_dist = min(math.dist((x, y), ep) for ep in epicenters)
                if min_dist <= rayon_zone_3:
                    zone = 3
                elif min_dist <= rayon_zone_2:
                    zone = 2
                else:
                    zone = 1
                self.zone_cells[zone].append((x, y))
                rad_agent = RadioactivityAgent(self, zone)
                self.grid.place_agent(rad_agent, (x, y))
                if x == width - 1:
                    disposal_zone = WasteDisposalZone(self, zone)
                    self.grid.place_agent(disposal_zone, (x, y))

        for waste_type, num in num_wastes.items():
            target_zone = 1 if waste_type == "green" else (2 if waste_type == "yellow" else 3)
            available_cells = self.zone_cells[target_zone]
            
            for _ in range(num):
                if not available_cells:
                    break
                pos = self.random.choice(available_cells)
                waste = WasteAgent(self, waste_type)
                self.grid.place_agent(waste, pos)

        for color, num in num_robots.items():
            for _ in range(num):
                agent_class = AGENT_CLASSES.get(color)
                if agent_class:
                    if color == "green":
                        allowed_cells = self.zone_cells[1]
                    elif color == "yellow":
                        allowed_cells = self.zone_cells[2]
                    else:
                        allowed_cells = self.zone_cells[3]
                        
                    pos = self.random.choice(allowed_cells)
                    robot = agent_class(self, version=version)
                    self.grid.place_agent(robot, pos)

        self.datacollector = mesa.DataCollector(
            agent_reporters={"Position": "pos", "Color": "color"}
        )

    def get_zone(self, pos):
        cell = self.grid.get_cell_list_contents([pos])
        radio = next((obj for obj in cell if isinstance(obj, RadioactivityAgent)), None)
        return radio.zone if radio else None
    
    def get_agents_zone(self, zone: int):
        zone_color = {1: "green", 2: "yellow", 3: "red"}
        cells = self.zone_cells[zone]
        agents = self.grid.get_cell_list_contents(cells)
        return [a for a in agents 
                if isinstance(a, (greenAgent, yellowAgent, redAgent)) 
                and a.color == zone_color[zone]]
    
    def is_border_cell_of_zone(self, pos, zone, adjacent_to_zone):
        if self.get_zone(pos) != zone:
            return False

        x, y = pos
        for dx, dy in [(0,1), (0,-1), (1,0), (-1,0)]:
            npos = (x + dx, y + dy)
            if self.grid.out_of_bounds(npos):
                continue
            if self.get_zone(npos) == adjacent_to_zone:
                return True
        return False
    
    def get_local_percepts(self, pos):
        percepts = {}
        x0, y0 = pos
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                x, y = x0 + dx, y0 + dy
                if self.grid.out_of_bounds((x, y)):
                    continue
                cell = self.grid.get_cell_list_contents([(x, y)])
                zone = None
                for obj in cell:
                    if isinstance(obj, RadioactivityAgent):
                        zone = obj.zone
                        break
                percepts[(x, y)] = {
                    "zone": zone,
                    "wastes": [obj.waste_type for obj in cell if isinstance(obj, WasteAgent)],
                    "disposal": any(isinstance(obj, WasteDisposalZone) for obj in cell),
                }

        return percepts
    def can_deposit_red(self, agent, pos):
        return self.is_border_cell_of_zone(pos, zone=2, adjacent_to_zone=3)

    def can_deposit_yellow(self, agent, pos):
        return self.is_border_cell_of_zone(pos, zone=1, adjacent_to_zone=2)

    def is_disposal_cell(self, pos):
        cell = self.grid.get_cell_list_contents([pos])
        return any(isinstance(obj, WasteDisposalZone) for obj in cell)

    def spawn_waste(self, waste_type, pos):
        waste = WasteAgent(self, waste_type)
        self.grid.place_agent(waste, pos)
        self.agents.add(waste)

    def do(self, agent, action):
        if not action:
            return self.get_local_percepts(agent.pos)

        if action["name"] == "move":
            dx, dy = action["direction"]
            new_pos = (agent.pos[0] + dx, agent.pos[1] + dy)

            if not self.grid.out_of_bounds(new_pos):
                cell = self.grid.get_cell_list_contents([new_pos])
                zone = next((obj.zone for obj in cell if isinstance(obj, RadioactivityAgent)), None)

                if self.can_enter(agent, new_pos):
                    self.grid.move_agent(agent, new_pos)

        elif action["name"] == "pickup":
            max_carry = getattr(agent, "max_carry", 2)
            if len(agent.carrying) >= max_carry:
                return self.get_local_percepts(agent.pos)
            
            cell = self.grid.get_cell_list_contents([agent.pos])
            wastes = [
                obj for obj in cell
                if isinstance(obj, WasteAgent) and obj.waste_type in agent.allowed_waste_types
            ]
            if wastes:
                waste = wastes[0]
                agent.carrying.append(waste)
                self.grid.remove_agent(waste)
                self.agents.remove(waste)
        elif action["name"] == "deposit":
            if not agent.carrying:
                return self.get_local_percepts(agent.pos)

            if agent.color == "red" and self.can_deposit_red(agent, agent.pos):
                carried = agent.carrying.pop()
                if carried.waste_type == "red":
                    self.spawn_waste("yellow", agent.pos)
                    self.spawn_waste("yellow", agent.pos)
                    self.deposit_events.append(
                        {
                            "step": self.current_step,
                            "robot_color": "red",
                            "deposited_waste": "red",
                            "resulting_wastes": {"yellow": 2},
                            "position": agent.pos,
                        }
                    )

            elif agent.color == "yellow" and self.can_deposit_yellow(agent, agent.pos):
                carried = agent.carrying.pop()
                if carried.waste_type == "yellow":
                    self.spawn_waste("green", agent.pos)
                    self.spawn_waste("green", agent.pos)
                    self.deposit_events.append(
                        {
                            "step": self.current_step,
                            "robot_color": "yellow",
                            "deposited_waste": "yellow",
                            "resulting_wastes": {"green": 2},
                            "position": agent.pos,
                        }
                    )

            elif agent.color == "green" and self.is_disposal_cell(agent.pos):
                agent.carrying.pop()
                self.deposit_events.append(
                    {
                        "step": self.current_step,
                        "robot_color": "green",
                        "deposited_waste": "green",
                        "resulting_wastes": {},
                        "position": agent.pos,
                    }
                )

        return self.get_local_percepts(agent.pos)

    def step(self):
        self.datacollector.collect(self)
        self.agents.shuffle_do("step")
        self.current_step += 1

    def collect_comm_metrics(self) -> dict:
        """Agrège les métriques de communication et de mouvement de tous les robots."""
        from agents import greenAgent, yellowAgent, redAgent
        robots = [
            a for a in self.agents
            if isinstance(a, (greenAgent, yellowAgent, redAgent))
        ]
        if not robots:
            return {}

        total_steps = max(self.current_step, 1)
        all_moves = [r.metrics["moves"] for r in robots]
        all_pickups = [r.metrics["pickups"] for r in robots]
        all_deposits = [r.metrics["deposits"] for r in robots]
        all_sent = [r.metrics["msg_sent"] for r in robots]
        all_received = [r.metrics["msg_received"] for r in robots]
        all_syncs = [r.metrics["local_syncs"] for r in robots]
        all_idle = [r.metrics["idle_steps"] for r in robots]

        # Budget moyen consommé
        def _mean_budget(key):
            all_vals = [v for r in robots for v in r.metrics[key]]
            return statistics.mean(all_vals) if all_vals else 0.0

        # Ratio budget effectivement consommé vs budget max théorique
        budget_max_out = self.comm_budget.messages_out * total_steps * len(robots)
        budget_max_in  = self.comm_budget.messages_in  * total_steps * len(robots)
        total_out_used = sum(v for r in robots for v in r.metrics["msg_out_budget_used"])
        total_in_used  = sum(v for r in robots for v in r.metrics["msg_in_budget_used"])

        total_wastes_cleared = sum(all_deposits)

        return {
            # Mouvements
            "moves_total": sum(all_moves),
            "moves_max": max(all_moves),
            "moves_min": min(all_moves),
            "moves_avg_per_agent": statistics.mean(all_moves),
            "moves_avg_per_agent_per_step": statistics.mean(all_moves) / total_steps,
            # Actions de pickup/deposit
            "pickups_total": sum(all_pickups),
            "deposits_total": sum(all_deposits),
            "waste_cleared_per_step": total_wastes_cleared / total_steps,
            # Idle steps
            "idle_steps_total": sum(all_idle),
            "idle_ratio": statistics.mean(all_idle) / total_steps,
            # Communication locale
            "local_syncs_total": sum(all_syncs),
            "local_syncs_avg_per_step": sum(all_syncs) / total_steps,
            # Messages envoyés/reçus - si possible
            "msg_sent_total": sum(all_sent),
            "msg_received_total": sum(all_received),
            "msg_sent_per_step": sum(all_sent) / total_steps,
            "msg_received_per_step": sum(all_received) / total_steps,
            # Budget de communication consommé
            "avg_msg_out_budget_used_per_step": _mean_budget("msg_out_budget_used"),
            "avg_msg_in_budget_used_per_step": _mean_budget("msg_in_budget_used"),
            "comm_out_overhead_ratio": total_out_used / budget_max_out if budget_max_out > 0 else 0.0,
            "comm_in_overhead_ratio":  total_in_used  / budget_max_in  if budget_max_in  > 0 else 0.0,
        }

    def can_enter(self, agent, pos):
        if self.grid.out_of_bounds(pos):
            return False
        zone = self.get_zone(pos)
        if agent.color == "green":
            return zone == 1 or self.is_disposal_cell(pos)
        if agent.color == "yellow":
            return zone == 2 or self.is_border_cell_of_zone(pos, zone=1, adjacent_to_zone=2)
        if agent.color == "red":
            return zone == 3 or self.is_border_cell_of_zone(pos, zone=2, adjacent_to_zone=3)
        return False