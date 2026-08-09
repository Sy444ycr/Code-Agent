from __future__ import annotations

import getpass
import json as jsonlib
from pathlib import Path
from typing import Annotated

import typer

from code_agent import __version__, auth
from code_agent.application.scenarios import MockScenarioError, load_mock_decisions
from code_agent.application.task_service import TaskService
from code_agent.core.models import ApprovalResolution, PermissionMode, Task, ToolAction
from code_agent.core.policy import PolicyDecision
from code_agent.storage import SQLiteStore

app = typer.Typer(help="Local-first coding agent")
auth_app = typer.Typer(help="Manage provider credentials")
app.add_typer(auth_app, name="auth")


@app.callback(invoke_without_command=True)
def main(version: bool = typer.Option(False, "--version")) -> None:
    if version:
        typer.echo(__version__)


@app.command()
def run(
    workspace: Path,
    goal: str,
    provider: Annotated[str, typer.Option("--provider")] = "mock",
    mock_decisions: Annotated[Path | None, typer.Option("--mock-decisions")] = None,
    mode: Annotated[PermissionMode, typer.Option("--mode")] = PermissionMode.SUPERVISED,
    checks: Annotated[list[str] | None, typer.Option("--check")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    if provider != "mock":
        typer.echo("only the mock provider is supported", err=True)
        raise typer.Exit(code=2)
    if mock_decisions is None:
        typer.echo("--mock-decisions is required for the mock provider", err=True)
        raise typer.Exit(code=2)
    try:
        decisions = load_mock_decisions(mock_decisions)
    except MockScenarioError as exc:
        typer.echo(f"invalid mock scenario: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    state_dir = workspace / ".code-agent"
    state_dir.mkdir(parents=True, exist_ok=True)
    service = TaskService(SQLiteStore(state_dir / "state.db"), approval_handler=_prompt_approval)
    try:
        result = service.run(workspace, goal, mode, decisions, checks or [])
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    payload = {
        "id": result.events[0].task_id if result.events else "",
        "status": result.status.value,
        "report": result.report,
        "events": len(result.events),
        "changed_files": result.changed_files,
        "feedback": [signal.model_dump(mode="json") for signal in result.feedback],
        "verification": result.verification,
    }
    if json_output:
        typer.echo(jsonlib.dumps(payload))
    else:
        typer.echo(f"status: {payload['status']}")
        typer.echo(f"report: {payload['report']}")
        typer.echo(f"changed files: {', '.join(result.changed_files) or 'none'}")
    if result.status.value != "succeeded":
        raise typer.Exit(code=1)


def _prompt_approval(
    task: Task, action: ToolAction, decision: PolicyDecision
) -> ApprovalResolution:
    prompt = (
        f"Approval required: tool={action.tool} risk={decision.risk.value} "
        f"reason={decision.reason} "
        "[y] once [a] task [n] reject"
    )
    while True:
        try:
            choice = typer.prompt(prompt, default="n").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return ApprovalResolution(approved=False)
        if choice == "y":
            return ApprovalResolution(approved=True, scope="once")
        if choice == "a":
            return ApprovalResolution(approved=True, scope="task")
        if choice == "n":
            return ApprovalResolution(approved=False)
        typer.echo("enter y, a, or n", err=True)


@auth_app.command("status")
def auth_status(provider: str) -> None:
    typer.echo(f"{provider}: {'configured' if auth.has_secret(provider) else 'missing'}")


@auth_app.command("set")
def auth_set(provider: str) -> None:
    auth.set_secret(provider, getpass.getpass(f"Enter {provider} API key: "))
    typer.echo("configured")


@auth_app.command("clear")
def auth_clear(provider: str) -> None:
    auth.clear_secret(provider)
    typer.echo("cleared")
