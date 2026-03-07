from __future__ import annotations

import random
from collections import deque

from .types import Point


def carve_maze(width: int, height: int, seed: int, loop_chance: float = 0.08) -> list[list[int]]:
    rng = random.Random(seed)
    grid = [[1 for _ in range(width)] for _ in range(height)]

    start = Point(1, 1)
    grid[start.y][start.x] = 0
    stack = [start]

    while stack:
        current = stack[-1]
        directions = [(2, 0), (-2, 0), (0, 2), (0, -2)]
        rng.shuffle(directions)

        carved = False
        for dx, dy in directions:
            nx = current.x + dx
            ny = current.y + dy
            if not (0 < nx < width - 1 and 0 < ny < height - 1):
                continue
            if grid[ny][nx] == 0:
                continue
            grid[current.y + dy // 2][current.x + dx // 2] = 0
            grid[ny][nx] = 0
            stack.append(Point(nx, ny))
            carved = True
            break

        if not carved:
            stack.pop()

    # Add loops while keeping dead-ends from the DFS backbone.
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if grid[y][x] == 1 and rng.random() < loop_chance:
                grid[y][x] = 0

    grid[1][1] = 0
    return grid


def floor_cells(grid: list[list[int]]) -> list[Point]:
    cells: list[Point] = []
    for y in range(1, len(grid) - 1):
        for x in range(1, len(grid[0]) - 1):
            if grid[y][x] == 0:
                cells.append(Point(x, y))
    return cells


def manhattan(a: Point, b: Point) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def farthest_reachable_cell(grid: list[list[int]], start: Point) -> Point:
    queue = deque([start])
    seen = {(start.x, start.y)}
    farthest = start

    while queue:
        cur = queue.popleft()
        if manhattan(start, cur) > manhattan(start, farthest):
            farthest = cur
        for nxt in neighbors(cur):
            if not in_bounds(grid, nxt):
                continue
            if grid[nxt.y][nxt.x] == 1:
                continue
            key = (nxt.x, nxt.y)
            if key in seen:
                continue
            seen.add(key)
            queue.append(nxt)
    return farthest


def reachable_cells(grid: list[list[int]], start: Point) -> set[tuple[int, int]]:
    queue = deque([start])
    seen: set[tuple[int, int]] = {(start.x, start.y)}
    while queue:
        cur = queue.popleft()
        for nxt in neighbors(cur):
            if not in_bounds(grid, nxt):
                continue
            if grid[nxt.y][nxt.x] == 1:
                continue
            key = (nxt.x, nxt.y)
            if key in seen:
                continue
            seen.add(key)
            queue.append(nxt)
    return seen


def neighbors(point: Point) -> list[Point]:
    return [
        Point(point.x + 1, point.y),
        Point(point.x - 1, point.y),
        Point(point.x, point.y + 1),
        Point(point.x, point.y - 1),
    ]


def in_bounds(grid: list[list[int]], point: Point) -> bool:
    return 0 <= point.x < len(grid[0]) and 0 <= point.y < len(grid)
