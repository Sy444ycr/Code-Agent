from code_agent.core.models import PermissionMode, ToolAction
from code_agent.core.policy import ApprovalStore, PolicyEngine


def test_plan_mode_allows_read_and_denies_write() -> None:
    engine = PolicyEngine()
    read = engine.evaluate(
        ToolAction(tool="read_file", arguments={"path": "README.md"}), PermissionMode.PLAN
    )
    write = engine.evaluate(
        ToolAction(tool="write_file", arguments={"path": "x.py"}), PermissionMode.PLAN
    )
    assert read.outcome == "allow"
    assert write.outcome == "deny"
    assert write.rule == "mode_plan_blocks_write"


def test_hard_forbidden_command_is_denied_even_in_auto() -> None:
    engine = PolicyEngine()
    action = ToolAction(tool="shell", arguments={"command": "git reset --hard"})
    decision = engine.evaluate(action, PermissionMode.AUTO)
    assert decision.outcome == "deny"
    assert decision.rule == "hard_forbidden"


def test_supervised_shell_requires_approval() -> None:
    engine = PolicyEngine()
    action = ToolAction(tool="shell", arguments={"command": "python script.py"})
    decision = engine.evaluate(action, PermissionMode.SUPERVISED)
    assert decision.outcome == "ask"
    assert "Shell" in decision.reason


def test_approval_store_records_append_only_decisions() -> None:
    store = ApprovalStore()
    pending = store.create(tool_call_id="tc_1", reason="Shell requires approval")
    approved = store.decide(pending.id, approved=True, scope="once", actor="tester")
    assert pending.status == "pending"
    assert approved.status == "approved"
    assert approved.scope == "once"
    assert approved.actor == "tester"
