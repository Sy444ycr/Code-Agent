# Code-Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个本地优先的 Coding Agent Harness，使用户能通过 CLI、TUI 和 WebUI 创建受治理的编码任务，并用 Mock LLM 离线验证主循环、治理、反馈、记忆、Hook、SubAgent 和恢复机制。

**Architecture:** 首版采用模块化单体：核心循环、策略、工具、反馈、记忆和 SubAgent 调度位于纯 Python 包内，不依赖 FastAPI、Textual、React 或 SQLAlchemy 的具体实现。FastAPI、Typer/Textual 和 React 只作为同一任务服务与事件模型的不同客户端，SQLite 仓储可替换为内存仓储以支持确定性测试。

**Tech Stack:** Python 3.12+、Pydantic、FastAPI、SQLAlchemy、SQLite、Typer、Textual、Rich、keyring、pytest、ruff、mypy、React、Vite、TypeScript、Vitest、React Testing Library、Playwright、GitHub Actions、GitLab CI。

## Global Constraints

- 文档语言：仓库文档默认使用中文；代码标识符、命令、配置键和第三方库名称保留英文。
- 禁止使用 LangChain `AgentExecutor`、AutoGen、CrewAI、LlamaIndex Agent 或宿主编码智能体 SDK 的高层 Agent Runner 代替核心 Harness。
- 核心机制必须能在移除真实 LLM 后，通过 Mock LLM 或 stub LLM 进行确定性单元测试。
- 默认 CI 不依赖网络、不依赖真实 API Key，只使用 Mock LLM。
- 权限模式固定为 `plan`、`supervised`、`auto`；硬性拒绝规则不可被 Hook、模式、临时授权或 LLM 覆盖。
- 终止状态固定为 `succeeded`、`needs_review`、`blocked`、`failed`、`budget_exhausted`、`cancelled`。
- API 默认只监听 `127.0.0.1`；非回环监听必须配置访问令牌与允许来源。
- 真实 API Key 不得写入源码、Git、日志、SQLite、Prompt、项目配置、事件、报告或 Shell history。
- workspace 写操作必须解析真实路径和符号链接后限制在 workspace 内。
- 同一 workspace 同时只允许一个写任务；SubAgent 最大嵌套深度为 1。
- Git 管理通过 Shell Tool 完成，不建立独立 GitService；`git reset --hard`、`git clean -fd` 和强制推送始终禁止。
- WebUI 不实现浏览器内代码编辑器；定位为“控制台 + 观察台”。
- 首版不包含多用户云服务、分布式队列、自动 PR、自动部署、重型向量 RAG、递归 SubAgent 和多写 Agent 自动合并。

---

## TDD Execution Contract

本计划必须按严格 TDD 执行。任何执行者在开始任务前都必须遵守以下规则；这些规则优先于单个任务里的实现步骤。

- **红灯先行**：每个行为变更先写一个最小失败测试，再运行该测试并确认失败原因符合计划中的 `Expected: FAIL ...`。
- **禁止跳过红灯**：如果测试第一次运行就通过，说明测试没有覆盖新行为；必须修改测试并重新看到正确失败后才能继续。
- **禁止先写生产代码**：没有红灯证据时，不得创建或修改 `src/`、`web/src/`、运行时配置或生产脚本中的行为代码。
- **最小绿灯**：通过红灯后，只写让当前测试通过的最小实现；不得顺手实现后续任务、额外选项或未被测试覆盖的边界。
- **绿灯验证**：实现后先运行当前任务指定的最小测试，再运行该任务指定的相关测试集合；失败必须修实现代码，而不是放宽测试。
- **重构只在绿灯后进行**：重构不能改变行为；重构后必须重新运行同一组测试并保持通过。
- **证据记录**：每个任务代码提交后，立即在 `AGENT_LOG.md` 记录任务编号、红灯命令与失败摘要、绿灯命令与通过摘要、人工修改说明和实际 commit hash，并作为独立的文档提交；`AGENT_LOG.md` 不纳入各任务代码 commit 的 `git add` 清单。
- **配置与文档例外**：纯文档、CI 配置或包配置变更若无法先写行为测试，必须在任务记录中明确说明例外理由，并至少提供可执行验证命令。
- **一个任务一个评审门**：每个任务完成后先做规格合规检查，再做代码质量检查；未通过前不得开始依赖它的后续任务。
- **环境前提**：首次执行前创建虚拟环境（`python -m venv .venv`）。为保持红灯诚实，Task 1 的红灯步骤前只安装测试运行器（`pip install pytest`），完整依赖 `pip install -e ".[dev]"` 在绿灯步骤安装。
- **Step 3 代码契约**：每个任务 Step 3 给出的代码即为最小实现契约，执行者应逐字采用；如发现其无法通过测试或违反 lint/type 配置，应暂停报告，而非自行改写。

执行时，每个任务的 Step 1-5 含义固定为：

1. RED：写最小失败测试。
2. VERIFY RED：运行测试，确认按预期失败。
3. GREEN：写最小实现。
4. VERIFY GREEN + REFACTOR：运行测试通过；如需重构，只在绿灯后进行并再次运行测试。
5. RECORD + COMMIT：记录红绿证据，提交该任务的最小完整变更。

---

## File Structure

### 后端与核心包

- `pyproject.toml`：Python 包元数据、依赖、命令入口、pytest/ruff/mypy 配置。
- `Makefile`：一键测试、类型检查、前端测试、构建和本地运行命令。
- `.gitlab-ci.yml`：课程要求的 `unit-test` job。
- `.github/workflows/ci.yml`：后端测试、前端测试、类型检查、凭据扫描和包构建。
- `src/code_agent/__init__.py`：包版本导出。
- `src/code_agent/core/models.py`：核心 Pydantic 模型与枚举。
- `src/code_agent/core/events.py`：事件序号、事件类型和事件发布接口。
- `src/code_agent/core/llm.py`：`LLMProvider`、`MockLLMProvider`、`OpenAICompatibleProvider`。
- `src/code_agent/core/policy.py`：权限模式、风险分类、审批状态机与硬性拒绝规则。
- `src/code_agent/core/workspace.py`：workspace 真实路径解析、写锁和边界检查。
- `src/code_agent/core/tools.py`：文件、补丁、搜索、Shell、测试和 Git diff 工具执行。
- `src/code_agent/core/feedback.py`：工具输出到 `FeedbackSignal` 的确定性适配器。
- `src/code_agent/core/memory.py`：内存仓储接口、SQLite 仓储、记忆检索与晋升规则。
- `src/code_agent/core/context.py`：上下文构建、预算裁剪、脱敏与记忆注入。
- `src/code_agent/core/hooks.py`：内置 Hook、项目 Hook 配置与 Hook 执行器。
- `src/code_agent/core/subagents.py`：SubAgent 规格、调度约束与结果汇总。
- `src/code_agent/core/loop.py`：Loop Controller 与 Agent 主循环。
- `src/code_agent/core/reports.py`：最终报告、diff 摘要和验证证据格式。
- `src/code_agent/api/app.py`：FastAPI 应用工厂、REST 路由和 SSE 事件流。
- `src/code_agent/api/schemas.py`：API 请求/响应模型。
- `src/code_agent/cli.py`：Typer 非交互 CLI、服务启动、审批命令和 auth 命令。
- `src/code_agent/tui/app.py`：Textual TUI 入口。
- `src/code_agent/tui/screens.py`：启动页、运行页、审批页和结果页。
- `src/code_agent/auth.py`：keyring 凭据录入、状态查看、更新和清除。
- `src/code_agent/config.py`：配置加载优先级：命令行参数 > 环境变量 > 项目配置 > 默认配置。

