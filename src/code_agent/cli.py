from __future__ import annotations

import getpass
import json as jsonlib

import typer

from code_agent import __version__, auth

app = typer.Typer(help="Local-first coding agent")
auth_app = typer.Typer(help="Manage provider credentials")
app.add_typer(auth_app, name="auth")


@app.callback(invoke_without_command=True)
def main(version: bool = typer.Option(False, "--version")) -> None:
    if version:
        typer.echo(__version__)


@app.command()
def run(workspace: str, goal: str, json_output: bool = typer.Option(False, "--json")) -> None:
    result = {"id": "pending", "status": "pending", "workspace": workspace, "goal": goal}
    typer.echo(jsonlib.dumps(result) if json_output else "Task pending")


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
