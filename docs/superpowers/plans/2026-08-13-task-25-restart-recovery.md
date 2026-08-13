# Task 25：服务重启后的任务隔离与显式恢复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施。步骤使用 checkbox（`- [ ]`）跟踪。

**目标：** 服务重启后将未终态任务安全隔离为 `needs_review`，并允许用户在明确知情的情况下从头重新运行可恢复任务。

**架构：** SQLite 新增恢复描述记录，保存任务可恢复性、恢复原因和仅 Mock 使用的决策序列。`TaskManager` 初始化时原子隔离遗留任务；显式恢复重新通过 ProviderFactory 构造 Provider 并创建全新内存 runtime，不复用旧 worker 或旧审批。API、TUI 与 WebUI 读取统一恢复摘要并显示“从头重新执行”的安全语义。

**技术栈：** Python 3.12、Pydantic、SQLite、FastAPI、Typer、Textual、React、TypeScript、pytest、Vitest。

## 全局约束

- 服务启动时绝不自动重放结果未知的工具调用；`pending`、`running`、`waiting_approval` 统一隔离到 `needs_review`。
- 显式恢复只能从头开始一次新的运行尝试，不实现检查点续跑、跨进程 worker 接管、工具幂等性推断或自动恢复。
- Mock 仅持久化 `AgentDecision` 序列；非 Mock 仅持久化 Provider 档案名称，绝不写入密钥、Authorization、Provider 响应正文或内存运行时状态。
- workspace 或 Provider 不可用时，恢复拒绝且任务保持 `needs_review`，不创建 worker、不执行工具调用、不写入 `recovery_started`。
- 启动隔离幂等：同一任务最多有一条 `recovery_required` 事件；事件序号在任务内严格递增。
- API、TUI、WebUI 文案使用中文；默认测试不读取 keyring、不访问真实 Provider 网络。
- 不修改既有 Task API/SSE 事件格式、SQLite 既有数据、Policy Engine 或审批状态机的既有语义，只新增恢复字段和事件。

---

## 文件结构

- `src/code_agent/core/models.py`：定义 `TaskRecovery` 的持久化模型和任务详情可消费的恢复字段。
- `src/code_agent/storage.py`：保存、读取和原子隔离恢复描述；保持 SQLite 向后兼容。
- `src/code_agent/application/task_manager.py`：启动隔离、从头恢复、旧审批冲突处理和恢复事件。
- `src/code_agent/api/app.py`：创建时持久化恢复输入，详情响应暴露恢复摘要，恢复路由重新构造 Provider。
- `src/code_agent/api/schemas.py`：保持请求模型约束，增加恢复详情响应所需的类型注释（若当前模型用于该输出）。
- `src/code_agent/tui/screens.py`、`src/code_agent/tui/app.py`：显示恢复原因和“从头重新执行”说明。
- `web/src/types.ts`、`web/src/components/TaskSummary.tsx`、`web/src/App.tsx`：显示恢复警告，并仅向可恢复任务提供带说明的恢复操作。
- `tests/integration/test_storage.py`、`tests/integration/test_task_manager.py`、`tests/integration/test_api_sse.py`、`tests/integration/test_tui.py`、`web/src/App.test.tsx`：分别验证存储、运行时、API、TUI 与 WebUI 契约。
- `AGENT_LOG.md`、`SPEC_PROCESS.md`：记录红绿证据、验证结果和不实现的恢复边界。

### Task 1：恢复描述存储与幂等启动隔离

**文件：**

- 修改：`src/code_agent/core/models.py`
- 修改：`src/code_agent/storage.py`
- 测试：`tests/integration/test_storage.py`

**接口：**

- 产生：`TaskRecovery(required: bool, reason: str | None, mock_decisions: list[AgentDecision] | None)`。
- 产生：`SQLiteStore.save_recovery(task_id: str, recovery: TaskRecovery) -> None`。
- 产生：`SQLiteStore.get_recovery(task_id: str) -> TaskRecovery | None`。
- 产生：`SQLiteStore.isolate_interrupted_tasks() -> list[Task]`，只隔离三种非终态任务，并为每个新隔离任务追加一条 `recovery_required`。

- [ ] **步骤 1：写失败存储测试**

