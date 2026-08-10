# Task 19：任务 API 生命周期与实时审批实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施。每一步使用 checkbox（`- [ ]`）跟踪。

**目标：** 为 Mock Provider 增加异步任务生命周期 API、实时审批和可断线恢复的 SSE 事件流。

**架构：** FastAPI 通过进程内 `TaskManager` 创建任务并提交 `ThreadPoolExecutor` worker；worker 调用现有核心循环，审批时将 pending 记录写入 SQLite 并通过 `Condition` 等待 API 决定。SQLite 持久化任务、LoopSpec、审批和有序事件，SSE 先回放事件再等待新事件。

**技术栈：** Python 3.12+、FastAPI、Pydantic、SQLite、ThreadPoolExecutor、threading、pytest、Ruff、Mypy。

## 全局约束

- 本阶段只支持单机、单进程、Mock Provider；不实现 TUI、WebUI、真实 Provider、SubAgent 或跨进程恢复。
- `POST /api/tasks` 必须立即返回，不得等待 worker 运行完成。
- SSE 客户端断开不得取消任务；客户端通过 `after=N` 恢复事件。
- 硬性禁止动作永远不创建审批；重复审批、终态操作返回 `409`。
- 所有行为遵循红灯、最小实现、绿灯、回归检查的 TDD 顺序。
- 不修改用户已有的未跟踪 `.idea/` 目录；文档和过程记录使用中文。

---

## 文件结构

- `src/code_agent/api/schemas.py`：任务创建、任务详情、取消/恢复、审批决定的 API 模型。
- `src/code_agent/api/app.py`：生命周期、任务查询、取消、恢复、审批和 SSE 路由。
- `src/code_agent/application/task_manager.py`：线程池、运行上下文、审批等待、取消信号、事件广播。
- `src/code_agent/application/task_service.py`：保持 CLI 同步闭环，同时提供 TaskManager 可注入的审批/事件协调接口。
- `src/code_agent/core/loop.py`：增加取消检查和审批等待所需的回调边界。
- `src/code_agent/core/models.py`：为 `Approval` 增加任务关联字段，为任务详情提供稳定序列化模型。
- `src/code_agent/storage.py`：增加线程锁、LoopSpec 查询、任务审批查询和原子审批决定。
- `tests/integration/test_storage.py`：存储关联、并发写入和审批状态测试。
- `tests/integration/test_task_manager.py`：后台运行、等待审批、唤醒、拒绝、取消测试。
- `tests/integration/test_api_sse.py`：REST、SSE 回放/实时推送和错误状态测试。
- `SPEC_PROCESS.md`：追加 Task 19 的实施和验证证据。

## 任务依赖

```text
Task 1 存储与领域接口
          │
          ├── Task 2 TaskManager 与可取消/可审批 Loop
          │             │
          └─────────────┴── Task 3 API 路由与 SSE
                                  │
                                  └── Task 4 完整回归、文档与验收
```

### Task 1：扩展领域模型与 SQLite 并发存储

**文件：**

- 修改：`src/code_agent/core/models.py`
- 修改：`src/code_agent/storage.py`
- 修改：`tests/integration/test_storage.py`

**接口：**

- `Approval.task_id: str | None = None`
- `SQLiteStore.get_spec(task_id: str) -> LoopSpec | None`
- `SQLiteStore.list_pending_approvals(task_id: str) -> list[Approval]`
- `SQLiteStore.decide_approval(approval_id: str, approved: bool, scope: Literal["once", "task"], actor: str) -> Approval`
- `SQLiteStore.get_task(task_id: str) -> Task | None`
- `SQLiteStore.update_task(task: Task) -> Task`

- [ ] **步骤 1：编写失败测试**

在 `tests/integration/test_storage.py` 追加：

