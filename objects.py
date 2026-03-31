# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

import mesa
import random

class RadioactivityAgent(mesa.Agent):
    def __init__(self, model, zone):
        super().__init__(model)
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
        pass

class WasteDisposalZone(mesa.Agent):
    def __init__(self, model, zone):
        super().__init__(model)
        self.zone = zone

    def step(self):
        pass

class WasteAgent(mesa.Agent):
    VALID_TYPES = {"green", "yellow", "red"}

    def __init__(self, model, waste_type):
        super().__init__(model)
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
        pass

class ObstacleAgent(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)
        self.zone = -1

    def step(self):
        pass