# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

from abc import ABC, abstractmethod
import mesa

class Robot(mesa.Agent, ABC):
    def __init__(self, model):
        super().__init__(model)
        self.carrying = []
        self.knowledge = [{
            "timestep": 0,
            "percepts": [],
            "actions": [],
            "position": None
        }]

    @abstractmethod
    def percepts(self):
        pass
    
    @abstractmethod
    def deliberate(self, percepts):
        pass

    def step_agent(self):
        current_percepts = self.percepts()
        self.update_knowledge(current_percepts, None, self.pos)
        
        action = self.deliberate(self.knowledge)
        
        new_percepts = self.model.do(self, action)
        self.update_knowledge(new_percepts, action, self.pos)

    def update_knowledge(self, percepts, action, position):
        self.knowledge[-1]["percepts"].append(percepts)
        self.knowledge[-1]["actions"].append(action)
        self.knowledge[-1]["timestep"] += 1
        self.knowledge[-1]["position"] = position

    def step(self):
        self.step_agent()

class greenAgent(Robot):
    def __init__(self, model):
        super().__init__(model)
        self.color = "green"

    def percepts(self):
        return self.model.grid.get_neighbors(self.pos, moore=True, include_center=True)

    def deliberate(self, knowledge):
        return {"name": "move", "direction": (1, 0)}

class yellowAgent(Robot):
    def __init__(self, model):
        super().__init__(model)
        self.color = "yellow"

    def percepts(self):
        return self.model.grid.get_neighbors(self.pos, moore=True, include_center=True)

    def deliberate(self, knowledge):
        return {"name": "move", "direction": (0, 1)}

class redAgent(Robot):
    def __init__(self, model):
        super().__init__(model)
        self.color = "red"

    def percepts(self):
        return self.model.grid.get_neighbors(self.pos, moore=True, include_center=True)

    def deliberate(self, knowledge):
        return {"name": "move", "direction": (0, -1)}