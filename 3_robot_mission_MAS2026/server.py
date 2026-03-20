# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

from mesa.visualization import SolaraViz
from model import RobotMissionModel
from agents import greenAgent, yellowAgent, redAgent
from objects import WasteAgent, RadioactivityAgent, WasteDisposalZone

import solara
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def make_custom_space(model):
    fig, ax = plt.subplots(figsize=(7, 7))

    ax.set_xlim(-0.5, model.grid.width - 0.5)
    ax.set_ylim(-0.5, model.grid.height - 0.5)
    ax.set_aspect("equal")
    ax.grid(True, color="lightgray", linewidth=0.5)

    for cell_content, (x, y) in model.grid.coord_iter():
        for agent in cell_content:

            if isinstance(agent, RadioactivityAgent):
                colors = {1: "#e6ffe6", 2: "#e3e3a6", 3: "#f6c0c0"}
                ax.scatter(x, y, marker="s",
                           color=colors.get(agent.zone, "white"),
                           s=500, alpha=0.4, zorder=0)

            elif isinstance(agent, WasteDisposalZone):
                ax.scatter(x, y, marker="s", color="blue",
                           s=400, alpha=0.35, zorder=1)

            elif isinstance(agent, WasteAgent):
                ax.scatter(x, y, marker="s", color=agent.waste_type,
                           s=120, zorder=2)

            elif isinstance(agent, greenAgent):
                ax.scatter(x, y, marker="o", color="green",
                           s=200, zorder=3, edgecolors="black", linewidths=0.8)

            elif isinstance(agent, yellowAgent):
                ax.scatter(x, y, marker="o", color="yellow",
                           s=200, zorder=3, edgecolors="black", linewidths=0.8)

            elif isinstance(agent, redAgent):
                ax.scatter(x, y, marker="o", color="red",
                           s=200, zorder=3, edgecolors="black", linewidths=0.8)

    legend_elements = [
        mpatches.Patch(color="green", label="Robot vert"),
        mpatches.Patch(color="yellow", label="Robot jaune"),
        mpatches.Patch(color="red", label="Robot rouge"),
        mpatches.Patch(color="blue", alpha=0.35, label="Zone dépôt"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)
    plt.tight_layout()
    return fig

def CustomSpaceComponent(model):
    fig = make_custom_space(model)
    return solara.FigureMatplotlib(fig)

model_params = {
    "num_robots": {"green": 2, "yellow": 2, "red": 1},
    "num_wastes": {"green": 8, "yellow": 4, "red": 2},
    "width": 15,
    "height": 15,
    "epicenters": [(7, 7), (1, 13)],
    "rayon_zone_3": 2.5,
    "rayon_zone_2": 5.5,
    "seed": 1
}

mission_model = RobotMissionModel(**model_params)

Page = SolaraViz(
    mission_model,
    components=[CustomSpaceComponent],
    model_params=model_params,
    name="Mission de Robots - Zones Concentriques"
)