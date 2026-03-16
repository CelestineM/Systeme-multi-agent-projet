# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

# agent passif représentant la radioactivité d'une cellule, la zone de dépôt des déchets rouges, ou un déchet lui-même
# passif = pas de step, juste des attributs pour stocker les informations nécessaires aux agents actifs (robots)

import mesa
import random

class RadioactivityAgent(mesa.Agent):
   
    # Agent passif représentant la radioactivité d'une cellule.

    # Attributs:
    #     zone (int): la zone à laquelle appartient la cellule (1, 2 ou 3)
    #     radioactivity (float): niveau de radioactivité aléatoire selon la zone
    #         - z1 : entre 0.0  et 0.33
    #         - z2 : entre 0.33 et 0.66
    #         - z3 : entre 0.66 et 1.0
  

    def __init__(self, unique_id, model, zone):
        super().__init__(unique_id, model)
        self.zone = zone

        # On tire un niveau de radioactivité aléatoire selon la zone
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
  
    # Agent passif marquant la zone de dépôt final des déchets rouges.
    # Placée sur la (ou les) cellule(s) la plus à l'est de z3.
    
    # Les robots rouges cherchent cette cellule pour y déposer les déchets.

    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)

    def step(self):
        pass  # Aucun comportement


class WasteAgent(mesa.Agent):

    # Agent passif représentant un déchet dans la grille.
    
    # Attributs:
    #     waste_type (str): type du déchet parmi "green", "yellow", "red"
    #         - green : déchet initial, présent dans z1
    #         - yellow : déchet transformé (2 verts → 1 jaune), transitant en z1/z2
    #         - red : déchet transformé (2 jaunes → 1 rouge), à déposer en z3


    VALID_TYPES = {"green", "yellow", "red"}

    def __init__(self, unique_id, model, waste_type):
        super().__init__(unique_id, model)

        if waste_type not in self.VALID_TYPES:
            raise ValueError(f"Type de déchet invalide : {waste_type}.")
        
        self.waste_type = waste_type

    def step(self):
        pass  # Aucun comportement