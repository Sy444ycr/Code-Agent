# Task 18 本地 Mock Agent 端到端闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 使 `code-agent run` 能以可校验的 Mock 决策场景在本地工作区执行真实工具调用、即时审批、验收命令和 SQLite 证据持久化。

**架构：** `TaskService` 作为 CLI 与现有核心模块之间的应用层。它校验 Mock 场景、创建任务、将审批回调注入 `LoopController`，并将结果、事件和审批记录写入 SQLite；CLI 只负责参数、交互与输出。

**技术栈：** Python 3.12+、Typer、Pydantic、SQLite、pytest、Ruff、Mypy。

## 全局约束

- 只支持单机、单任务和 `mock` Provider；真实 Provider、API 后台任务、WebUI、取消/恢复和 SubAgent 派发不在本计划范围内。
- 所有行为变更必须遵循红灯、最小实现、绿灯、回归检查的 TDD 顺序。
- `PolicyEngine` 的硬性禁止规则不可绕过；没有审批回调时，`ask` 必须安全地结束为 `needs_review`。
- 文档和过程记录使用中文；不得修改或暂存用户已有的未跟踪 `.idea/` 目录。
- 任务成功只能由所有 `acceptance_checks` 通过决定，不能仅由 Mock 决策的 `complete` 动作决定。

---

## 文件结构

- `src/code_agent/application/__init__.py`：应用层包导出。
- `src/code_agent/application/scenarios.py`：严格解析 Mock JSON 场景，输出 `list[AgentDecision]`。
- `src/code_agent/application/task_service.py`：创建任务、运行主循环并持久化运行证据。
- `src/code_agent/core/models.py`：增加审批回调使用的 `ApprovalResolution` 模型。
- `src/code_agent/core/loop.py`：在策略返回 `ask` 时调用审批回调、应用一次或任务级授权并发出审批事件。
- `src/code_agent/storage.py`：读取/更新任务，保存/读取审批记录。
- `src/code_agent/cli.py`：实现真实 `run` 参数、终端审批和结果输出。
- `tests/unit/test_scenarios.py`：场景文件的严格校验测试。
- `tests/unit/test_loop_approvals.py`：审批与授权传播测试。
- `tests/integration/test_task_service.py`：TaskService 和 SQLite 证据闭环测试。
- `tests/integration/test_cli_runtime.py`：CLI 临时 Git 仓库端到端测试。
- `SPEC_PROCESS.md`：记录本轮设计、计划、实施和验证证据。

## Task 1：严格 Mock 场景解析

**文件：**

- 创建：`src/code_agent/application/__init__.py`
- 创建：`src/code_agent/application/scenarios.py`
- 创建：`tests/unit/test_scenarios.py`

**接口：**

- 产生：`MockScenarioError(ValueError)`
- 产生：`load_mock_decisions(path: Path) -> list[AgentDecision]`
- 接受：顶层 JSON 对象 `{ "decisions": [...] }`，每个决策字段必须符合 `AgentDecision`，未知字段被拒绝。

- [x] **步骤 1：编写失败测试**

在 `tests/unit/test_scenarios.py` 写入：

```python
import json

import pytest

from code_agent.application.scenarios import MockScenarioError, load_mock_decisions


def test_load_mock_decisions_returns_validated_order(tmp_path) -> None:
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps({"decisions": [{"action": "complete", "completion_message": "done"}]}), encoding="utf-8")

    decisions = load_mock_decisions(path)

    assert [decision.action.value for decision in decisions] == ["complete"]


def test_load_mock_decisions_rejects_unknown_nested_field(tmp_path) -> None:
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps({"decisions": [{"action": "complete", "unexpected": True}]}), encoding="utf-8")

    with pytest.raises(MockScenarioError, match="unexpected"):
        load_mock_decisions(path)
```

- [x] **步骤 2：运行测试并确认红灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_scenarios.py -q
```

预期：因缺少 `code_agent.application.scenarios` 而失败。

- [x] **步骤 3：实现最小场景加载器**

在 `src/code_agent/application/scenarios.py` 定义严格 Pydantic 模型，并在加载时转换为领域模型：

```python
class MockScenarioError(ValueError):
    pass


def load_mock_decisions(path: Path) -> list[AgentDecision]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        scenario = _StrictScenario.model_validate(raw)
        return [AgentDecision.model_validate(item) for item in scenario.decisions]
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise MockScenarioError(str(exc)) from exc
```

`_StrictScenario`、`_StrictDecision` 和 `_StrictToolAction` 使用 `ConfigDict(extra="forbid")`；将 `action`、`rationale`、`tool_action`、`subtask`、`completion_message` 显式映射为 `AgentDecision` 支持的字段。

- [x] **步骤 4：运行测试并确认绿灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_scenarios.py -q
```

预期：通过。

- [x] **步骤 5：提交**

```powershell
git add src/code_agent/application/__init__.py src/code_agent/application/scenarios.py tests/unit/test_scenarios.py
git commit -m "feat: load strict mock decision scenarios"
```

## Task 2：审批驱动的主循环

**文件：**

