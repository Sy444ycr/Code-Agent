import json

import pytest

from code_agent.application.scenarios import MockScenarioError, load_mock_decisions


def test_load_mock_decisions_returns_validated_order(tmp_path) -> None:
    path = tmp_path / "decisions.json"
    path.write_text(
        json.dumps({"decisions": [{"action": "complete", "completion_message": "done"}]}),
        encoding="utf-8",
    )

    decisions = load_mock_decisions(path)

    assert [decision.action.value for decision in decisions] == ["complete"]


def test_load_mock_decisions_rejects_unknown_nested_field(tmp_path) -> None:
    path = tmp_path / "decisions.json"
    path.write_text(
        json.dumps({"decisions": [{"action": "complete", "unexpected": True}]}),
        encoding="utf-8",
    )

    with pytest.raises(MockScenarioError, match="unexpected"):
        load_mock_decisions(path)
