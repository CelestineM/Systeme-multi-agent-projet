# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

from mesa import Model
from agents import greenAgent, yellowAgent, redAgent
from typing import Any
from objects import Cell

AGENT_CLASSES = {
    'green': greenAgent,
    'yellow': yellowAgent,
    'red': redAgent
}

class Grid:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.cells = [[Cell(x, y, None) for y in range(height)] for x in range(width)]
        self.agent_positions = {}
    
    def get_cell(self, x: int, y: int) -> Cell:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[x][y]
        else:
            raise IndexError(f"Coordonnées hors limites : ({x}, {y})")
        
    def set_cell(self, x: int, y: int, cell_type: Any):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[x][y] = Cell(x, y, cell_type)

            if cell_type in AGENT_CLASSES:
                self.agent_positions[(x, y)] = cell_type
        else:
            raise IndexError(f"Coordonnées hors limites : ({x}, {y})")

    def update_agent_position(self, agent, direction):
        current_pos = self.agent_positions.get((agent.x, agent.y))
        new_x = agent.x + direction[0]
        new_y = agent.y + direction[1]
        if current_pos:
            del self.agent_positions[(agent.x, agent.y)]
        self.agent_positions[(new_x, new_y)] = agent

class RobotMissionModel(Model):
    def __init__(self, num_robots : dict, grid : Grid):
        super().__init__()
        self.grid = grid

        for color, num in num_robots.items():
            for i in range(num):
                agent_class = AGENT_CLASSES.get(color)
                if agent_class:
                    agent_class(self)
    
    def check_move_validity(self, agent, direction):
        zones = agent.autorized_zones()
        target_cell = self.grid.get_cell(agent.x + direction[0], agent.y + direction[1])
        if target_cell and target_cell.cell_type.zone in zones:
            return True
        return False

    def do(self, agent, action):
        if action.name == 'move':
            if self.check_move_validity(agent, action.direction):
                agent.move(action.direction)
                self.grid.update_agent_position(agent, action.direction)
        if action.name == 'pick_up':
                agent.pick_up()

        pass
    