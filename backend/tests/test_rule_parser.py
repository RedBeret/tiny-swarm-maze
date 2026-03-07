import asyncio

from app.services.llm.rule_adapter import RuleCommandParser


def test_rule_parser_color_halt() -> None:
    parser = RuleCommandParser()
    parsed = asyncio.run(
        parser.parse_command(
            text='blue stop',
            selected_unit_id=None,
            available_unit_ids=['blue-1', 'red-2'],
            available_colors=['blue', 'red'],
            session_id='s1',
        )
    )
    assert parsed.intent == 'halt'
    assert parsed.target_ids == ['blue-1']


def test_rule_parser_selected_unit_fallback() -> None:
    parser = RuleCommandParser()
    parsed = asyncio.run(
        parser.parse_command(
            text='not that way',
            selected_unit_id='red-2',
            available_unit_ids=['blue-1', 'red-2'],
            available_colors=['blue', 'red'],
            session_id='s1',
        )
    )
    assert parsed.intent == 'avoid'
    assert parsed.target_ids == ['red-2']


def test_rule_parser_follow() -> None:
    parser = RuleCommandParser()
    parsed = asyncio.run(
        parser.parse_command(
            text='blue follow red-2',
            selected_unit_id='blue-1',
            available_unit_ids=['blue-1', 'red-2'],
            available_colors=['blue', 'red'],
            session_id='s1',
        )
    )
    assert parsed.intent == 'follow'
    assert parsed.arguments.get('follow_unit_id') == 'red-2'
