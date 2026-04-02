import heapq
import random


class NaiveNavigator:
    def step_toward(self, robot, target):
        current_pos = robot._current_pos()
        dx = target[0] - current_pos[0]
        dy = target[1] - current_pos[1]
        candidates = []

        if dx != 0:
            candidates.append((1 if dx > 0 else -1, 0))
        if dy != 0:
            candidates.append((0, 1 if dy > 0 else -1))

        for step in candidates:
            next_pos = (current_pos[0] + step[0], current_pos[1] + step[1])
            if robot.model.can_enter(robot, next_pos):
                return step
        return None

    def exploration_move(self, robot):
        current_pos = robot._current_pos()
        possible_steps = [
            step
            for step in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if robot.model.can_enter(robot, (current_pos[0] + step[0], current_pos[1] + step[1]))
        ]
        return {"name": "move", "direction": random.choice(possible_steps)} if possible_steps else None


class AStarFrontierNavigator:
    def step_toward(self, robot, target):
        start = robot._current_pos()
        if start == target:
            return None

        def heuristic(pos):
            return abs(pos[0] - target[0]) + abs(pos[1] - target[1])

        open_heap = []
        heapq.heappush(open_heap, (heuristic(start), 0, start))

        came_from = {start: None}
        g_score = {start: 0}

        while open_heap:
            _, current_g, current = heapq.heappop(open_heap)
            if current == target:
                break

            x, y = current
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nxt = (x + dx, y + dy)
                if not robot.model.can_enter(robot, nxt):
                    continue

                tentative_g = current_g + 1
                if nxt not in g_score or tentative_g < g_score[nxt]:
                    g_score[nxt] = tentative_g
                    f_score = tentative_g + heuristic(nxt)
                    heapq.heappush(open_heap, (f_score, tentative_g, nxt))
                    came_from[nxt] = current

        if target not in came_from:
            return None

        current = target
        while came_from[current] != start:
            current = came_from[current]
            if current is None:
                return None

        dx = current[0] - start[0]
        dy = current[1] - start[1]
        return (dx, dy)

    def frontier_cells(self, robot):
        frontier = []
        for pos in robot.knowledge.map:
            if not robot.model.can_enter(robot, pos):
                continue

            x, y = pos
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                npos = (x + dx, y + dy)
                if npos not in robot.knowledge.map:
                    frontier.append(pos)
                    break
        return frontier

    def closest_frontier(self, robot):
        current_pos = robot._current_pos()
        frontiers = self.frontier_cells(robot)
        if not frontiers:
            return None
        return min(frontiers, key=lambda pos: robot.shortest_path_distance(pos, current_pos))

    def exploration_move(self, robot):
        target = self.closest_frontier(robot)
        if target is not None:
            step = self.step_toward(robot, target)
            if step is not None:
                return {"name": "move", "direction": step}
        return NaiveNavigator().exploration_move(robot)