from __future__ import annotations

import getpass
import json as jsonlib
from pathlib import Path
from typing import Annotated

import typer

from code_agent import __version__, auth
from code_agent.application.providers import ProviderFactoryError, build_provider
from code_agent.application.scenarios import MockScenarioError, load_mock_decisions
from code_agent.application.task_service import TaskService
from code_agent.cli_api import TaskApiClient
from code_agent.config import ProviderConfigurationError, resolve_provider_profile
from code_agent.core.llm import (
    LLMProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
    ProviderRequestError,
)
from code_agent.core.models import ApprovalResolution, PermissionMode, Task, ToolAction
from code_agent.core.policy import PolicyDecision
from code_agent.storage import SQLiteStore

app = typer.Typer(help="Local-first coding agent")
auth_app = typer.Typer(help="Manage provider credentials")
app.add_typer(auth_app, name="auth")


class CLIProviderError(ValueError):
    """可安全显示给命令行用户的 Provider 错误。"""


def _normalize_provider_name(provider: str) -> str:
    try:
        return auth.normalize_provider_name(provider)
    except ValueError as exc:
        raise CLIProviderError("Provider 名称无效。") from exc


def _legacy_build_provider(
    name: str,
    workspace: Path,
    *,
    allow_development_fallback: bool = False,
) -> tuple[LLMProvider, str]:
    provider_name = _normalize_provider_name(name)
    try:
        profile = resolve_provider_profile(provider_name, workspace)
    except ProviderConfigurationError as exc:
        if str(exc) == "未找到指定的 Provider 配置。":
            raise CLIProviderError("Provider 档案不存在。") from exc
        raise CLIProviderError(str(exc)) from exc
    try:
        api_key = auth.get_provider_secret(
            provider_name,
            allow_development_fallback=allow_development_fallback,
        )
    except Exception as exc:
        raise CLIProviderError("无法访问 Provider 凭据。") from exc
    if api_key is None:
        raise CLIProviderError("Provider 密钥未配置。")
    return (
        OpenAICompatibleProvider(
            base_url=profile.base_url,
            model=profile.model,
            api_key_getter=lambda: api_key,
        ),
        provider_name,
    )


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
    try:
        provider_name = _normalize_provider_name(provider)
        if provider_name == "mock":
            if mock_decisions is None:
                raise typer.BadParameter("mock Provider 必须提供 --mock-decisions")
            try:
                decisions = load_mock_decisions(mock_decisions)
            except MockScenarioError as exc:
                raise typer.BadParameter("Mock 场景无效。") from exc
            llm_provider: LLMProvider = MockLLMProvider(decisions)
        else:
            if mock_decisions is not None:
                raise typer.BadParameter("非 Mock Provider 不接受 --mock-decisions")
            try:
                llm_provider, provider_name = build_provider(provider_name, workspace)
            except ProviderFactoryError as exc:
                raise CLIProviderError(str(exc)) from exc
    except CLIProviderError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    state_dir = workspace / ".code-agent"
    state_dir.mkdir(parents=True, exist_ok=True)
    service = TaskService(SQLiteStore(state_dir / "state.db"), approval_handler=_prompt_approval)
    try:
        result = service.run(workspace, goal, mode, llm_provider, provider_name, checks or [])
    except (ProviderRequestError, ValueError) as exc:
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


@app.command()
def status(
    task_id: str,
    url: Annotated[str, typer.Option("--url")] = "http://127.0.0.1:8000",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _print_api_result(TaskApiClient(url).get_status(task_id), json_output)


@app.command()
def approve(
    approval_id: str,
    url: Annotated[str, typer.Option("--url")] = "http://127.0.0.1:8000",
    scope: Annotated[str, typer.Option("--scope")] = "once",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _print_api_result(
        TaskApiClient(url).decide_approval(approval_id, True, scope), json_output
    )


@app.command()
def reject(
    approval_id: str,
    url: Annotated[str, typer.Option("--url")] = "http://127.0.0.1:8000",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _print_api_result(
        TaskApiClient(url).decide_approval(approval_id, False), json_output
    )


@app.command()
def resume(
    task_id: str,
    url: Annotated[str, typer.Option("--url")] = "http://127.0.0.1:8000",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _print_api_result(TaskApiClient(url).resume_task(task_id), json_output)


@app.command()
def attach(url: str) -> None:
    """验证并显示用户提供的本地服务地址。"""
    if not url.startswith(("http://", "https://")):
        typer.echo("服务地址无效。", err=True)
        raise typer.Exit(code=2)
    typer.echo(url)


def _print_api_result(payload: dict[str, object], json_output: bool) -> None:
    if json_output:
        typer.echo(jsonlib.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(jsonlib.dumps(payload, ensure_ascii=False, indent=2))


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
    provider_name = _auth_provider_name(provider)
    try:
        configured = auth.has_secret(provider_name)
    except Exception as exc:
        _credential_error(exc)
    typer.echo(f"{provider_name}: {'configured' if configured else 'missing'}")


@auth_app.command("set")
def auth_set(provider: str) -> None:
    provider_name = _auth_provider_name(provider)
    secret = getpass.getpass(f"Enter {provider_name} API key: ")
    try:
        auth.set_secret(provider_name, secret)
    except Exception as exc:
        _credential_error(exc)
    typer.echo("configured")


@auth_app.command("clear")
def auth_clear(provider: str) -> None:
    provider_name = _auth_provider_name(provider)
    try:
        auth.clear_secret(provider_name)
    except Exception as exc:
        _credential_error(exc)
    typer.echo("cleared")


def _auth_provider_name(provider: str) -> str:
    try:
        return _normalize_provider_name(provider)
    except CLIProviderError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _credential_error(exc: Exception) -> None:
    typer.echo("无法访问 Provider 凭据。", err=True)
    raise typer.Exit(code=2) from exc
