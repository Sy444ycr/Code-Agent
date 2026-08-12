# Task 21：Textual TUI 接入任务 API 设计

## 1. 目标与范围

Task 21 将现有仅含启动骨架的 Textual TUI 升级为浏览同一 Task 19 任务 API 的单任务终端控制台。用户可创建 Mock 任务、观察状态与事件、处理审批、取消或安全恢复，并查看终态结果。

本阶段范围：

- 使用 `POST /api/tasks` 创建 Mock 任务。
- 使用 `GET /api/tasks/{id}` 获取任务详情与 pending approvals。
- 以 `GET /api/tasks/{id}/events?after=N` 轮询事件并按 sequence 恢复。
- 调用审批、取消和恢复 API。
- 用 Textual 测试验证关键状态、快捷键和 API 请求。

本阶段不包含桌面 App、WebUI 改动、真实 Provider、跨进程任务恢复、多任务列表或 SubAgent 实际派发。

## 2. 方案选择

采用“详情轮询 + JSON 事件回放”，而不在 Textual 中直接维护 SSE HTTP 流。TUI 每 500ms 拉取任务详情并以最后已处理的 sequence 调用事件回放端点。该方案仍使用 Task 19 的同一事件模型，断线后可从游标恢复，同时保持 Textual 异步测试可重复且实现边界清晰。

SQLite 和 TaskManager 继续作为后端事实来源；TUI 不推断状态迁移、不修改本地任务状态，也不自行生成事件。

## 3. API 客户端边界

新增 `src/code_agent/tui/api.py`，定义可注入 `TaskApiClient`：

- `create_task(payload: dict[str, object]) -> dict[str, object]`
- `get_task(task_id: str) -> dict[str, object]`
- `events_after(task_id: str, after: int) -> list[dict[str, object]]`
- `decide_approval(approval_id: str, approved: bool, scope: Literal["once", "task"]) -> dict[str, object]`
- `cancel_task(task_id: str) -> dict[str, object]`
- `resume_task(task_id: str) -> dict[str, object]`

默认 API base URL 为 `http://127.0.0.1:8000`；请求失败时客户端提取后端 `detail`，抛出不含 traceback 的 `TaskApiError`。测试注入 fake client，避免真实网络与线程调度。

## 4. 屏幕与交互

### StartScreen

显示 workspace、goal、mode、Mock 决策 JSON 输入框和创建按钮。提交前验证必填项和 JSON 数组。创建成功后由 `CodeAgentTui` 保存 task ID、将 sequence 清零并进入 RunScreen。

### RunScreen

显示任务 ID、状态、目标、最近事件和连接/轮询状态。运行期间每 500ms 请求详情与新事件；只接收 sequence 严格大于本地游标的事件。快捷键：`c` 取消非终态任务；`r` 仅在服务端允许安全恢复时出现/生效。若详情含 pending approvals，自动切换到 ApprovalScreen。终态任务进入 ResultScreen。

### ApprovalScreen

显示审批理由与三种明确动作：`y` 允许一次（`scope=once`）、`a` 允许本任务（`scope=task`）、`n` 拒绝（`approved=false`，`scope=once`）。提交期间禁用重复输入；成功后返回 RunScreen，后续轮询呈现真实状态变化。

### ResultScreen

显示终态、任务 ID、最近事件摘要、报告/验证字段（若后端响应提供）。终态不再显示取消、恢复或审批动作；`q` 退出应用或返回启动页由现有 TUI 导航约定决定。

## 5. 轮询、恢复与错误处理

1. 首次进入 RunScreen 时，`after=0` 请求事件；每成功处理事件后将 sequence 设为该事件序号。
2. 后续轮询始终使用 `after=last_sequence`；服务器重放的旧事件被忽略，事件列表保持递增。
3. 网络/HTTP 错误显示 Textual 通知，保留现有任务详情、事件和 sequence，并在下一周期继续请求。
4. 创建、审批、取消和恢复的错误不改变本地任务状态；通知仅显示 API `detail` 或安全的通用文案。
5. 屏幕切换、任务切换或应用退出时取消轮询 worker，避免旧任务继续更新当前屏幕。

## 6. 测试与验收

新增或扩展 `tests/integration/test_tui.py`，以 fake `TaskApiClient` 覆盖：

1. 启动页包含任务创建字段；提交合法 Mock 任务后进入 RunScreen 并保存 task ID。
2. 非法 JSON 保留启动页并显示验证错误。
3. RunScreen 只追加递增 sequence 的事件；轮询使用最后 sequence 恢复。
4. pending approval 自动切换审批页；`y`、`a`、`n` 分别提交正确的 `approved/scope`。
5. `c` 调用取消；符合服务端允许条件时 `r` 调用恢复；终态不提供这些动作。
6. 终态进入 ResultScreen；客户端异常显示通知且不清空已有事件。

最终运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_tui.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
```

## 7. 文件边界

- 创建：`src/code_agent/tui/api.py`。
- 修改：`src/code_agent/tui/app.py`、`src/code_agent/tui/screens.py`、`tests/integration/test_tui.py`。
- 完成实施后修改：`SPEC_PROCESS.md`、`AGENT_LOG.md`，中文记录 TDD 与验证证据。

不修改 Task 19 后端 API、WebUI 文件，也不推进 Task 22。

## 8. 自检

- API 路由、审批 scope 与 Task 19 契约一致。
- 事件恢复基于服务端 sequence，不依赖本地时间戳。
- 页面仅属于 Textual TUI，所有非范围均已明确排除。