```python
def test_isolate_interrupted_tasks_marks_only_non_terminal_tasks_once(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    pending = Task(workspace=str(tmp_path), goal="pending")
    running = Task(workspace=str(tmp_path), goal="running", status=TaskStatus.RUNNING)
    finished = Task(workspace=str(tmp_path), goal="done", status=TaskStatus.SUCCEEDED)
    for task in (pending, running, finished):
        store.create_task(task, LoopSpec(goal=task.goal))

    isolated = store.isolate_interrupted_tasks()

    assert {task.id for task in isolated} == {pending.id, running.id}
    assert store.get_task(pending.id).status is TaskStatus.NEEDS_REVIEW
    assert store.get_task(finished.id).status is TaskStatus.SUCCEEDED
    assert store.get_recovery(pending.id).reason == "服务重启后需人工复核"
    assert [event.type for event in store.events_after(pending.id, 0)] == ["recovery_required"]
    assert store.isolate_interrupted_tasks() == []
```

- [ ] **步骤 2：运行红灯测试**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_storage.py -q`

预期：因 `TaskRecovery`、`get_recovery` 与 `isolate_interrupted_tasks` 不存在而失败。

- [ ] **步骤 3：实现最小持久化与隔离操作**

```python
class TaskRecovery(BaseModel):
    required: bool = False
    reason: str | None = None
    mock_decisions: list[AgentDecision] | None = None

def isolate_interrupted_tasks(self) -> list[Task]:
    interrupted = {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL}
    isolated: list[Task] = []
    with self._lock:
        for task in self.list_tasks():
            if task.status not in interrupted or self.get_recovery(task.id) is not None:
                continue
            reviewed = task.model_copy(update={"status": TaskStatus.NEEDS_REVIEW})
            self._write_task(reviewed)
            self._write_recovery(task.id, TaskRecovery(required=True, reason="服务重启后需人工复核"))
            self._append_event_locked(task.id, "recovery_required", {"reason": "服务重启后需人工复核"})
            isolated.append(reviewed)
        self.connection.commit()
    return isolated
```

在 `create_task` 中可选接收 `recovery: TaskRecovery | None` 并持久化；SQLite 表通过 `CREATE TABLE IF NOT EXISTS recoveries(task_id TEXT PRIMARY KEY, data TEXT)` 向后兼容创建。将 `update_task`、写恢复记录与事件追加拆成私有的锁内辅助方法，避免同一 `RLock` 中过早提交。

- [ ] **步骤 4：运行绿灯与静态检查**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_storage.py -q; .\.venv\Scripts\ruff.exe check src/code_agent/storage.py src/code_agent/core/models.py tests/integration/test_storage.py; .\.venv\Scripts\mypy.exe src`

预期：存储测试、Ruff 与 Mypy 通过。

- [ ] **步骤 5：提交**

```powershell
git add src/code_agent/core/models.py src/code_agent/storage.py tests/integration/test_storage.py
git commit -m "feat: persist restart recovery state"
```

### Task 2：TaskManager 启动隔离与从头新执行恢复

**文件：**

- 修改：`src/code_agent/application/task_manager.py`
- 修改：`src/code_agent/storage.py`
- 测试：`tests/integration/test_task_manager.py`

**接口：**

- 消费：`SQLiteStore.isolate_interrupted_tasks()`、`get_recovery()`、`get_spec()`。
- 产生：`TaskManager.recover(task_id: str, provider: LLMProvider) -> Task`。
- 产生：恢复事件 `recovery_started`，其 payload 为 `{"reason": "用户确认从头重新执行"}`。

- [ ] **步骤 1：写失败运行时测试**

```python
def test_manager_startup_isolates_then_mock_recovery_restarts_from_beginning(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = Task(workspace=str(tmp_path), goal="recover", status=TaskStatus.RUNNING)
    decisions = [AgentDecision(action="complete", completion_message="recovered")]
    store.create_task(task, LoopSpec(goal="recover"), TaskRecovery(mock_decisions=decisions))

    manager = TaskManager(store)

    assert store.get_task(task.id).status is TaskStatus.NEEDS_REVIEW
    manager.recover(task.id, MockLLMProvider(decisions))
    wait_until(lambda: store.get_task(task.id).status is TaskStatus.SUCCEEDED)
    assert [event.type for event in store.events_after(task.id, 0)] == [
        "recovery_required", "recovery_started", "task_completed"
    ]
    manager.shutdown()

def test_recover_rejects_non_recovery_task_without_creating_runtime(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = Task(workspace=str(tmp_path), goal="review", status=TaskStatus.NEEDS_REVIEW)
    store.create_task(task, LoopSpec(goal="review"))
    manager = TaskManager(store)

    with pytest.raises(ValueError, match="not restart-recoverable"):
        manager.recover(task.id, MockLLMProvider([]))

    assert task.id not in manager._runtimes
    manager.shutdown()
```

