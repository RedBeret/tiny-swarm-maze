from app.sim.engine import GameEngine
from app.sim.maze import carve_maze, farthest_reachable_cell
from app.sim.types import Point


def test_maze_is_deterministic() -> None:
    grid_a = carve_maze(29, 19, seed=1234)
    grid_b = carve_maze(29, 19, seed=1234)
    assert grid_a == grid_b
    assert grid_a[1][1] == 0


def test_dense_preset_is_larger_than_starter() -> None:
    starter = GameEngine(session_id='s1', seed=1234, difficulty='starter')
    dense = GameEngine(session_id='s2', seed=1234, difficulty='dense')
    assert starter.width < dense.width
    assert starter.height < dense.height


def test_exit_is_far_from_spawn() -> None:
    grid = carve_maze(35, 23, seed=1337)
    spawn = Point(1, 1)
    exit_point = farthest_reachable_cell(grid, spawn)
    assert abs(exit_point.x - spawn.x) + abs(exit_point.y - spawn.y) > 10
