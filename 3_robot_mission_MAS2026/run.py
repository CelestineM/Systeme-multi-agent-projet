# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

from .model import Model, Grid
from .server import Server
from .agents import greenAgent, yellowAgent, redAgent
from .objects import Object
import argparse

def main():
    # chose the number, type of the agents and waste objects
    parser = argparse.ArgumentParser(description='Run the robot mission simulation.')

    # Environment parameters
    parser.add_argument('--grid_width', type=int, default=10, help='Width of the grid')
    parser.add_argument('--grid_height', type=int, default=10, help='Height of the grid')

    # Agents parameters
    parser.add_argument('--num_green_agents', type=int, default=1, help='Number of green agents')
    parser.add_argument('--num_yellow_agents', type=int, default=1, help='Number of yellow agents')
    parser.add_argument('--num_red_agents', type=int, default=1, help='Number of red agents')
    parser.add_argument('--num_objects_green', type=int, default=5, help='Number of green waste objects')
    parser.add_argument('--num_objects_yellow', type=int, default=5, help='Number of yellow waste objects')
    parser.add_argument('--num_objects_red', type=int, default=5, help='Number of red waste objects')

    args = parser.parse_args()

    agents_args = {
        "num_green_agents": args.num_green_agents,
        "num_yellow_agents": args.num_yellow_agents,
        "num_red_agents": args.num_red_agents,
        "num_objects_green": args.num_objects_green,
        "num_objects_yellow": args.num_objects_yellow,
        "num_objects_red": args.num_objects_red,
    }

    grid = Grid(args.grid_width, args.grid_height)
    # create the model and the server
    model = Model(agents_args, grid)
    server = Server(model)