- 修改：`src/code_agent/core/models.py`
- 修改：`src/code_agent/core/loop.py`
- 创建：`tests/unit/test_loop_approvals.py`

**接口：**

- 产生：`ApprovalResolution(approved: bool, scope: Literal["once", "task"] = "once")`
- `LoopController.__init__` 接受可选 `approval_handler: Callable[[Task, ToolAction, PolicyDecision], ApprovalResolution] | None`。
- `LoopController.run` 在 `ask` 时发出 `approval_requested`、调用处理器、发出 `approval_decided`；任务级授权使用 `risk.value` 加入同一任务的临时授权集合。

- [x] **步骤 1：编写失败测试**

在 `tests/unit/test_loop_approvals.py` 写入：

```python
from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.llm import MockLLMProvider
from code_agent.core.loop import LoopController
from code_agent.core.models import AgentDecision, ApprovalResolution, LoopSpec, PermissionMode, Task, ToolAction, TaskStatus
from code_agent.core.policy import PolicyEngine
from code_agent.core.tools import ToolExecutor


def test_task_grant_allows_second_shell_without_second_prompt(tmp_path) -> None:
    answers: list[str] = []

    def approve(task: Task, action: ToolAction, decision: object) -> ApprovalResolution:
        answers.append(action.tool)
        return ApprovalResolution(approved=True, scope="task")

    loop = LoopController(
        provider=MockLLMProvider([
            AgentDecision(action="tool_call", tool_action=ToolAction(tool="shell", arguments={"command": "python -c \"pass\""})),
            AgentDecision(action="tool_call", tool_action=ToolAction(tool="shell", arguments={"command": "python -c \"pass\""})),
            AgentDecision(action="complete", completion_message="done"),
        ]),
        policy=PolicyEngine(), tools=ToolExecutor(), feedback=FeedbackAdapter(), approval_handler=approve,
    )

    result = loop.run(Task(workspace=str(tmp_path), goal="run", mode=PermissionMode.SUPERVISED), LoopSpec(goal="run"))

    assert result.status == TaskStatus.SUCCEEDED
    assert answers == ["shell"]
    assert [event.type for event in result.events if event.type.startswith("approval_")] == ["approval_requested", "approval_decided"]
```

- [x] **步骤 2：运行测试并确认红灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_loop_approvals.py -q
```

预期：因缺少 `ApprovalResolution` 和 `approval_handler` 而失败。

- [x] **步骤 3：实现最小审批循环**

在 `models.py` 添加：

```python
class ApprovalResolution(BaseModel):
    approved: bool
    scope: Literal["once", "task"] = "once"
```

在 `loop.py` 保存 `approval_handler`，并在策略结果为 `ask` 时：创建 `approval_requested` 事件；没有处理器时返回 `needs_review`；处理器拒绝时创建 `approval_decided` 事件并返回 `needs_review`；处理器批准且范围为 `task` 时将 `policy.risk.value` 加入 `temporary_grants`；批准后执行当前工具调用并继续循环。调用 `policy.evaluate` 时传入 `temporary_grants`。

- [x] **步骤 4：运行测试并确认绿灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_loop_approvals.py tests/unit/test_loop.py -q
```

预期：通过。

- [x] **步骤 5：提交**

```powershell
git add src/code_agent/core/models.py src/code_agent/core/loop.py tests/unit/test_loop_approvals.py
git commit -m "feat: prompt for governed loop actions"
```

## Task 3：任务与审批 SQLite 持久化

**文件：**

- 修改：`src/code_agent/storage.py`
- 修改：`tests/integration/test_storage.py`

**接口：**

- 产生：`SQLiteStore.get_task(task_id: str) -> Task | None`
- 产生：`SQLiteStore.update_task(task: Task) -> Task`
- 产生：`SQLiteStore.save_approval(approval: Approval) -> Approval`
- 产生：`SQLiteStore.get_approval(approval_id: str) -> Approval | None`

- [x] **步骤 1：编写失败测试**

追加到 `tests/integration/test_storage.py`：

```python
from code_agent.core.models import Approval, TaskStatus


def test_task_status_and_approval_roundtrip(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    completed = task.model_copy(update={"status": TaskStatus.SUCCEEDED})
    approval = Approval(tool_call_id="tool-1", reason="shell requires approval")

    store.update_task(completed)
    store.save_approval(approval)

    assert store.get_task(task.id) == completed
    assert store.get_approval(approval.id) == approval
```

- [x] **步骤 2：运行测试并确认红灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_storage.py::test_task_status_and_approval_roundtrip -q
```

预期：因缺少 `update_task` 而失败。

- [x] **步骤 3：实现最小存储方法**

在 `SQLiteStore.__init__` 的建表脚本中增加：

```sql
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, data TEXT);
```

并实现：

```python
def get_task(self, task_id: str) -> Task | None: ...
def update_task(self, task: Task) -> Task: ...
def save_approval(self, approval: Approval) -> Approval: ...
def get_approval(self, approval_id: str) -> Approval | None: ...
```

所有对象以 `model_dump_json()` 保存，以 `model_validate_json()` 恢复；更新任务使用已有 `tasks(id, data)` 表的 `INSERT OR REPLACE`。

- [x] **步骤 4：运行测试并确认绿灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_storage.py -q
```