```python
from threading import Thread

from code_agent.core.models import Approval, LoopSpec, Task


def test_approval_roundtrip_keeps_task_id_and_decision(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    approval = store.save_approval(
        Approval(task_id=task.id, tool_call_id="tool-1", reason="shell requires approval")
    )

    decided = store.decide_approval(approval.id, approved=True, scope="task", actor="api")

    assert decided.task_id == task.id
    assert decided.status == "approved"
    assert store.list_pending_approvals(task.id) == []


def test_concurrent_event_writes_keep_unique_order(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    errors: list[Exception] = []

    def append() -> None:
        try:
            store.append_event(task.id, "feedback", {})
        except Exception as exc:
            errors.append(exc)

    threads = [Thread(target=append) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert [event.sequence for event in store.events_after(task.id, 0)] == list(range(1, 9))
```

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_storage.py -q
```

预期：因 `Approval.task_id`、`get_spec`/pending 查询、原子审批决定或并发保护缺失而失败。

- [ ] **步骤 3：实现最小存储改动**

为 `Approval` 增加默认值为 `None` 的 `task_id`，保持现有 CLI 测试兼容。为 `SQLiteStore` 增加实例级 `RLock`，将读写数据库的方法包在同一把锁中；连接继续使用 `check_same_thread=False`。实现：

```python
def get_spec(self, task_id: str) -> LoopSpec | None:
    row = self.connection.execute("SELECT data FROM specs WHERE task_id = ?", (task_id,)).fetchone()
    return LoopSpec.model_validate_json(row[0]) if row else None


def list_pending_approvals(self, task_id: str) -> list[Approval]:
    rows = self.connection.execute("SELECT data FROM approvals ORDER BY rowid").fetchall()
    return [
        approval
        for (data,) in rows
        if (approval := Approval.model_validate_json(data)).task_id == task_id
        and approval.status == "pending"
    ]
```

`decide_approval` 必须在锁内读取当前记录，若不存在抛出 `KeyError`，若状态不是 `pending` 抛出 `ValueError`，再以 `model_copy` 更新并提交；不覆盖既有决定。

- [ ] **步骤 4：运行绿灯与既有存储测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_storage.py -q
```

预期：全部通过。

- [ ] **步骤 5：提交**

```powershell
git add src/code_agent/core/models.py src/code_agent/storage.py tests/integration/test_storage.py
git commit -m "feat: make task storage safe for api workers"
```

### Task 2：实现 TaskManager 与可取消、可等待审批的运行时

**文件：**

- 创建：`src/code_agent/application/task_manager.py`
- 修改：`src/code_agent/core/loop.py`
- 修改：`src/code_agent/application/task_service.py`
- 创建：`tests/integration/test_task_manager.py`

**接口：**

- `TaskManager(store: SQLiteStore, max_workers: int = 4)`
- `TaskManager.submit(task: Task, loop_spec: LoopSpec, decisions: list[AgentDecision]) -> Task`
- `TaskManager.get_task(task_id: str) -> Task | None`
- `TaskManager.cancel(task_id: str) -> Task`
- `TaskManager.resume(task_id: str) -> Task`
- `TaskManager.decide_approval(approval_id: str, approved: bool, scope: Literal["once", "task"], actor: str) -> Approval`
- `TaskManager.wait_for_event(task_id: str, after: int, timeout: float) -> list[Event]`
- `TaskManager.shutdown() -> None`

- [ ] **步骤 1：编写失败测试**

在 `tests/integration/test_task_manager.py` 写入：