- [ ] **步骤 2：运行红灯测试**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_task_manager.py -q`

预期：因构造函数未隔离任务且 `recover` 不存在而失败。

- [ ] **步骤 3：实现启动隔离与恢复 runtime**

```python
def __init__(self, store: SQLiteStore, max_workers: int = 4) -> None:
    self.store = store
    self.executor = ThreadPoolExecutor(max_workers=max_workers)
    self._runtimes = {}
    self._lock = RLock()
    self.store.isolate_interrupted_tasks()

def recover(self, task_id: str, provider: LLMProvider) -> Task:
    task = self.store.get_task(task_id)
    recovery = self.store.get_recovery(task_id)
    spec = self.store.get_spec(task_id)
    if task is None or recovery is None or not recovery.required or spec is None:
        raise ValueError(f"task {task_id} is not restart-recoverable")
    if task.status is not TaskStatus.NEEDS_REVIEW:
        raise ValueError(f"task {task_id} is not awaiting recovery")
    running = task.model_copy(update={"status": TaskStatus.RUNNING})
    self.store.update_task(running)
    self.store.save_recovery(task_id, recovery.model_copy(update={"required": False}))
    self.store.append_event(task_id, "recovery_started", {"reason": "用户确认从头重新执行"})
    self._start_runtime(running, spec, provider)
    return running
```

让 `submit` 和 `recover` 共用 `_start_runtime(task, spec, provider)`；恢复路径只在所有前置检查通过后才写状态/事件。`decide_approval` 对没有 runtime 的遗留审批继续返回冲突，绝不为其创建 `_Runtime`。

- [ ] **步骤 4：运行绿灯与回归**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_task_manager.py tests/unit/test_loop.py tests/unit/test_loop_approvals.py -q; .\.venv\Scripts\ruff.exe check src/code_agent/application/task_manager.py tests/integration/test_task_manager.py; .\.venv\Scripts\mypy.exe src`

预期：重启隔离、Mock 从头恢复、审批冲突和既有循环测试均通过。

- [ ] **步骤 5：提交**

```powershell
git add src/code_agent/application/task_manager.py src/code_agent/storage.py tests/integration/test_task_manager.py
git commit -m "feat: isolate interrupted tasks on restart"
```

### Task 3：API 恢复输入、详情摘要与安全拒绝

**文件：**

- 修改：`src/code_agent/api/app.py`
- 修改：`src/code_agent/api/schemas.py`
- 修改：`tests/integration/test_api_sse.py`

**接口：**

- 消费：`TaskRecovery`、`TaskManager.recover(task_id, provider)`、`build_provider()`。
- 产生：任务详情字段 `recovery_required: bool`、`recovery_reason: str | null`、`resumable: bool`。
- 产生：`POST /api/tasks/{task_id}/resume` 对 restart-recoverable 任务从头运行。

- [ ] **步骤 1：写失败 API 测试**