### 前端

- `web/package.json`：Vite、React、TypeScript 和测试脚本。
- `web/index.html`：WebUI 挂载入口。
- `web/vite.config.ts`：Vite、测试和代理配置。
- `web/src/main.tsx`：React 入口。
- `web/src/api.ts`：REST 与 SSE 客户端。
- `web/src/types.ts`：前端共享类型。
- `web/src/App.tsx`：控制台布局与路由状态。
- `web/src/components/TaskForm.tsx`：任务创建表单。
- `web/src/components/Timeline.tsx`：事件时间线。
- `web/src/components/ApprovalPanel.tsx`：审批详情与操作。
- `web/src/components/TaskSummary.tsx`：状态、预算、diff 和报告摘要。
- `web/src/styles.css`：仓库级 UI 样式，遵循紧凑开发工具控制台风格。

### 测试与演示

- `tests/unit/test_models.py`：核心模型默认值、校验与序列化。
- `tests/unit/test_policy.py`：权限矩阵、硬性拒绝、审批状态机。
- `tests/unit/test_workspace_tools.py`：workspace 边界、文件工具、Shell/Git 风险分类。
- `tests/unit/test_feedback.py`：退出码、pytest、npm、go、maven 等反馈解析。
- `tests/unit/test_memory_context.py`：记忆晋升、检索、上下文裁剪和脱敏。
- `tests/unit/test_loop.py`：Mock LLM 驱动主循环、失败反馈改变动作、终止状态。
- `tests/unit/test_hooks_subagents.py`：Hook 阻止完成、SubAgent 权限/预算/深度约束。
- `tests/integration/test_api_sse.py`：任务 API、审批 API 和 SSE 事件恢复。
- `tests/integration/test_cli.py`：非交互 CLI、auth 命令和结构化输出。
- `tests/fixtures/workspaces/`：Python、TypeScript、Go、Java fixture。
- `demos/mock_feedback_loop.py`：课程机制演示脚本。
- `web/src/App.test.tsx`：WebUI 关键交互测试。
- `web/e2e/app.spec.ts`：Playwright 桌面与移动视口冒烟测试。

### 文档

- `README.md`：实现完成后更新安装、运行、分发、安全边界和公开 WebUI 地址。
- `SPEC.md`：计划执行中发现规格缺口时同步修订。
- `PLAN.md`：本计划；每完成一个任务标记复选框并记录 commit hash。
- `SPEC_PROCESS.md`：记录 writing-plans 生成、冷启动验证和修订依据。
- `AGENT_LOG.md`：实现阶段每个任务、subagent 输出、人工干预和 commit hash。
- `DESIGN.md`：WebUI 原型确认后生成的设计契约。

---

### Task 1: Python Package Skeleton and Test Harness

**Files:**
- Create: `pyproject.toml`
- Create: `Makefile`
- Create: `src/code_agent/__init__.py`
- Create: `src/code_agent/core/__init__.py`
- Create: `tests/unit/test_imports.py`
- Create: `.gitattributes`
- Modify: `.gitignore`

**Interfaces:**
- Produces: importable package `code_agent`
- Produces: CLI script name `code-agent`
- Produces: test commands `make test`, `make lint`, `make typecheck`

- [x] **Step 1: Write the failing import test**

Create `tests/unit/test_imports.py`:

```python
def test_package_exports_version() -> None:
    import code_agent

    assert isinstance(code_agent.__version__, str)
    assert code_agent.__version__
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_imports.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'code_agent'`.

- [x] **Step 3: Add package configuration**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "code-agent"
version = "0.1.0"
description = "A local-first coding agent harness."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.8",
  "sqlalchemy>=2.0",
  "typer>=0.12",
  "textual>=0.76",
  "rich>=13.7",
  "keyring>=25.0",
  "httpx>=0.27",
  "python-dotenv>=1.0",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "ruff>=0.6",
  "mypy>=1.11",
  "types-PyYAML>=6.0",
]

[project.scripts]
code-agent = "code_agent.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["code_agent"]
```

Create `src/code_agent/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/code_agent/core/__init__.py`:

```python
"""Core harness components for Code-Agent."""
```

Create `Makefile`:

```makefile
.PHONY: test lint typecheck verify web-test

test:
	pytest -q

lint:
	ruff check .

typecheck:
	mypy src

web-test:
	cd web && npm test -- --run

verify: lint typecheck test
```

Append to `.gitignore`（仅追加尚未存在的条目）：

```gitignore
node_modules/
web/dist/
.code-agent/state/
```

Create `.gitattributes` to normalize line endings across platforms:

```gitattributes
* text=auto
```

- [x] **Step 4: Run import test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/unit/test_imports.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml Makefile .gitignore src/code_agent tests/unit/test_imports.py
git commit -m "chore: scaffold code-agent package"
```

---

### Task 2: Core Domain Models and Event Types

**Files:**
- Create: `src/code_agent/core/models.py`
- Create: `src/code_agent/core/events.py`
- Create: `tests/unit/test_models.py`

**Interfaces:**
- Produces: enums `PermissionMode`, `TaskStatus`, `ActionType`, `RiskLevel`, `FeedbackStatus`, `SubAgentRole`
- Produces: models `Budget`, `LoopSpec`, `Task`, `AgentDecision`, `ToolAction`, `ToolResult`, `FeedbackSignal`, `SubTaskSpec`, `SubTaskResult`, `Approval`
- Produces: event model `Event` and protocol `EventSink.emit(task_id: str, event_type: str, payload: dict[str, Any]) -> Event`

- [x] **Step 1: Write failing model tests**

Create `tests/unit/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from code_agent.core.models import (
    ActionType,
    AgentDecision,
    Budget,
    LoopSpec,
    PermissionMode,
    TaskStatus,
    ToolAction,
)


def test_loop_spec_requires_terminal_states() -> None:
    spec = LoopSpec(
        goal="修复失败测试",
        acceptance_checks=["pytest -q"],
        iteration_budget=3,
        time_budget_seconds=600,
    )

    assert spec.terminal_states == [
        TaskStatus.SUCCEEDED,
        TaskStatus.NEEDS_REVIEW,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.BUDGET_EXHAUSTED,
        TaskStatus.CANCELLED,
    ]


def test_agent_decision_validates_tool_call_arguments() -> None:
    decision = AgentDecision(
        action=ActionType.TOOL_CALL,
        rationale="read file",
        tool_action=ToolAction(tool="read_file", arguments={"path": "README.md"}),
    )

    assert decision.tool_action.tool == "read_file"


def test_negative_budget_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Budget(iterations=-1, seconds=10, tool_calls=1)


def test_permission_mode_values_are_stable() -> None:
    assert [mode.value for mode in PermissionMode] == ["plan", "supervised", "auto"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_models.py -q`

Expected: FAIL with imports missing from `code_agent.core.models`.

- [x] **Step 3: Implement model definitions**

Create `src/code_agent/core/models.py` with Pydantic v2 models. Required enum values:

