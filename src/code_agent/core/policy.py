from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from code_agent.core.models import Approval, PermissionMode, RiskLevel, ToolAction


class PolicyDecision(BaseModel):
    outcome: Literal["allow", "ask", "deny"]
    reason: str
    rule: str
    risk: RiskLevel


class PolicyEngine:
    forbidden_fragments = (
        "git reset --hard",
        "git clean -fd",
        "git push --force",
        "git push -f",
        "rm -rf /",
        "del /f /s /q c:\\",
    )

    def classify(self, action: ToolAction) -> RiskLevel:
        tool = action.tool
        command = str(action.arguments.get("command", "")).lower()
        if any(fragment in command for fragment in self.forbidden_fragments):
            return RiskLevel.FORBIDDEN
        if tool in {"read_file", "list_dir", "search", "git_diff"}:
            return RiskLevel.READ
        if tool in {"write_file", "apply_patch"}:
            return RiskLevel.WRITE
        if tool == "delete_file":
            return RiskLevel.DELETE
        if tool == "run_check":
            return RiskLevel.TEST
        if tool == "network":
            return RiskLevel.NETWORK
        if tool == "install_dependency":
            return RiskLevel.INSTALL
        if tool == "shell":
            if command.startswith("git "):
                return RiskLevel.GIT_WRITE
            return RiskLevel.SHELL
        return RiskLevel.SHELL

    def evaluate(
        self,
        action: ToolAction,
        mode: PermissionMode,
        temporary_grants: set[str] | None = None,
    ) -> PolicyDecision:
        grants = temporary_grants or set()
        risk = self.classify(action)
        if risk == RiskLevel.FORBIDDEN:
            return PolicyDecision(
                outcome="deny", reason="Hard forbidden action", rule="hard_forbidden", risk=risk
            )
        if risk.value in grants:
            return PolicyDecision(
                outcome="allow", reason="Temporary task grant", rule="temporary_grant", risk=risk
            )
        if mode == PermissionMode.PLAN:
            if risk == RiskLevel.READ:
                return PolicyDecision(
                    outcome="allow", reason="Read-only action", rule="mode_plan_read", risk=risk
                )
            return PolicyDecision(
                outcome="deny",
                reason="Plan mode blocks write or execution",
                rule=f"mode_plan_blocks_{risk.value}",
                risk=risk,
            )
        if mode == PermissionMode.SUPERVISED:
            if risk in {RiskLevel.READ, RiskLevel.WRITE, RiskLevel.TEST}:
                return PolicyDecision(
                    outcome="allow",
                    reason="Supervised mode allows configured action",
                    rule="mode_supervised_allow",
                    risk=risk,
                )
            return PolicyDecision(
                outcome="ask",
                reason=f"{risk.value.title()} requires approval",
                rule="mode_supervised_ask",
                risk=risk,
            )
        if mode == PermissionMode.AUTO:
            if risk in {RiskLevel.DELETE, RiskLevel.GIT_WRITE}:
                return PolicyDecision(
                    outcome="ask",
                    reason=f"{risk.value.title()} requires approval",
                    rule="mode_auto_ask",
                    risk=risk,
                )
            return PolicyDecision(
                outcome="allow", reason="Auto mode allows action", rule="mode_auto_allow", risk=risk
            )
        return PolicyDecision(
            outcome="deny", reason="Unknown permission mode", rule="unknown_mode", risk=risk
        )


@dataclass
class ApprovalStore:
    approvals: dict[str, Approval] | None = None

    def __post_init__(self) -> None:
        if self.approvals is None:
            self.approvals = {}

    def create(self, tool_call_id: str, reason: str) -> Approval:
        approval = Approval(tool_call_id=tool_call_id, reason=reason)
        assert self.approvals is not None
        self.approvals[approval.id] = approval
        return approval

    def decide(
        self, approval_id: str, approved: bool, scope: Literal["once", "task"], actor: str
    ) -> Approval:
        assert self.approvals is not None
        current = self.approvals[approval_id]
        decided = current.model_copy(
            update={
                "status": "approved" if approved else "rejected",
                "scope": scope,
                "actor": actor,
            }
        )
        self.approvals[approval_id] = decided
        return decided
