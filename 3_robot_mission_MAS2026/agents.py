# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================
from abc import ABC, abstractmethod
from mesa import Agent

class Robot(Agent, ABC):
    def __init__(self, position):
        super().__init__()
        self.knowledge = []
        self.knowledge.append({
            "timestep": 0,
            "percepts": [],
            "actions": [],
            "position": position
        })

    @abstractmethod
    def percepts(self):
        # Code to gather percepts from the environment
        pass
    
    @abstractmethod
    def deliberate(self, percepts):
        # Code to process percepts and decide on an action
        pass

    @abstractmethod
    def do(self, action):
        # Code to execute the action and update knowledge
        pass

    def step_agent(self):
        action = self.deliberate(self.knowledge)
        percepts=self.model.do(self, action)
        self.update(self.knowledge, percepts, action)

    def update(self, percepts, action, position):
        self.knowledge[-1]["percepts"].append(percepts)
        self.knowledge[-1]["actions"].append(action)
        self.knowledge[-1]["timestep"] += 1
        self.knowledge[-1]["position"] = position

class greenAgent(Robot):
    def __init__(self, position):
        super().__init__(position)
        self.color = "green"

class yellowAgent(Robot):
    def __init__(self, position):
        super().__init__(position)
        self.color = "yellow"

class redAgent(Robot):
    def __init__(self, position):
        super().__init__(position)
        self.color = "red"