```python
def test_restart_recovery_api_exposes_reason_and_restarts_mock_task(tmp_path) -> None:
    state_path = tmp_path / "state.db"
    seed = SQLiteStore(state_path)
    task = Task(workspace=str(tmp_path), goal="recover", status=TaskStatus.RUNNING, provider="mock")
    decisions = [AgentDecision(action="complete", completion_message="done")]
    seed.create_task(task, LoopSpec(goal="recover"), TaskRecovery(mock_decisions=decisions))

    with TestClient(create_app(state_path=state_path)) as client:
        detail = client.get(f"/api/tasks/{task.id}").json()
        assert detail["status"] == "needs_review"
        assert detail["recovery_required"] is True
        assert detail["recovery_reason"] == "服务重启后需人工复核"
        assert detail["resumable"] is True
        assert client.post(f"/api/tasks/{task.id}/resume").status_code == 200
        wait_for_status(client, task.id, "succeeded")

def test_restart_recovery_rejects_missing_workspace_without_starting_worker(tmp_path) -> None:
    state_path = tmp_path / "state.db"
    missing_workspace = tmp_path / "missing"
    seed = SQLiteStore(state_path)
    task = Task(workspace=str(missing_workspace), goal="recover", status=TaskStatus.RUNNING, provider="mock")
    seed.create_task(task, LoopSpec(goal="recover"), TaskRecovery(mock_decisions=[]))

    with TestClient(create_app(state_path=state_path)) as client:
        response = client.post(f"/api/tasks/{task.id}/resume")
        assert response.status_code == 409
        assert client.get(f"/api/tasks/{task.id}").json()["status"] == "needs_review"
        assert all(event.type != "recovery_started" for event in seed.events_after(task.id, 0))
```

- [ ] **步骤 2：运行红灯测试**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -q`

预期：详情缺少恢复字段，且恢复路由仍按旧 `waiting_approval` 语义失败。

- [ ] **步骤 3：实现 API 运行输入持久化与恢复路由**

```python
recovery = TaskRecovery(
    mock_decisions=request.mock_decisions if provider_name == "mock" else None
)
app.state.manager.submit(task, spec, provider, recovery=recovery)

@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str) -> dict[str, object]:
    task = _require_task(task_id, app.state.store)
    workspace = Path(task.workspace).resolve()
    if not workspace.is_dir():
        raise HTTPException(status_code=409, detail="恢复工作区不可用")
    recovery = app.state.store.get_recovery(task_id)
    try:
        provider, _ = build_provider(task.provider, workspace, mock_decisions=recovery.mock_decisions)
        return _task_response(app.state.manager.recover(task_id, provider), [])
    except (ProviderFactoryError, ValueError):
        raise HTTPException(status_code=409, detail="任务当前无法安全恢复") from None
```

在 `_task_response` 中从 store 获取恢复记录，并仅当 `status == needs_review and recovery.required` 时设置 `resumable=True`。`TaskManager.submit` 新增关键字参数 `recovery: TaskRecovery`，以便创建时保存 Mock 决策；保留原调用的默认值兼容性。

- [ ] **步骤 4：运行绿灯、API 回归与静态检查**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py tests/integration/test_task_manager.py -q; .\.venv\Scripts\ruff.exe check src/code_agent/api tests/integration/test_api_sse.py; .\.venv\Scripts\mypy.exe src`

预期：API 详情、Mock 恢复、workspace 拒绝、既有 SSE 生命周期和静态检查均通过。

- [ ] **步骤 5：提交**

```powershell
git add src/code_agent/api/app.py src/code_agent/api/schemas.py src/code_agent/application/task_manager.py tests/integration/test_api_sse.py
git commit -m "feat: expose safe restart recovery api"
```

### Task 4：TUI 与 WebUI 恢复提示

**文件：**

- 修改：`src/code_agent/tui/screens.py`
- 修改：`src/code_agent/tui/app.py`
- 修改：`tests/integration/test_tui.py`
- 修改：`web/src/types.ts`
- 修改：`web/src/components/TaskSummary.tsx`
- 修改：`web/src/App.tsx`
- 修改：`web/src/App.test.tsx`

**接口：**

- 消费：任务详情中的 `recovery_required`、`recovery_reason`、`resumable`。
- 产生：中文提示“服务重启后需人工复核”和“将从头重新执行”。

- [ ] **步骤 1：写失败 TUI 与 WebUI 测试**

```python
async def test_recovery_required_result_explains_restart_semantics() -> None:
    client = RuntimeTaskApiClient(
        status="needs_review",
        recovery_required=True,
        recovery_reason="服务重启后需人工复核",
        resumable=True,
    )
    app = CodeAgentTui(client=client)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "服务重启后需人工复核" in app.screen.query_one("#result-summary").renderable
        assert "从头重新执行" in app.screen.query_one("#recovery-hint").renderable
```

