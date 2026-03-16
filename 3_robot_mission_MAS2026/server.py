# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

from mesa.visualization import SolaraViz, make_space_component
from model import RobotMissionModel
from agents import greenAgent, yellowAgent, redAgent
from objects import WasteAgent, RadioactivityAgent, WasteDisposalZone

def agent_portrayal(agent):
    if agent is None:
        return

    portrayal = {"marker": "o", "color": "grey", "size": 50}

    if isinstance(agent, greenAgent):
        portrayal["color"] = "green"
        portrayal["size"] = 150
    elif isinstance(agent, yellowAgent):
        portrayal["color"] = "yellow"
        portrayal["size"] = 150
    elif isinstance(agent, redAgent):
        portrayal["color"] = "red"
        portrayal["size"] = 150

    elif isinstance(agent, WasteAgent):
        portrayal["marker"] = "s"
        portrayal["color"] = agent.waste_type
        portrayal["size"] = 60

    elif isinstance(agent, RadioactivityAgent):
        portrayal["marker"] = "s"
        portrayal["size"] = 350
        colors = {1: "#e6ffe6", 2: "#ffffe6", 3: "#ffe6e6"}
        portrayal["color"] = colors.get(agent.zone, "white")
        
    elif isinstance(agent, WasteDisposalZone):
        portrayal["marker"] = "s"
        portrayal["size"] = 250
        portrayal["color"] = "blue"

    return portrayal

model_params = {
    "num_robots": {"green": 2, "yellow": 2, "red": 1},
    "num_wastes": {"green": 8, "yellow": 4, "red": 2},
    "width": 15,
    "height": 15,
    "epicenters": [(7, 7), (2, 12)],
    "rayon_zone_3": 2.5,
    "rayon_zone_2": 5.5,
    "seed": 17
}

mission_model = RobotMissionModel(**model_params)
grid_component = make_space_component(agent_portrayal)

Page = SolaraViz(
    mission_model,
    components=[grid_component],
    model_params=model_params,
    name="Mission de Robots - Zones Concentriques"
)