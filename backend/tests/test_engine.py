from app.schemas import ParsedCommand
from app.sim.engine import GameEngine


def test_engine_applies_command_once() -> None:
    engine = GameEngine(session_id='s1', seed=1234)
    command = ParsedCommand(target_ids=['blue-1'], intent='halt', ttl_ticks=10)
    first = engine.apply_command(command, client_command_id='cmd-1')
    second = engine.apply_command(command, client_command_id='cmd-1')
    assert first is True
    assert second is False


def test_engine_progresses_ticks() -> None:
    engine = GameEngine(session_id='s1', seed=1234)
    start_tick = engine.state.tick
    engine.step()
    assert engine.state.tick == start_tick + 1


def test_engine_has_traps_on_standard() -> None:
    engine = GameEngine(session_id='s1', seed=1234, difficulty='standard')
    assert len(engine.state.traps) >= 1
