"""Legacy formation geometry retained for historical task_sequences replay."""

import math
from typing import List


class FormationGenerator:
    """Historical generator; its geometry conventions must remain unchanged."""

    def __init__(self, global_center: List[float], formation_radius: float):
        self.center = global_center
        self.radius = formation_radius

    def generate_line(self, n: int) -> List[List[float]]:
        start_x = self.center[0] - (n - 1) * self.radius / 2
        return [
            [start_x + index * self.radius, self.center[1], self.center[2]]
            for index in range(n)
        ]

    def generate_circle(self, n: int) -> List[List[float]]:
        return [
            [
                self.center[0] + self.radius * math.cos(2 * math.pi * index / n),
                self.center[1] + self.radius * math.sin(2 * math.pi * index / n),
                self.center[2],
            ]
            for index in range(n)
        ]

    def generate_sphere(self, n: int) -> List[List[float]]:
        points = []
        phi = math.pi * (3.0 - math.sqrt(5.0))
        for index in range(n):
            y_norm = 1 - (index / float(n - 1)) * 2
            radius_at_y = math.sqrt(1 - y_norm * y_norm)
            theta = phi * index
            points.append([
                self.center[0] + math.cos(theta) * radius_at_y * self.radius,
                self.center[1] + y_norm * self.radius,
                self.center[2] + math.sin(theta) * radius_at_y * self.radius,
            ])
        return points

    def generate(self, formation_type: str, uav_count: int) -> List[List[float]]:
        if formation_type in ("Line", "Lineup"):
            return self.generate_line(uav_count)
        if formation_type in ("Circle", "Polygon", "Triangle"):
            return self.generate_circle(uav_count)
        if formation_type == "Sphere":
            return self.generate_sphere(uav_count)
        if formation_type == "Free":
            return []
        raise ValueError(f"不支持的编队类型: {formation_type}")
