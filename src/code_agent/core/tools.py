from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from code_agent.auth import provider_secret_environment_names
from code_agent.core.models import ToolAction, ToolResult
from code_agent.core.workspace import Workspace


class ToolExecutor:
    def execute(self, action: ToolAction, workspace: Workspace) -> ToolResult:
        try:
            if action.tool == "read_file":
                path = workspace.resolve_inside(str(action.arguments["path"]))
                self._check_size(path, workspace)
                return ToolResult(
                    tool=action.tool, exit_code=0, stdout=path.read_text(encoding="utf-8")
                )
            if action.tool == "write_file":
                path = workspace.resolve_inside(str(action.arguments["path"]))
                content = str(action.arguments.get("content", ""))
                if len(content.encode()) > workspace.max_file_bytes:
                    raise ValueError("file exceeds max_file_bytes")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return ToolResult(
                    tool=action.tool,
                    exit_code=0,
                    changed_files=[path.relative_to(workspace.root).as_posix()],
                )
            if action.tool == "apply_patch":
                path = workspace.resolve_inside(str(action.arguments["path"]))
                content = str(action.arguments.get("content", ""))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return ToolResult(
                    tool=action.tool,
                    exit_code=0,
                    changed_files=[path.relative_to(workspace.root).as_posix()],
                )
            if action.tool == "list_dir":
                path = workspace.resolve_inside(str(action.arguments.get("path", ".")))
                output = "\n".join(sorted(item.name for item in path.iterdir()))
                return ToolResult(
                    tool=action.tool, exit_code=0, stdout=output[: workspace.max_output_chars]
                )
            if action.tool == "search":
                pattern = str(action.arguments["pattern"])
                matches: list[str] = []
                for path in workspace.root.rglob("*"):
                    if path.is_file() and path.stat().st_size <= workspace.max_file_bytes:
                        try:
                            for number, line in enumerate(
                                path.read_text(encoding="utf-8").splitlines(), 1
                            ):
                                if pattern in line:
                                    matches.append(
                                        f"{path.relative_to(workspace.root).as_posix()}:{number}:{line}"
                                    )
                        except UnicodeDecodeError:
                            continue
                return ToolResult(
                    tool=action.tool,
                    exit_code=0,
                    stdout="\n".join(matches)[: workspace.max_output_chars],
                )
            if action.tool == "delete_file":
                path = workspace.resolve_inside(str(action.arguments["path"]))
                path.unlink()
                return ToolResult(
                    tool=action.tool,
                    exit_code=0,
                    changed_files=[path.relative_to(workspace.root).as_posix()],
                )
            if action.tool == "git_diff":
                result = subprocess.run(
                    ["git", "diff"], cwd=workspace.root, capture_output=True, text=True, check=False
                )
                return ToolResult(
                    tool=action.tool,
                    exit_code=result.returncode,
                    stdout=result.stdout[: workspace.max_output_chars],
                    stderr=result.stderr[: workspace.max_output_chars],
                )
            if action.tool in {"shell", "run_check"}:
                command = str(action.arguments.get("command", ""))
                if command.startswith("python "):
                    command = f'"{sys.executable}" {command[7:]}'
                env = {
                    key: value
                    for key, value in os.environ.items()
                    if not re.search(r"(API_KEY|TOKEN|SECRET)$", key)
                    and not re.fullmatch(r"CODE_AGENT_PROVIDER_.*_API_KEY", key)
                    and key not in provider_secret_environment_names()
                }
                timeout = float(action.arguments.get("timeout_seconds", 30))
                try:
                    result = subprocess.run(
                        command,
                        cwd=workspace.root,
                        timeout=timeout,
                        capture_output=True,
                        text=True,
                        shell=True,
                        env=env,
                    )
                    return ToolResult(
                        tool=action.tool,
                        exit_code=result.returncode,
                        stdout=result.stdout[: workspace.max_output_chars],
                        stderr=result.stderr[: workspace.max_output_chars],
                    )
                except subprocess.TimeoutExpired as exc:
                    return ToolResult(
                        tool=action.tool,
                        exit_code=124,
                        stdout=str(exc.stdout or ""),
                        stderr="timed out",
                    )
            return ToolResult(
                tool=action.tool, exit_code=1, stderr=f"unsupported tool: {action.tool}"
            )
        except Exception as exc:
            return ToolResult(
                tool=action.tool, exit_code=1, stderr=str(exc)[: workspace.max_output_chars]
            )

    @staticmethod
    def _check_size(path: Path, workspace: Workspace) -> None:
        if path.stat().st_size > workspace.max_file_bytes:
            raise ValueError("file exceeds max_file_bytes")