```python
import time

from code_agent.application.task_manager import TaskManager
from code_agent.core.models import AgentDecision, LoopSpec, PermissionMode, Task, ToolAction, TaskStatus
from code_agent.storage import SQLiteStore


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


def test_submit_runs_in_background_and_persists_terminal_status(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="complete", mode=PermissionMode.PLAN)
    spec = LoopSpec(goal="complete")

    manager.submit(task, spec, [AgentDecision(action="complete", completion_message="done")])
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.SUCCEEDED)

    assert store.events_after(task.id, 0)[-1].type == "task_completed"
    manager.shutdown()


def test_api_approval_wakes_waiting_worker(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="shell")
    spec = LoopSpec(goal="shell")
    manager.submit(task, spec, [
        AgentDecision(action="tool_call", tool_action=ToolAction(tool="shell", arguments={"command": "python -c \"pass\""})),
        AgentDecision(action="complete", completion_message="done"),
    ])

    wait_until(lambda: store.get_task(task.id).status == TaskStatus.WAITING_APPROVAL)
    approval = store.list_pending_approvals(task.id)[0]
    manager.decide_approval(approval.id, approved=True, scope="once", actor="api")
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.SUCCEEDED)
    manager.shutdown()
```

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_task_manager.py -q
```

预期：因缺少 `TaskManager` 和 Loop 取消/审批协作接口而失败。

- [ ] **步骤 3：实现最小运行时**

`TaskManager.submit` 先写入任务和 LoopSpec，将任务状态改为 `running`，再提交 worker。worker 构造现有 `MockLLMProvider`、`PolicyEngine`、`ToolExecutor` 和 `FeedbackAdapter`，通过注入的审批回调执行循环；每个 Loop 事件立即写入 SQLite 并通知事件 condition，最终更新任务并写入 `task_completed`。

审批回调创建 `Approval(task_id=task.id, tool_call_id=uuid4(), reason=...)`，更新任务为 `waiting_approval`，等待对应 condition；收到决定后返回 `ApprovalResolution`，worker 将状态改回 `running`。取消回调检查 `threading.Event`，在每次迭代和审批等待中返回 `cancelled`，不得中断正在执行的危险子进程。

修改 `LoopController.run` 增加可选 `cancel_check: Callable[[], bool] | None`，每轮开始、工具调用后和验收前检查；取消时返回 `TaskRunResult(status=TaskStatus.CANCELLED, ...)`。保留现有无参数调用兼容性。

- [ ] **步骤 4：运行绿灯与核心回归**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_task_manager.py tests/unit/test_loop.py tests/unit/test_loop_approvals.py -q
```

预期：全部通过。

- [ ] **步骤 5：提交**

```powershell
git add src/code_agent/application/task_manager.py src/code_agent/application/task_service.py src/code_agent/core/loop.py tests/integration/test_task_manager.py
git commit -m "feat: run tasks asynchronously with api approvals"
```

### Task 3：接入 REST 生命周期接口和实时 SSE

**文件：**

- 修改：`src/code_agent/api/schemas.py`
- 修改：`src/code_agent/api/app.py`
- 修改：`tests/integration/test_api_sse.py`

**接口：**

- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/resume`
- `GET /api/tasks/{task_id}/events?after=N`
- `GET /api/tasks/{task_id}/events/stream?after=N`
- `POST /api/approvals/{approval_id}/decision`

- [ ] **步骤 1：编写失败 API 测试**

在 `tests/integration/test_api_sse.py` 追加覆盖：

```python
def test_create_task_returns_before_worker_finishes(tmp_path) -> None:
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    response = client.post("/api/tasks", json={
        "workspace": str(tmp_path),
        "goal": "complete",
        "provider": "mock",
        "mock_decisions": [{"action": "complete", "completion_message": "done"}],
    })
    assert response.status_code == 201
    assert response.json()["id"]


def test_approval_endpoint_decides_pending_approval(tmp_path) -> None:
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    response = client.post("/api/tasks", json={
        "workspace": str(tmp_path),
        "goal": "shell",
        "mock_decisions": [
            {"action": "tool_call", "tool_action": {"tool": "shell", "arguments": {"command": "python -c \"pass\""}}},
            {"action": "complete", "completion_message": "done"},
        ],
    })
    task_id = response.json()["id"]
    wait_for_status(client, task_id, "waiting_approval")
    approval_id = client.get(f"/api/tasks/{task_id}").json()["pending_approvals"][0]["id"]

    decision = client.post(f"/api/approvals/{approval_id}/decision", json={"approved": True, "scope": "once"})

    assert decision.status_code == 200


