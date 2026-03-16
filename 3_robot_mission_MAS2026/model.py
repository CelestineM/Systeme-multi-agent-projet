# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

import mesa
import math
from agents import greenAgent, yellowAgent, redAgent
from objects import WasteAgent, RadioactivityAgent, WasteDisposalZone

AGENT_CLASSES = {
    'green': greenAgent,
    'yellow': yellowAgent,
    'red': redAgent
}

class RobotMissionModel(mesa.Model):
    def __init__(self, num_robots: dict, width: int, height: int, 
                 num_wastes: dict, epicenters: list, 
                 rayon_zone_3: float, rayon_zone_2: float, 
                 seed: int = None):
        
        # Initialisation du modèle avec la SEED globale
        super().__init__(seed=seed)
        self.running = True
        self.grid = mesa.space.MultiGrid(width, height, torus=False)

        # Dictionnaires pour stocker les coordonnées des cases de chaque zone
        self.zone_cells = {1: [], 2: [], 3: []}

        # --------------------------------------------------------
        # 1. INITIALISATION DE L'ENVIRONNEMENT (Radioactivité et Dépôt)
        # --------------------------------------------------------
        for x in range(width):
            for y in range(height):
                # Calcul de la distance minimale au plus proche épicentre
                min_dist = min([math.dist((x, y), ep) for ep in epicenters])
                
                # Détermination de la zone selon la distance
                if min_dist <= rayon_zone_3:
                    zone = 3
                elif min_dist <= rayon_zone_2:
                    zone = 2
                else:
                    zone = 1
                    
                self.zone_cells[zone].append((x, y))

                # Placement de l'agent de radioactivité (le fond de la carte)
                rad_agent = RadioactivityAgent(self, zone)
                self.grid.place_agent(rad_agent, (x, y))

                # Placement de la WasteDisposalZone sur toute la colonne de droite
                if x == width - 1:
                    disposal_zone = WasteDisposalZone(self, zone)
                    self.grid.place_agent(disposal_zone, (x, y))

        # --------------------------------------------------------
        # 2. PLACEMENT DES DÉCHETS (Dans leurs zones respectives)
        # --------------------------------------------------------
        for waste_type, num in num_wastes.items():
            # Association du type de déchet à sa zone d'origine
            target_zone = 1 if waste_type == "green" else (2 if waste_type == "yellow" else 3)
            available_cells = self.zone_cells[target_zone]
            
            for _ in range(num):
                if not available_cells: # Sécurité si la zone est trop petite
                    break
                # On utilise self.random pour respecter la SEED globale
                pos = self.random.choice(available_cells)
                waste = WasteAgent(self, waste_type)
                self.grid.place_agent(waste, pos)

        # --------------------------------------------------------
        # 3. PLACEMENT DES ROBOTS (Dans les zones autorisées)
        # --------------------------------------------------------
        for color, num in num_robots.items():
            for i in range(num):
                agent_class = AGENT_CLASSES.get(color)
                if agent_class:
                    # Les robots verts commencent en zone 1, les jaunes en Z1/Z2, les rouges partout
                    if color == "green":
                        allowed_cells = self.zone_cells[1]
                    elif color == "yellow":
                        allowed_cells = self.zone_cells[1] + self.zone_cells[2]
                    else:
                        allowed_cells = self.zone_cells[1] + self.zone_cells[2] + self.zone_cells[3]
                        
                    pos = self.random.choice(allowed_cells)
                    robot = agent_class(self)
                    self.grid.place_agent(robot, pos)

        self.datacollector = mesa.DataCollector(
            agent_reporters={"Position": "pos", "Color": "color"}
        )

    def do(self, agent, action):
        if not action: return {}
        if action["name"] == 'move':
            dx, dy = action["direction"]
            new_x, new_y = agent.pos[0] + dx, agent.pos[1] + dy
            if not self.grid.out_of_bounds((new_x, new_y)):
                self.grid.move_agent(agent, (new_x, new_y))

        elif action["name"] == 'pick_up':
            cell_contents = self.grid.get_cell_list_contents([agent.pos])
            wastes = [obj for obj in cell_contents if isinstance(obj, WasteAgent)]
            if wastes:
                waste = wastes[0]
                agent.carrying.append(waste)
                self.grid.remove_agent(waste)
                self.agents.remove(waste)

        return {agent.pos: self.grid.get_cell_list_contents([agent.pos])}

    def step(self):
        self.datacollector.collect(self)
        self.agents.shuffle_do("step")