```tsx
it("explains that restart recovery reruns from the beginning", async () => {
  mockGetTask.mockResolvedValue({
    id: "task-1", status: "needs_review", recovery_required: true,
    recovery_reason: "服务重启后需人工复核", resumable: true, pending_approvals: [],
  });
  render(<App initialTaskId="task-1" />);
  expect(await screen.findByText("服务重启后需人工复核")).toBeVisible();
  expect(screen.getByText("恢复将从头重新执行")).toBeVisible();
});
```

- [ ] **步骤 2：运行红灯测试**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_tui.py -q; Set-Location web; npm.cmd test -- --run src/App.test.tsx; Set-Location ..`

预期：假客户端、TypeScript 类型和组件均缺少恢复摘要字段/提示而失败。

- [ ] **步骤 3：实现最小客户端提示**

```tsx
{task.recovery_required && (
  <p role="status">
    {task.recovery_reason ?? "服务重启后需人工复核"}；恢复将从头重新执行。
  </p>
)}
```

将恢复按钮仅用于 `task.resumable === true` 的 restart-recoverable 任务；既有已取消任务的恢复控件保持原行为或改为由 API 返回的 `resumable` 明确区分，不能把任意 `needs_review` 误标为可恢复。Textual 在结果屏使用同样的两段中文文案，并保持 API 错误时仅通知、不改变当前屏幕。

- [ ] **步骤 4：运行绿灯与构建**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_tui.py -q; Set-Location web; npm.cmd test -- --run; npm.cmd run build; Set-Location ..`

预期：TUI 测试、Vitest 与 TypeScript/Vite build 通过。

- [ ] **步骤 5：提交**

```powershell
git add src/code_agent/tui tests/integration/test_tui.py web/src/types.ts web/src/components/TaskSummary.tsx web/src/App.tsx web/src/App.test.tsx
git commit -m "feat: explain restart recovery in clients"
```

### Task 5：完整验收与中文过程记录

**文件：**

- 修改：`AGENT_LOG.md`
- 修改：`SPEC_PROCESS.md`

**接口：**

- 消费：Task 1-4 的恢复存储、运行时、API 与客户端契约。
- 产生：中文红绿证据、重启恢复验收结论和明确的非目标说明。

- [ ] **步骤 1：写端到端失败验收**

在 `tests/integration/test_api_sse.py` 添加一条覆盖完整重启流程的测试：用一个应用创建等待审批的 Mock 任务，关闭该应用，用同一 `state.db` 创建新应用，断言任务变为 `needs_review`、旧审批决定为 `409`、详情有恢复提示；随后 `resume` 并等待新执行终态，断言事件序号严格递增且包含 `recovery_required`、`recovery_started`、`task_completed`。

- [ ] **步骤 2：运行红灯验收**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -q`

预期：在 Task 1-4 尚未全部完成时，至少因启动隔离、详情字段或恢复事件缺失而失败。

- [ ] **步骤 3：补足最小验收实现并记录实际行为**

只修复端到端测试暴露的 Task 1-4 契约缺口；不得增加自动重放、检查点续跑或真实 Provider E2E。将实际 RED/GREEN 命令、测试数量、既有警告及“恢复从头执行”的边界写入中文过程文档。

- [ ] **步骤 4：运行最终验证**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest -q; .\.venv\Scripts\ruff.exe check .; .\.venv\Scripts\mypy.exe src; Set-Location web; npm.cmd test -- --run; npm.cmd run build; Set-Location ..`

预期：全部 Python 测试、Ruff、Mypy、Vitest 与 Vite build 成功；既有 FastAPI/Starlette 或 Vite 警告如实记录，但不包含失败。

- [ ] **步骤 5：提交**

```powershell
git add AGENT_LOG.md SPEC_PROCESS.md tests/integration/test_api_sse.py
git commit -m "docs: record task restart recovery verification"
```

## 计划自检

- 规格覆盖：Task 1 实现持久化与幂等隔离；Task 2 实现启动与从头运行 runtime；Task 3 实现 API、Provider/workspace 安全拒绝；Task 4 实现 TUI/WebUI 提示；Task 5 覆盖重启端到端验收与中文记录。
- 类型一致性：所有后续任务只使用 Task 1 定义的 `TaskRecovery`、Task 2 定义的 `TaskManager.recover` 和 Task 3 固定的详情字段。
- 范围检查：计划没有自动重放、检查点续跑、跨进程 worker 接管或真实 Provider E2E。