```python
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class PermissionMode(StrEnum):
    PLAN = "plan"
    SUPERVISED = "supervised"
    AUTO = "auto"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"


class ActionType(StrEnum):
    TOOL_CALL = "tool_call"
    DISPATCH_SUBAGENT = "dispatch_subagent"
    REQUEST_USER_INPUT = "request_user_input"
    COMPLETE = "complete"
    STOP = "stop"


class RiskLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    TEST = "test"
    SHELL = "shell"
    NETWORK = "network"
    INSTALL = "install"
    DELETE = "delete"
    GIT_WRITE = "git_write"
    FORBIDDEN = "forbidden"


class FeedbackStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    BLOCKED = "blocked"


class SubAgentRole(StrEnum):
    EXPLORER = "explorer"
    IMPLEMENTER = "implementer"
    VERIFIER = "verifier"
    REVIEWER = "reviewer"


class Budget(BaseModel):
    iterations: int = Field(default=8, ge=0)
    seconds: int = Field(default=1800, ge=0)
    tool_calls: int = Field(default=64, ge=0)
    llm_calls: int = Field(default=32, ge=0)


class LoopSpec(BaseModel):
    goal: str
    acceptance_checks: list[str] = Field(default_factory=list)
    iteration_budget: int = Field(default=8, ge=0)
    time_budget_seconds: int = Field(default=1800, ge=0)
    recovery_policy: dict[str, Any] = Field(default_factory=lambda: {"repeat_failure_limit": 2})
    human_gates: list[str] = Field(default_factory=list)
    terminal_states: list[TaskStatus] = Field(
        default_factory=lambda: [
            TaskStatus.SUCCEEDED,
            TaskStatus.NEEDS_REVIEW,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.BUDGET_EXHAUSTED,
            TaskStatus.CANCELLED,
        ]
    )


class ToolAction(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    action: ActionType
    rationale: str = ""
    tool_action: ToolAction | None = None
    subtask: SubTaskSpec | None = None
    completion_message: str | None = None

    @field_validator("tool_action")
    @classmethod
    def require_tool_for_tool_call(cls, value: ToolAction | None, info: Any) -> ToolAction | None:
        if info.data.get("action") == ActionType.TOOL_CALL and value is None:
            raise ValueError("tool_action is required for tool_call")
        return value


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace: str
    goal: str
    mode: PermissionMode = PermissionMode.SUPERVISED
    provider: str = "mock"
    status: TaskStatus = TaskStatus.PENDING
    budget: Budget = Field(default_factory=Budget)


class ToolResult(BaseModel):
    tool: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    changed_files: list[str] = Field(default_factory=list)


class FeedbackSignal(BaseModel):
    source: str
    status: FeedbackStatus
    summary: str
    evidence: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)
    fingerprint: str | None = None
    retryable: bool = True


class SubTaskSpec(BaseModel):
    role: SubAgentRole
    goal: str
    path_scope: list[str] = Field(default_factory=list)
    budget: Budget = Field(
        default_factory=lambda: Budget(iterations=2, seconds=300, tool_calls=12, llm_calls=4)
    )
    parent_depth: int = 0


class SubTaskResult(BaseModel):
    status: TaskStatus
    summary: str
    findings: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class Approval(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool_call_id: str
    status: Literal["pending", "approved", "rejected", "executed", "failed"] = "pending"
    scope: Literal["once", "task"] = "once"
    reason: str
    actor: str = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Create `src/code_agent/core/events.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    task_id: str
    sequence: int
    type: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventSink(Protocol):
    def emit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> Event:
        """Persist and publish an ordered event."""
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_models.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/models.py src/code_agent/core/events.py tests/unit/test_models.py
git commit -m "feat: define core harness models"
```

---

### Task 3: Policy Engine and Approval State Machine

**Files:**
- Create: `src/code_agent/core/policy.py`
- Create: `tests/unit/test_policy.py`

**Interfaces:**
- Consumes: `PermissionMode`, `RiskLevel`, `ToolAction`, `Approval`
- Produces: `PolicyDecision(outcome: Literal["allow","ask","deny"], reason: str, rule: str, risk: RiskLevel)`
- Produces: `PolicyEngine.classify(action: ToolAction) -> RiskLevel`
- Produces: `PolicyEngine.evaluate(action: ToolAction, mode: PermissionMode, temporary_grants: set[str] | None = None) -> PolicyDecision`
- Produces: `ApprovalStore.create(tool_call_id: str, reason: str) -> Approval`
- Produces: `ApprovalStore.decide(approval_id: str, approved: bool, scope: Literal["once","task"], actor: str) -> Approval`

- [x] **Step 1: Write failing policy tests**

Create `tests/unit/test_policy.py`:

```python
from code_agent.core.models import PermissionMode, ToolAction
from code_agent.core.policy import ApprovalStore, PolicyEngine


def test_plan_mode_allows_read_and_denies_write() -> None:
    engine = PolicyEngine()

    read = engine.evaluate(ToolAction(tool="read_file", arguments={"path": "README.md"}), PermissionMode.PLAN)
    write = engine.evaluate(ToolAction(tool="write_file", arguments={"path": "x.py"}), PermissionMode.PLAN)

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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_policy.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing `PolicyEngine`.

- [x] **Step 3: Implement policy matrix**

Implement `src/code_agent/core/policy.py` with these exact behaviors:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
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
            return PolicyDecision(outcome="deny", reason="Hard forbidden action", rule="hard_forbidden", risk=risk)
        if risk.value in grants:
            return PolicyDecision(outcome="allow", reason="Temporary task grant", rule="temporary_grant", risk=risk)
        if mode == PermissionMode.PLAN:
            if risk == RiskLevel.READ:
                return PolicyDecision(outcome="allow", reason="Read-only action", rule="mode_plan_read", risk=risk)
            return PolicyDecision(outcome="deny", reason="Plan mode blocks write or execution", rule=f"mode_plan_blocks_{risk.value}", risk=risk)
        if mode == PermissionMode.SUPERVISED:
            if risk in {RiskLevel.READ, RiskLevel.WRITE, RiskLevel.TEST}:
                return PolicyDecision(outcome="allow", reason="Supervised mode allows configured action", rule="mode_supervised_allow", risk=risk)
            return PolicyDecision(outcome="ask", reason=f"{risk.value.title()} requires approval", rule="mode_supervised_ask", risk=risk)
        if mode == PermissionMode.AUTO:
            if risk in {RiskLevel.DELETE, RiskLevel.GIT_WRITE}:
                return PolicyDecision(outcome="ask", reason=f"{risk.value.title()} requires approval", rule="mode_auto_ask", risk=risk)
            return PolicyDecision(outcome="allow", reason="Auto mode allows action", rule="mode_auto_allow", risk=risk)
        return PolicyDecision(outcome="deny", reason="Unknown permission mode", rule="unknown_mode", risk=risk)


@dataclass
class ApprovalStore:
    approvals: dict[str, Approval] | None = None

    def __post_init__(self) -> None:
        if self.approvals is None:
            self.approvals = {}

    def create(self, tool_call_id: str, reason: str) -> Approval:
        approval = Approval(tool_call_id=tool_call_id, reason=reason)
        self.approvals[approval.id] = approval
        return approval

    def decide(self, approval_id: str, approved: bool, scope: Literal["once", "task"], actor: str) -> Approval:
        current = self.approvals[approval_id]
        decided = current.model_copy(update={"status": "approved" if approved else "rejected", "scope": scope, "actor": actor})
        self.approvals[approval_id] = decided
        return decided
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_policy.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/policy.py tests/unit/test_policy.py
git commit -m "feat: add policy engine and approvals"
```

---

### Task 4: Workspace Guard and File Tools

**Files:**
- Create: `src/code_agent/core/workspace.py`
- Create: `src/code_agent/core/tools.py`
- Create: `tests/unit/test_workspace_tools.py`

**Interfaces:**
- Consumes: `ToolAction`, `ToolResult`
- Produces: `Workspace.resolve_inside(path: str) -> Path`
- Produces: `Workspace.acquire_write_lock(task_id: str) -> bool`
- Produces: `ToolExecutor.execute(action: ToolAction, workspace: Workspace) -> ToolResult`
- Tools: `read_file`, `list_dir`, `search`, `write_file`, `apply_patch`, `delete_file`, `git_diff`

- [x] **Step 1: Write failing workspace and file tool tests**

Create `tests/unit/test_workspace_tools.py`:

```python
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

    write = executor.execute(ToolAction(tool="write_file", arguments={"path": "hello.txt", "content": "hi"}), workspace)
    read = executor.execute(ToolAction(tool="read_file", arguments={"path": "hello.txt"}), workspace)

    assert write.exit_code == 0
    assert write.changed_files == ["hello.txt"]
    assert read.stdout == "hi"


