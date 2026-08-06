import pytest

from code_agent.core.models import ToolAction
from code_agent.core.tools import ToolExecutor
from code_agent.core.workspace import Workspace, WorkspaceBoundaryError


def test_workspace_rejects_parent_escape(tmp_path) -> None:
    workspace = Workspace(tmp_path)
    with pytest.raises(WorkspaceBoundaryError):
        workspace.resolve_inside("../outside.txt")


def test_file_tools_read_and_write_inside_workspace(tmp_path) -> None:
    workspace = Workspace(tmp_path)
    executor = ToolExecutor()
    write = executor.execute(
        ToolAction(tool="write_file", arguments={"path": "hello.txt", "content": "hi"}), workspace
    )
    read = executor.execute(
        ToolAction(tool="read_file", arguments={"path": "hello.txt"}), workspace
    )
    assert write.exit_code == 0
    assert write.changed_files == ["hello.txt"]
    assert read.stdout == "hi"


def test_search_returns_matching_lines(tmp_path) -> None:
    (tmp_path / "a.py").write_text("print('needle')\n", encoding="utf-8")
    result = ToolExecutor().execute(
        ToolAction(tool="search", arguments={"pattern": "needle"}), Workspace(tmp_path)
    )
    assert "a.py:1:print('needle')" in result.stdout