预期：通过。

- [x] **步骤 5：提交**

```powershell
git add src/code_agent/storage.py tests/integration/test_storage.py
git commit -m "feat: persist task statuses and approvals"
```

## Task 4：TaskService 与 CLI 端到端闭环

**文件：**

- 创建：`src/code_agent/application/task_service.py`
- 修改：`src/code_agent/cli.py`
- 创建：`tests/integration/test_task_service.py`
- 创建：`tests/integration/test_cli_runtime.py`
- 修改：`SPEC_PROCESS.md`

**接口：**

- 产生：`TaskService(store: SQLiteStore, approval_handler: ApprovalPrompt | None = None)`
- 产生：`TaskService.run(workspace: Path, goal: str, mode: PermissionMode, decisions: list[AgentDecision], acceptance_checks: list[str]) -> TaskRunResult`
- `code-agent run` 接受 `--provider`、`--mock-decisions`、`--mode`、多个 `--check` 与 `--json`。

- [x] **步骤 1：编写失败测试**

在 `tests/integration/test_cli_runtime.py` 写入：

```python
import json

from typer.testing import CliRunner

from code_agent.cli import app


def test_cli_run_executes_mock_scenario_and_persists_evidence(tmp_path) -> None:
    (tmp_path / "target.txt").write_text("before", encoding="utf-8")
    scenario = tmp_path / "decisions.json"
    scenario.write_text(json.dumps({"decisions": [
        {"action": "tool_call", "tool_action": {"tool": "write_file", "arguments": {"path": "target.txt", "content": "after"}}},
        {"action": "complete", "completion_message": "done"},
    ]}), encoding="utf-8")

    result = CliRunner().invoke(app, ["run", str(tmp_path), "update target", "--mock-decisions", str(scenario), "--check", "python -c \"from pathlib import Path; assert Path('target.txt').read_text() == 'after'\"", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "succeeded"
    assert payload["changed_files"] == ["target.txt"]
    assert (tmp_path / ".code-agent" / "state.db").exists()
```

并在同一文件追加拒绝审批测试：

```python
def test_cli_run_records_rejected_supervised_shell(tmp_path) -> None:
    scenario = tmp_path / "decisions.json"
    scenario.write_text(json.dumps({"decisions": [
        {"action": "tool_call", "tool_action": {"tool": "shell", "arguments": {"command": "python -c \"pass\""}}},
        {"action": "complete", "completion_message": "done"},
    ]}), encoding="utf-8")

    result = CliRunner().invoke(app, ["run", str(tmp_path), "run shell", "--mock-decisions", str(scenario), "--json"], input="n\n")

    assert result.exit_code == 1
    assert json.loads(result.output.splitlines()[-1])["status"] == "needs_review"
```

- [x] **步骤 2：运行测试并确认红灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_cli_runtime.py -q
```

预期：CLI 不识别 `--mock-decisions`，或仍输出固定 `pending`。

- [x] **步骤 3：实现最小 TaskService 与 CLI**

`TaskService.run` 必须：创建 `Task` 和 `LoopSpec`；将状态更新为 `running`；使用 `MockLLMProvider(decisions)`、`PolicyEngine`、`ToolExecutor`、`FeedbackAdapter` 和 `LoopController` 执行；将全部事件写入 SQLite；创建与更新审批；把最终状态写回任务；追加含报告、反馈、修改文件和验收结果的 `task_completed` 事件。

CLI 的审批回调使用 `typer.prompt` 接收 `y`、`a`、`n`，并返回 `ApprovalResolution`。`--provider` 不等于 `mock`、缺少 `--mock-decisions` 或场景加载失败时，CLI 输出错误并以非零状态退出。JSON 输出使用 `TaskRunResult` 和持久化证据生成的字典；非 JSON 输出显示状态、报告、修改文件与验证摘要。

- [x] **步骤 4：运行测试并确认绿灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_task_service.py tests/integration/test_cli_runtime.py tests/integration/test_cli.py -q
```

预期：通过。

- [x] **步骤 5：运行完整验证并提交**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
```

更新 `SPEC_PROCESS.md`，记录 Task 18 的设计确认、实施任务、红绿测试与最终验证结果。然后提交：

```powershell
git add src/code_agent/application/task_service.py src/code_agent/cli.py tests/integration/test_task_service.py tests/integration/test_cli_runtime.py SPEC_PROCESS.md
git commit -m "feat: run mock tasks through cli"
```

## 自检

**规格覆盖：** Task 1 覆盖可重复且严格的 Mock 输入；Task 2 覆盖治理与即时审批；Task 3 覆盖任务和审批持久化；Task 4 将 CLI、循环、工具、验收和证据串成单机闭环。

**占位符扫描：** 未发现未完成占位语句或模糊的实现指令。

**接口一致性：** Task 2 定义 `ApprovalResolution` 供 Task 4 的 CLI 回调使用；Task 3 定义存储接口供 Task 4 的 `TaskService` 使用；Task 1 定义的 `list[AgentDecision]` 直接供 Task 4 的 Mock Provider 使用。