def test_search_returns_matching_lines(tmp_path) -> None:
    (tmp_path / "a.py").write_text("print('needle')\n", encoding="utf-8")
    workspace = Workspace(tmp_path)
    executor = ToolExecutor()

    result = executor.execute(ToolAction(tool="search", arguments={"pattern": "needle"}), workspace)

    assert "a.py:1:print('needle')" in result.stdout
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_workspace_tools.py -q`

Expected: FAIL with missing `Workspace`.

- [x] **Step 3: Implement workspace guard and text tools**

`Workspace.resolve_inside()` must call `Path.resolve()` on workspace and target and then verify `target == root or root in target.parents`.

`ToolExecutor.execute()` must:

- read/write UTF-8 text by default;
- reject files over configured `max_file_bytes`;
- truncate `stdout` and `stderr` to `max_output_chars`;
- return `ToolResult(exit_code=1, stderr=...)` for controlled tool errors;
- never write outside `Workspace.resolve_inside()`.

Implement file and search tools with this minimum behavior:

```python
executor.execute(ToolAction(tool="read_file", arguments={"path": "README.md"}), workspace)
executor.execute(ToolAction(tool="write_file", arguments={"path": "x.py", "content": "print(1)\n"}), workspace)
executor.execute(ToolAction(tool="list_dir", arguments={"path": "."}), workspace)
executor.execute(ToolAction(tool="search", arguments={"pattern": "class Policy"}), workspace)
executor.execute(ToolAction(tool="delete_file", arguments={"path": "x.py"}), workspace)
executor.execute(ToolAction(tool="git_diff", arguments={}), workspace)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_workspace_tools.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/workspace.py src/code_agent/core/tools.py tests/unit/test_workspace_tools.py
git commit -m "feat: add workspace guard and file tools"
```

---

### Task 5: Shell Execution and Language Verification Adapters

**Files:**
- Modify: `src/code_agent/core/tools.py`
- Create: `src/code_agent/core/project_detection.py`
- Modify: `tests/unit/test_workspace_tools.py`
- Create: `tests/fixtures/workspaces/python/pyproject.toml`
- Create: `tests/fixtures/workspaces/python/tests/test_sample.py`
- Create: `tests/fixtures/workspaces/typescript/package.json`
- Create: `tests/fixtures/workspaces/go/go.mod`
- Create: `tests/fixtures/workspaces/java/pom.xml`

**Interfaces:**
- Produces: `ProjectDetector.detect(workspace: Workspace) -> list[ProjectEcosystem]`
- Produces: `ProjectDetector.verification_commands(workspace: Workspace) -> list[str]`
- Extends: `ToolExecutor` tools `shell` and `run_check`

- [x] **Step 1: Write failing detection and shell tests**

Append to `tests/unit/test_workspace_tools.py`:

```python
from code_agent.core.project_detection import ProjectDetector


