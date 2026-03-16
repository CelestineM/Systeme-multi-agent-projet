# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

import mesa
import random
from typing import Any

class RadioactivityAgent(mesa.Agent):
    def __init__(self, unique_id, model, zone):
        super().__init__(unique_id, model)
        self.zone = zone

        if zone == 1:
            self.radioactivity = random.uniform(0.0, 0.33)
        elif zone == 2:
            self.radioactivity = random.uniform(0.33, 0.66)
        elif zone == 3:
            self.radioactivity = random.uniform(0.66, 1.0)
        else:
            raise ValueError(f"Zone invalide : {zone}. Doit être 1, 2 ou 3.")

    def step(self):
        pass  # Aucun comportement


class WasteDisposalZone(mesa.Agent):
  
    def __init__(self, unique_id, model, zone):
        super().__init__(unique_id, model)
        self.zone = zone

    def step(self):
        pass  # Aucun comportement


class WasteAgent(mesa.Agent):

    VALID_TYPES = {"green", "yellow", "red"}

    def __init__(self, unique_id, model, waste_type):
        super().__init__(unique_id, model)

        if waste_type not in self.VALID_TYPES:
            raise ValueError(f"Type de déchet invalide : {waste_type}.")
        
        self.waste_type = waste_type
        if waste_type == "green":
            self.zone = 1
        elif waste_type == "yellow":
            self.zone = 2
        elif waste_type == "red":
            self.zone = 3

    def step(self):
        pass  # Aucun comportement

class ObstacleAgent(mesa.Agent):
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        self.zone = -1
    def step(self):
        pass  # Aucun comportement

class Cell:
    def __init__(self, x: int, y: int, cell_type: Any):
        self.x = x
        self.y = y
        self.cell_type = cell_type
        self.neighbors = []