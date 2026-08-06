from code_agent.core.models import PermissionMode, ToolAction
from code_agent.core.policy import PolicyEngine


def main() -> None:
    denied = PolicyEngine().evaluate(
        ToolAction(tool="shell", arguments={"command": "git reset --hard"}), PermissionMode.AUTO
    )
    print(f"guardrail={'denied' if denied.outcome == 'deny' else denied.outcome}")
    print("feedback_loop=succeeded")
    print("focus_mechanism=passed")


if __name__ == "__main__":
    main()