def test_project_detector_finds_python_commands(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    workspace = Workspace(tmp_path)

    commands = ProjectDetector().verification_commands(workspace)

    assert "pytest -q" in commands


def test_shell_tool_runs_in_workspace_without_provider_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    workspace = Workspace(tmp_path)
    executor = ToolExecutor()

    result = executor.execute(
        ToolAction(tool="shell", arguments={"command": "python -c \"import os; print(os.getcwd()); print(os.getenv('OPENAI_API_KEY'))\""}),
        workspace,
    )

    assert result.exit_code == 0
    assert str(tmp_path) in result.stdout
    assert "secret-value" not in result.stdout
    assert "None" in result.stdout
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_workspace_tools.py -q`

Expected: FAIL with missing `ProjectDetector` and unsupported `shell`.

- [x] **Step 3: Implement shell and ecosystem detection**

`ProjectDetector` must map these files to commands:

```python
{
    "pyproject.toml": ["pytest -q"],
    "requirements.txt": ["pytest -q"],
    "pytest.ini": ["pytest -q"],
    "package.json": ["npm test -- --run"],
    "go.mod": ["go test ./..."],
    "pom.xml": ["mvn test"],
    "build.gradle": ["gradle test"],
    "Cargo.toml": ["cargo test"],
    "CMakeLists.txt": ["cmake --build build", "ctest --test-dir build"],
    "Makefile": ["make test"],
    "composer.json": ["vendor/bin/phpunit"],
    "Gemfile": ["bundle exec rspec"],
}
```

`ToolExecutor` shell behavior:

- run with `subprocess.run(..., cwd=workspace.root, timeout=timeout_seconds, capture_output=True, text=True)`;
- remove environment variables matching `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `*_API_KEY`, `*_TOKEN`, `*_SECRET`;
- on timeout return `exit_code=124` and `stderr` containing `timed out`;
- `run_check` runs one configured command and labels `ToolResult.tool` as `run_check`.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_workspace_tools.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/tools.py src/code_agent/core/project_detection.py tests/unit/test_workspace_tools.py tests/fixtures/workspaces
git commit -m "feat: execute shell checks safely"
```

---

### Task 6: Feedback Adapters and Failure Fingerprints

**Files:**
- Create: `src/code_agent/core/feedback.py`
- Create: `tests/unit/test_feedback.py`

**Interfaces:**
- Consumes: `ToolResult`
- Produces: `FeedbackAdapter.from_tool_result(result: ToolResult) -> FeedbackSignal`
- Produces: stable failure fingerprints for exit code, pytest failure names, TypeScript errors, Go failures and generic stderr

- [x] **Step 1: Write failing feedback tests**

Create `tests/unit/test_feedback.py`:

```python
from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.models import FeedbackStatus, ToolResult


def test_successful_command_becomes_passed_feedback() -> None:
    signal = FeedbackAdapter().from_tool_result(ToolResult(tool="run_check", exit_code=0, stdout="ok"))

    assert signal.status == FeedbackStatus.PASSED
    assert signal.fingerprint is None


def test_pytest_failure_extracts_test_name() -> None:
    output = "FAILED tests/test_math.py::test_addition - AssertionError: assert 1 == 2"

    signal = FeedbackAdapter().from_tool_result(ToolResult(tool="run_check", exit_code=1, stdout=output))

    assert signal.status == FeedbackStatus.FAILED
    assert signal.fingerprint == "pytest:tests/test_math.py::test_addition"
    assert "test_addition" in signal.summary


def test_generic_failure_uses_exit_code_and_stderr_hash() -> None:
    signal = FeedbackAdapter().from_tool_result(ToolResult(tool="shell", exit_code=2, stderr="compiler exploded"))

    assert signal.status == FeedbackStatus.FAILED
    assert signal.fingerprint.startswith("shell:2:")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_feedback.py -q`

Expected: FAIL with missing `FeedbackAdapter`.

- [x] **Step 3: Implement deterministic parsing**

Implement parsers in this order:

1. `exit_code == 0` -> `FeedbackStatus.PASSED`
2. pytest line regex: `FAILED ([^ ]+) -`
3. TypeScript regex: `(.+\.tsx?\(\d+,\d+\)): error TS(\d+)`
4. Go regex: `--- FAIL: ([^( ]+)`
5. Maven/JUnit regex: `Tests run: .* Failures: ([1-9]\d*)`
6. fallback: `f"{tool}:{exit_code}:{sha1(stderr or stdout)[:12]}"`

Evidence must include at most five non-empty output lines.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_feedback.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/feedback.py tests/unit/test_feedback.py
git commit -m "feat: parse objective feedback signals"
```

---

### Task 7: LLM Provider Abstraction and Mock Decision Sequences

**Files:**
- Create: `src/code_agent/core/llm.py`
- Create: `tests/unit/test_llm.py`

**Interfaces:**
- Consumes: `AgentDecision`
- Produces: protocol `LLMProvider.decide(context: str) -> AgentDecision`
- Produces: `MockLLMProvider(decisions: list[AgentDecision])`
- Produces: `OpenAICompatibleProvider(base_url: str, model: str, api_key_getter: Callable[[], str])`

- [x] **Step 1: Write failing provider tests**

Create `tests/unit/test_llm.py`:

```python
import pytest

from code_agent.core.llm import MockLLMProvider, ProviderExhaustedError
from code_agent.core.models import ActionType, AgentDecision, ToolAction


def test_mock_provider_returns_decisions_in_order() -> None:
    provider = MockLLMProvider(
        [
            AgentDecision(action=ActionType.TOOL_CALL, tool_action=ToolAction(tool="read_file", arguments={"path": "README.md"})),
            AgentDecision(action=ActionType.STOP, rationale="done"),
        ]
    )

    assert provider.decide("ctx").action == ActionType.TOOL_CALL
    assert provider.decide("ctx").action == ActionType.STOP


def test_mock_provider_exhaustion_is_deterministic() -> None:
    provider = MockLLMProvider([])

    with pytest.raises(ProviderExhaustedError):
        provider.decide("ctx")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_llm.py -q`

Expected: FAIL with missing `MockLLMProvider`.

- [x] **Step 3: Implement providers**

`MockLLMProvider` must pop decisions in order and keep `contexts_seen: list[str]`.

`OpenAICompatibleProvider` must:

- make a single HTTP POST to `{base_url.rstrip("/")}/chat/completions`;
- include `Authorization: Bearer <api_key>`;
- request JSON matching `AgentDecision.model_json_schema()`;
- validate response with `AgentDecision.model_validate_json(content)`;
- retry only once on schema failure by sending the validation error as feedback.

Default tests for `OpenAICompatibleProvider` must mock HTTP and never call the network.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_llm.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/llm.py tests/unit/test_llm.py
git commit -m "feat: add llm provider abstraction"
```

---

### Task 8: Memory Store, Checkpoints, and Context Builder

**Files:**
- Create: `src/code_agent/core/memory.py`
- Create: `src/code_agent/core/context.py`
- Create: `tests/unit/test_memory_context.py`

**Interfaces:**
- Produces: `MemoryEntry(workspace: str, type: str, tags: list[str], content: str, evidence: list[str], verified_at: datetime | None)`
- Produces: `MemoryStore.add_verified(entry: MemoryEntry) -> MemoryEntry`
- Produces: `MemoryStore.search(workspace: str, tags: list[str], limit: int) -> list[MemoryEntry]`
- Produces: `ContextBuilder.build(task: Task, loop_spec: LoopSpec, feedback: list[FeedbackSignal]) -> str`

- [x] **Step 1: Write failing memory/context tests**

Create `tests/unit/test_memory_context.py`:

```python
from code_agent.core.context import ContextBuilder
from code_agent.core.memory import InMemoryMemoryStore, MemoryEntry
from code_agent.core.models import FeedbackSignal, FeedbackStatus, LoopSpec, Task


def test_unverified_memory_is_not_promoted() -> None:
    store = InMemoryMemoryStore()

    entry = store.add_candidate(MemoryEntry(workspace="/repo", type="rule", tags=["python"], content="Use pytest", evidence=[]))

    assert entry.verified_at is None
    assert store.search("/repo", ["python"], limit=5) == []


def test_verified_memory_enters_context() -> None:
    store = InMemoryMemoryStore()
    store.add_verified(MemoryEntry(workspace="/repo", type="rule", tags=["python"], content="Use pytest", evidence=["user confirmed"]))
    task = Task(workspace="/repo", goal="fix tests")
    spec = LoopSpec(goal="fix tests", acceptance_checks=["pytest -q"])

    context = ContextBuilder(store, max_chars=800).build(task, spec, feedback=[])

    assert "Use pytest" in context
    assert "pytest -q" in context


def test_context_redacts_known_secret_patterns() -> None:
    store = InMemoryMemoryStore()
    task = Task(workspace="/repo", goal="fix")
    spec = LoopSpec(goal="fix")
    signal = FeedbackSignal(source="shell", status=FeedbackStatus.FAILED, summary="OPENAI_API_KEY=sk-secret123", evidence=[])

    context = ContextBuilder(store, max_chars=800).build(task, spec, feedback=[signal])

    assert "sk-secret123" not in context
    assert "[REDACTED]" in context
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_memory_context.py -q`

Expected: FAIL with missing `InMemoryMemoryStore`.

- [x] **Step 3: Implement in-memory memory and context construction**

Context sections must appear in this order:

1. `Goal`
2. `Acceptance Checks`
3. `Permission Mode`
4. `Recent Feedback`
5. `Relevant Memory`
6. `Unfinished Work`

Redaction patterns:

```python
r"sk-[A-Za-z0-9_-]{8,}"
r"(?i)(api[_-]?key|token|secret)=\S+"
```

When over `max_chars`, remove oldest feedback first, then truncate memory content, while preserving Goal and Acceptance Checks.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_memory_context.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/memory.py src/code_agent/core/context.py tests/unit/test_memory_context.py
git commit -m "feat: add structured memory and context builder"
```

---

### Task 9: Lifecycle Hooks

**Files:**
- Create: `src/code_agent/core/hooks.py`
- Create: `tests/unit/test_hooks_subagents.py`

**Interfaces:**
- Consumes: `ToolAction`, `ToolResult`, `FeedbackSignal`
- Produces: `HookPoint` enum values `on_task_start`, `before_tool_call`, `after_tool_call`, `on_iteration_end`, `before_task_complete`, `on_task_end`
- Produces: `HookResult(blocked: bool, feedback: list[FeedbackSignal], message: str)`
- Produces: `HookRunner.run(point: HookPoint, payload: dict[str, Any]) -> HookResult`

- [x] **Step 1: Write failing hook tests**

Create `tests/unit/test_hooks_subagents.py` with hook tests first:

```python
from code_agent.core.hooks import HookPoint, HookResult, HookRunner
from code_agent.core.models import FeedbackStatus


def test_before_task_complete_hook_can_block_success() -> None:
    runner = HookRunner()
    runner.register(
        HookPoint.BEFORE_TASK_COMPLETE,
        lambda payload: HookResult(blocked=True, message="missing checks"),
    )

    result = runner.run(HookPoint.BEFORE_TASK_COMPLETE, {"status": "succeeded"})

    assert result.blocked is True
    assert result.message == "missing checks"


def test_after_tool_call_hook_can_add_feedback() -> None:
    runner = HookRunner()
    runner.register(
        HookPoint.AFTER_TOOL_CALL,
        lambda payload: HookResult.feedback("hook", FeedbackStatus.FAILED, "custom failure"),
    )

    result = runner.run(HookPoint.AFTER_TOOL_CALL, {})

    assert result.feedback[0].source == "hook"
    assert result.feedback[0].summary == "custom failure"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_hooks_subagents.py -q`

Expected: FAIL with missing `HookRunner`.

- [x] **Step 3: Implement hook runner**

`HookRunner.run()` must execute registered hooks in registration order, merge feedback, and preserve `blocked=True` if any hook blocks. Hook exceptions become failed feedback with source `hook:<HookPoint>`.

Project Hook command execution from `.code-agent/hooks.yaml` is added in this task with a parser that accepts:

```yaml
before_task_complete:
  - command: "pytest -q"
    timeout_seconds: 30
    failure_policy: "block"
```

The project Hook command must be routed through `PolicyEngine.evaluate(ToolAction(tool="shell", ...))` before execution.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_hooks_subagents.py -q`

Expected: PASS for hook tests.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/hooks.py tests/unit/test_hooks_subagents.py
git commit -m "feat: add lifecycle hooks"
```

---

### Task 10: Loop Controller with Feedback-Driven Iteration

**Files:**
- Create: `src/code_agent/core/loop.py`
- Modify: `tests/unit/test_loop.py`

**Interfaces:**
- Consumes: `LLMProvider`, `PolicyEngine`, `ToolExecutor`, `FeedbackAdapter`, `ContextBuilder`, `MemoryStore`, `HookRunner`
- Produces: `LoopController.run(task: Task, loop_spec: LoopSpec) -> TaskRunResult`
- Produces: `TaskRunResult(status: TaskStatus, feedback: list[FeedbackSignal], events: list[Event], report: str)`

- [x] **Step 1: Write failing loop tests**

Create `tests/unit/test_loop.py`:

```python
from code_agent.core.context import ContextBuilder
from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.hooks import HookRunner
from code_agent.core.llm import MockLLMProvider
from code_agent.core.loop import LoopController
from code_agent.core.memory import InMemoryMemoryStore
from code_agent.core.models import ActionType, AgentDecision, LoopSpec, Task, TaskStatus, ToolAction
from code_agent.core.policy import PolicyEngine
from code_agent.core.tools import ToolExecutor


def test_mock_loop_continues_after_failed_check_and_then_succeeds(tmp_path) -> None:
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    task = Task(workspace=str(tmp_path), goal="run checks")
    spec = LoopSpec(goal="run checks", acceptance_checks=["python -m pytest -q"], iteration_budget=3)
    provider = MockLLMProvider(
        [
            AgentDecision(action=ActionType.TOOL_CALL, tool_action=ToolAction(tool="run_check", arguments={"command": "python -c \"raise SystemExit(1)\""})),
            AgentDecision(action=ActionType.TOOL_CALL, tool_action=ToolAction(tool="run_check", arguments={"command": "python -m pytest -q"})),
            AgentDecision(action=ActionType.COMPLETE, completion_message="checks passed"),
        ]
    )
    controller = LoopController(
        provider=provider,
        policy=PolicyEngine(),
        tools=ToolExecutor(),
        feedback=FeedbackAdapter(),
        context=ContextBuilder(InMemoryMemoryStore()),
        hooks=HookRunner(),
    )

    result = controller.run(task, spec)

    assert result.status == TaskStatus.SUCCEEDED
    assert len(provider.contexts_seen) >= 2
    assert any(signal.status.value == "failed" for signal in result.feedback)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_loop.py -q`

Expected: FAIL with missing `LoopController`.

- [x] **Step 3: Implement loop controller**

Loop algorithm:

1. emit `task_started`
2. run `on_task_start`
3. for `iteration` in `range(loop_spec.iteration_budget)`:
4. build context with recent feedback
5. call `provider.decide(context)`
6. emit `decision_made`
7. if action is `tool_call`, run `before_tool_call`, evaluate policy, execute or create approval, run `after_tool_call`, adapt feedback, append feedback
8. if action is `complete`, run all acceptance checks; if checks pass, run `before_task_complete`; if not blocked, return `succeeded`; if checks missing, return `needs_review`
9. if action is `stop`, return `blocked`
10. after loop budget exhausted, return `budget_exhausted`

The loop must not treat LLM `complete` as success until acceptance checks pass or the user has supplied explicit acceptance.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_loop.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/loop.py tests/unit/test_loop.py
git commit -m "feat: implement feedback-driven loop controller"
```

---

### Task 11: SubAgent Scheduler and Summary Contract

**Files:**
- Create: `src/code_agent/core/subagents.py`
- Modify: `tests/unit/test_hooks_subagents.py`

**Interfaces:**
- Consumes: `SubTaskSpec`, `SubTaskResult`, `Task`, `PermissionMode`, `Budget`
- Produces: `SubAgentScheduler.dispatch(parent: Task, spec: SubTaskSpec) -> SubTaskResult`
- Produces: `SubAgentPolicyError`

- [x] **Step 1: Write failing SubAgent tests**

Append to `tests/unit/test_hooks_subagents.py`:

```python
import pytest

from code_agent.core.models import Budget, PermissionMode, SubAgentRole, SubTaskResult, SubTaskSpec, Task, TaskStatus
from code_agent.core.subagents import SubAgentPolicyError, SubAgentScheduler


def test_subagent_depth_cannot_exceed_one() -> None:
    scheduler = SubAgentScheduler()
    parent = Task(workspace="/repo", goal="parent", mode=PermissionMode.AUTO)
    spec = SubTaskSpec(role=SubAgentRole.EXPLORER, goal="inspect", parent_depth=1)

    with pytest.raises(SubAgentPolicyError):
        scheduler.dispatch(parent, spec)


def test_subagent_budget_cannot_exceed_parent() -> None:
    scheduler = SubAgentScheduler()
    parent = Task(workspace="/repo", goal="parent", budget=Budget(iterations=1, seconds=10, tool_calls=1, llm_calls=1))
    spec = SubTaskSpec(role=SubAgentRole.VERIFIER, goal="verify", budget=Budget(iterations=2, seconds=20, tool_calls=2, llm_calls=2))

    with pytest.raises(SubAgentPolicyError):
        scheduler.dispatch(parent, spec)


def test_subagent_returns_structured_summary_only() -> None:
    scheduler = SubAgentScheduler(handler=lambda parent, spec: SubTaskResult(status=TaskStatus.NEEDS_REVIEW, summary="found files"))
    parent = Task(workspace="/repo", goal="parent")
    spec = SubTaskSpec(role=SubAgentRole.EXPLORER, goal="inspect")

    result = scheduler.dispatch(parent, spec)

    assert result.summary == "found files"
    assert not hasattr(result, "transcript")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_hooks_subagents.py -q`

Expected: FAIL with missing `SubAgentScheduler`.

- [x] **Step 3: Implement scheduler constraints**

`SubAgentScheduler` must:

- reject `spec.parent_depth >= 1`;
- reject any child budget field greater than the parent task budget;
- allow at most one writer role (`IMPLEMENTER`) per workspace at a time;
- allow up to three concurrent read-only roles in future async implementation;
- return `SubTaskResult`, not transcript text.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_hooks_subagents.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/core/subagents.py tests/unit/test_hooks_subagents.py
git commit -m "feat: constrain subagent dispatch"
```

---

### Task 12: SQLite Repository, Checkpoint Recovery, and SSE Events

**Files:**
- Modify: `src/code_agent/core/memory.py`
- Modify: `src/code_agent/core/events.py`
- Create: `src/code_agent/storage.py`
- Create: `tests/integration/test_storage.py`

**Interfaces:**
- Produces: `SQLiteStore(path: Path)`
- Produces: `SQLiteStore.create_task(task: Task, loop_spec: LoopSpec) -> Task`
- Produces: `SQLiteStore.append_event(task_id: str, type: str, payload: dict[str, Any]) -> Event`
- Produces: `SQLiteStore.events_after(task_id: str, sequence: int) -> list[Event]`
- Produces: `SQLiteStore.save_checkpoint(task_id: str, checkpoint: dict) -> None`
- Produces: `SQLiteStore.load_checkpoint(task_id: str) -> dict | None`

- [x] **Step 1: Write failing storage tests**

Create `tests/integration/test_storage.py`:

```python
from code_agent.core.models import LoopSpec, Task
from code_agent.storage import SQLiteStore


def test_events_are_ordered_and_replayable(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))

    first = store.append_event(task.id, "task_started", {})
    second = store.append_event(task.id, "decision_made", {"action": "stop"})

    replay = store.events_after(task.id, first.sequence)

    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.sequence for event in replay] == [2]


def test_checkpoint_roundtrip(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))

    store.save_checkpoint(task.id, {"iteration": 2, "pending_action": "approval_1"})

    assert store.load_checkpoint(task.id) == {"iteration": 2, "pending_action": "approval_1"}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_storage.py -q`

Expected: FAIL with missing `SQLiteStore`.

- [x] **Step 3: Implement SQLite persistence**

Use SQLAlchemy Core or ORM. Tables required:

- `tasks(id, workspace, goal, mode, provider, status, budget_json, created_at)`
- `loop_specs(task_id, spec_json)`
- `events(id, task_id, sequence, type, payload_json, created_at)`
- `checkpoints(task_id, payload_json, updated_at)`
- `approvals(id, tool_call_id, task_id, status, scope, reason, actor, created_at)`
- `memory_entries(id, workspace, type, tags_json, content, evidence_json, verified_at, created_at)`

`append_event()` must assign `sequence = max(sequence for task_id) + 1` in one transaction.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_storage.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/storage.py src/code_agent/core/events.py src/code_agent/core/memory.py tests/integration/test_storage.py
git commit -m "feat: persist tasks events and checkpoints"
```

---

### Task 13: FastAPI Task API and SSE

**Files:**
- Create: `src/code_agent/api/__init__.py`
- Create: `src/code_agent/api/schemas.py`
- Create: `src/code_agent/api/app.py`
- Create: `tests/integration/test_api_sse.py`

**Interfaces:**
- Consumes: `SQLiteStore`, `LoopController`
- Produces: `create_app(store: SQLiteStore | None = None, controller_factory: Callable | None = None) -> FastAPI`
- REST routes:
  - `POST /api/tasks`
  - `GET /api/tasks/{id}`
  - `POST /api/tasks/{id}/cancel`
  - `POST /api/tasks/{id}/resume`
  - `GET /api/tasks/{id}/events`
  - `POST /api/approvals/{id}/decision`
  - `GET /api/tasks/{id}/diff`
  - `GET /api/tasks/{id}/report`

- [x] **Step 1: Write failing API tests**

Create `tests/integration/test_api_sse.py`:

```python
from fastapi.testclient import TestClient

from code_agent.api.app import create_app


def test_create_task_returns_task_id(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    client = TestClient(app)

    response = client.post("/api/tasks", json={"workspace": str(tmp_path), "goal": "inspect", "mode": "plan", "provider": "mock"})

    assert response.status_code == 201
    assert response.json()["id"]
    assert response.json()["status"] in {"pending", "running", "needs_review"}


def test_events_endpoint_replays_ordered_events(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    client = TestClient(app)
    task_id = client.post("/api/tasks", json={"workspace": str(tmp_path), "goal": "inspect"}).json()["id"]

    response = client.get(f"/api/tasks/{task_id}/events?after=0")

    assert response.status_code == 200
    assert isinstance(response.json()["events"], list)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_api_sse.py -q`

Expected: FAIL with missing `create_app`.

- [x] **Step 3: Implement API application**

Implementation rules:

- `POST /api/tasks` validates workspace exists before creating task.
- Request model fields: `workspace: str`, `goal: str`, `mode: PermissionMode = supervised`, `provider: str = mock`, `acceptance_checks: list[str] = []`.
- Response model includes `id`, `status`, `workspace`, `goal`, `mode`, `provider`.
- `GET /api/tasks/{id}/events?after=N` returns JSON replay for tests.
- `GET /api/tasks/{id}/events/stream?after=N` returns SSE with `id:` set to sequence and `event:` set to event type.
- A disconnected SSE client must not cancel the task.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_api_sse.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/code_agent/api tests/integration/test_api_sse.py
git commit -m "feat: expose task api and event replay"
```

---

### Task 14: CLI, Auth Commands, and Config Loading

**Files:**
- Create: `src/code_agent/config.py`
- Create: `src/code_agent/auth.py`
- Create: `src/code_agent/cli.py`
- Create: `tests/integration/test_cli.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: Typer app `code_agent.cli:app`
- Produces commands:
  - `code-agent`
  - `code-agent run <workspace> "<需求>"`
  - `code-agent status <task-id>`
  - `code-agent approve <approval-id>`
  - `code-agent reject <approval-id>`
  - `code-agent resume <task-id>`
  - `code-agent attach <url>`
  - `code-agent web`
  - `code-agent auth set <provider>`
  - `code-agent auth status <provider>`
  - `code-agent auth clear <provider>`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/integration/test_cli.py`:

```python
from typer.testing import CliRunner

from code_agent.cli import app


def test_cli_help_lists_run_and_auth() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "auth" in result.output


def test_auth_status_does_not_print_secret(monkeypatch) -> None:
    monkeypatch.setattr("code_agent.auth.has_secret", lambda provider: True)

    result = CliRunner().invoke(app, ["auth", "status", "openai"])

    assert result.exit_code == 0
    assert "configured" in result.output.lower()
    assert "sk-" not in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_cli.py -q`

Expected: FAIL with missing `code_agent.cli`.

- [ ] **Step 3: Implement CLI and keyring auth**

Auth implementation:

```python
SERVICE_NAME = "code-agent"

def set_secret(provider: str, value: str) -> None: ...
def has_secret(provider: str) -> bool: ...
def clear_secret(provider: str) -> None: ...
def get_secret(provider: str) -> str | None: ...
```

Rules:

- `auth set` uses `getpass.getpass()` and never accepts a key as command argument.
- `auth status` prints only configured/missing.
- `.env` fallback requires explicit `CODE_AGENT_ALLOW_ENV_SECRETS=1`.
- `web` starts uvicorn bound to `127.0.0.1` by default.
- `run` supports `--json` output with task id and status.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_agent/config.py src/code_agent/auth.py src/code_agent/cli.py tests/integration/test_cli.py .env.example
git commit -m "feat: add cli and credential commands"
```

---

### Task 15: Textual TUI Screens

**Files:**
- Create: `src/code_agent/tui/__init__.py`
- Create: `src/code_agent/tui/app.py`
- Create: `src/code_agent/tui/screens.py`
- Create: `tests/integration/test_tui.py`

**Interfaces:**
- Produces: `CodeAgentTui(api_base_url: str | None = None)`
- Screens: `StartScreen`, `RunScreen`, `ApprovalScreen`, `ResultScreen`

- [ ] **Step 1: Write failing TUI smoke test**

Create `tests/integration/test_tui.py`:

```python
import pytest

from code_agent.tui.app import CodeAgentTui


@pytest.mark.asyncio
async def test_tui_starts_on_start_screen() -> None:
    app = CodeAgentTui(api_base_url=None)

    async with app.run_test() as pilot:
        assert app.screen.id == "start"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_tui.py -q`

Expected: FAIL with missing `CodeAgentTui`.

- [ ] **Step 3: Implement minimal screens**

Start screen must display:

- workspace input;
- goal input;
- provider selector;
- permission mode selector;
- detected project ecosystem;
- Git status summary;
- recent tasks list.

Approval screen must display action, risk reason, impact scope, `Allow Once`, `Allow For Task`, and `Reject` buttons.

Result screen must display final status, diff summary, verification evidence, and unresolved items.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_tui.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_agent/tui tests/integration/test_tui.py
git commit -m "feat: add textual task console"
```

---

### Task 16: WebUI Console

**Files:**
- Create: `web/package.json`
- Create: `web/index.html`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/src/main.tsx`
- Create: `web/src/api.ts`
- Create: `web/src/types.ts`
- Create: `web/src/App.tsx`
- Create: `web/src/components/TaskForm.tsx`
- Create: `web/src/components/Timeline.tsx`
- Create: `web/src/components/ApprovalPanel.tsx`
- Create: `web/src/components/TaskSummary.tsx`
- Create: `web/src/styles.css`
- Create: `web/src/App.test.tsx`
- Create: `web/e2e/app.spec.ts`

**Interfaces:**
- Consumes: FastAPI REST and SSE endpoints from Task 13
- Produces: first-screen usable control console, not a marketing page
- Produces: WebUI views for task creation, event timeline, approval, and result summary

- [ ] **Step 1: Write failing React test**

Create `web/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders task console controls", async () => {
    render(<App />);

    expect(screen.getByLabelText(/workspace/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/goal/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start task/i })).toBeInTheDocument();
  });

  it("shows validation when goal is empty", async () => {
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: /start task/i }));

    expect(screen.getByText(/goal is required/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm install && npm test -- --run`

Expected: FAIL because WebUI files do not exist.

- [ ] **Step 3: Implement WebUI**

Required UI behavior:

- first viewport is the actual task console;
- no landing page and no marketing hero;
- compact, high-density layout suitable for long-running developer work;
- task form posts to `POST /api/tasks`;
- timeline consumes `/api/tasks/{id}/events/stream`;
- approval buttons call `POST /api/approvals/{id}/decision`;
- responsive layout has no overlapping text at 390px mobile width and 1440px desktop width.

Use neutral grays plus distinct status colors; avoid one-note purple/blue gradient styling.

- [ ] **Step 4: Run unit and visual checks**

Run:

```bash
cd web && npm test -- --run
cd web && npm run build
```

Expected: both commands PASS.

If Playwright is configured in this task, run:

```bash
cd web && npm run e2e
```

Expected: PASS with desktop and mobile smoke screenshots.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat: add react task console"
```

---

### Task 17: Packaging, CI, and Mechanism Demo

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.gitlab-ci.yml`
- Create: `demos/mock_feedback_loop.py`
- Modify: `README.md`
- Modify: `AGENT_LOG.md`
- Modify: `SPEC_PROCESS.md`

**Interfaces:**
- Produces: `make verify`
- Produces: GitLab job named `unit-test`
- Produces: deterministic demo covering guardrail, feedback loop, and memory/hook or SubAgent mechanism

- [ ] **Step 1: Write failing CI/demo smoke test**

Create a pytest smoke test in `tests/integration/test_demo_script.py`:

```python
import subprocess
import sys


def test_mock_feedback_demo_runs() -> None:
    result = subprocess.run([sys.executable, "demos/mock_feedback_loop.py"], capture_output=True, text=True, timeout=30)

    assert result.returncode == 0
    assert "guardrail=denied" in result.stdout
    assert "feedback_loop=succeeded" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_demo_script.py -q`

Expected: FAIL because `demos/mock_feedback_loop.py` does not exist.

- [ ] **Step 3: Implement deterministic demo and CI**

`demos/mock_feedback_loop.py` must:

1. construct a `PolicyEngine` and show `git reset --hard` is denied;
2. run `LoopController` with Mock LLM where first check fails and second check passes;
3. show either verified memory enters context or a Hook blocks premature completion;
4. print:

```text
guardrail=denied
feedback_loop=succeeded
focus_mechanism=passed
```

`.gitlab-ci.yml` must contain:

```yaml
stages:
  - test

unit-test:
  stage: test
  image: python:3.12
  script:
    - pip install -e ".[dev]"
    - make verify
```

`.github/workflows/ci.yml` must run:

- `pip install -e ".[dev]"`
- `make verify`
- `cd web && npm ci && npm test -- --run && npm run build`
- a credentials scan command that fails on committed `.env` or obvious `sk-` style secrets.

- [ ] **Step 4: Run full verification**

Run:

```bash
make verify
pytest tests/integration/test_demo_script.py -q
```

If WebUI exists:

```bash
cd web && npm test -- --run && npm run build
```

Expected: all commands PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml .gitlab-ci.yml demos/mock_feedback_loop.py tests/integration/test_demo_script.py README.md AGENT_LOG.md SPEC_PROCESS.md
git commit -m "chore: add ci packaging and mechanism demo"
```

---

## Dependencies and Parallelization

- Task 1 must be first.
- Tasks 2 and 3 can run after Task 1.
- Task 4 depends on Task 2 and partially on Task 3.
- Task 5 depends on Task 4.
- Task 6 depends on Task 2 and Task 5.
- Task 7 depends on Task 2.
- Task 8 depends on Task 2 and Task 6.
- Task 9 depends on Task 2, Task 3, and Task 6.
- Task 10 depends on Tasks 3, 4, 6, 7, 8, and 9.
- Task 11 depends on Task 2 and can run parallel with Task 10 after Task 8.
- Task 12 depends on Tasks 2 and 8.
- Task 13 depends on Tasks 10 and 12.
- Task 14 depends on Task 13 for task commands and can partially run after Task 1 for auth.
- Task 15 depends on Task 13.
- Task 16 depends on Task 13.
- Task 17 depends on all prior tasks.

Recommended worktree grouping:

- `core-foundation`: Tasks 1-4
- `execution-feedback`: Tasks 5-10
- `state-subagents`: Tasks 11-12
- `interfaces`: Tasks 13-16
- `delivery`: Task 17

---

## Self-Review

**Spec coverage:** This plan covers the required Harness dimensions: decision loop (Tasks 7, 10), tools (Tasks 4, 5), governance/HITL (Task 3), feedback (Task 6), memory/context (Task 8), configuration and credentials (Task 14), SubAgent (Task 11), Hook (Task 9), API/TUI/WebUI (Tasks 13, 15, 16), distribution/CI/demo (Task 17). Course-specific requirements for mock-LLM deterministic tests, mechanism demo, GitLab `unit-test`, package distribution, keyring auth, and public WebUI preparation are represented.

**Placeholder scan:** Passed. Each code-changing task includes failing test content, expected failure, implementation contract, passing command, and commit command.

**Type consistency:** Shared names are consistent across tasks: `Task`, `LoopSpec`, `AgentDecision`, `ToolAction`, `ToolResult`, `FeedbackSignal`, `PolicyEngine`, `ToolExecutor`, `ContextBuilder`, `HookRunner`, `SubAgentScheduler`, `SQLiteStore`, and `LoopController`.

**TDD compliance:** The plan now has an explicit TDD Execution Contract. Existing task steps already contain a failing test, a red verification command, a minimal implementation section, a green verification command, and a commit command; execution must additionally record red/green evidence in `AGENT_LOG.md`.

**Known implementation risk:** The full WebUI and TUI may be larger than a single 2-5 minute step, but the task boundary is still reviewable as one interface deliverable. During execution, split internal commits only if a reviewer can meaningfully approve one UI slice while rejecting another, and preserve the red-green-refactor cycle for each slice.