def test_events_stream_replays_after_cursor_and_closes_at_terminal(tmp_path) -> None:
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    task_id = client.post("/api/tasks", json={
        "workspace": str(tmp_path),
        "goal": "complete",
        "mock_decisions": [{"action": "complete", "completion_message": "done"}],
    }).json()["id"]
    wait_for_status(client, task_id, "succeeded")

    with client.stream("GET", f"/api/tasks/{task_id}/events/stream?after=1") as response:
        body = response.read().decode()
    assert response.status_code == 200
    assert "id: 2" in body
    assert "event: task_completed" in body
```

`wait_for_status` 使用最多 2 秒、每 10ms 轮询 `GET /api/tasks/{id}`，超时即失败；测试不依赖固定线程调度顺序。

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -q
```

预期：因请求模型字段、生命周期路由、后台 manager 和阻塞 SSE 尚未实现而失败。

- [ ] **步骤 3：实现 API 与 SSE**

在 `schemas.py` 增加严格 `TaskCreate`（包含 `mock_decisions`）、`ApprovalDecisionRequest` 和响应模型。`create_app` 创建或接收 `SQLiteStore` 和 `TaskManager`，并在 FastAPI shutdown 事件中调用 `manager.shutdown()`。

`POST /api/tasks` 校验 provider、workspace 和决策，创建 Task/LoopSpec 后调用 `manager.submit`。`GET /api/tasks/{id}` 读取任务、spec 和 pending approvals。取消、恢复和审批路由将 manager 的 `KeyError` 映射为 `404`，状态冲突映射为 `409`。

SSE generator 维护 `cursor`：先读取 `events_after(task_id, cursor)`，没有新事件时调用 `manager.wait_for_event(task_id, cursor, timeout=0.5)`；每批事件逐条 yield，任务终态且无剩余事件时结束。生成器不在 `finally` 中取消任务。

- [ ] **步骤 4：运行 API 绿灯测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -q
```

预期：通过。

- [ ] **步骤 5：提交**

```powershell
git add src/code_agent/api/schemas.py src/code_agent/api/app.py tests/integration/test_api_sse.py
git commit -m "feat: expose task lifecycle and realtime approval api"
```

### Task 4：完整验证与过程记录

**文件：**

- 修改：`SPEC_PROCESS.md`

- [ ] **步骤 1：运行完整验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
```

预期：pytest、Ruff 和 Mypy 全部成功；允许记录既有第三方弃用警告，但不能有失败测试或类型错误。

- [ ] **步骤 2：执行端到端验收**

使用 `TestClient` 创建一个包含 shell 决策的 Mock 任务，确认任务进入 `waiting_approval`，通过审批 API 批准，确认任务进入终态；再从 `after=0` 和中间 cursor 读取事件，核对序号无重复且包含 `approval_requested`、`approval_decided` 和 `task_completed`。

- [ ] **步骤 3：更新过程记录**

在 `SPEC_PROCESS.md` 记录 Task 19 的规格路径、计划路径、每个 TDD 单元的红灯/绿灯命令、完整验证结果和已知边界（单进程 Mock、无跨进程恢复）。

- [ ] **步骤 4：提交验证记录**

```powershell
git add SPEC_PROCESS.md
git commit -m "docs: record task api lifecycle verification"
```

## 计划自检

- 规格覆盖：Task 1 覆盖领域字段、审批关联、SQLite 并发和事件序号；Task 2 覆盖后台 worker、审批等待、取消和运行结果；Task 3 覆盖所有 REST 路由、JSON 回放和 SSE；Task 4 覆盖全量验证与过程记录。
- 完整性检查：没有未完成占位语句、模糊实现指令或未定义的接口名称。
- 类型一致性：`TaskManager.decide_approval` 使用 `Approval.task_id` 关联 worker；`TaskManager.wait_for_event` 使用现有 `Event` 和 `events_after`；API 的 `mock_decisions` 直接产生 `list[AgentDecision]`；Loop 的 `cancel_check` 为可选回调，不破坏 Task 18 调用方。
