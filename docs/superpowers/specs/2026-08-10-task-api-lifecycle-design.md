# Task 19：任务 API 生命周期与实时审批设计

## 1. 目标与范围

Task 19 为现有 Mock 任务闭环增加后端任务生命周期能力，使 FastAPI 客户端可以异步创建、查询、取消、恢复和观察任务，并通过 API 完成实时审批。

本阶段范围限定为：

- 单机、单进程、Mock Provider。
- FastAPI REST API、后台任务运行时、SQLite 状态持久化和 SSE 事件流。
- 任务创建、状态查询、取消、安全恢复、审批决定和事件重放。
- 断开 SSE 客户端不影响后台任务继续执行。

本阶段不包含：

- TUI 或 React WebUI 客户端。
- OpenAI-compatible Provider。
- 多进程/分布式任务调度、消息队列和跨进程恢复。
- SubAgent 实际派发。
- 自动重放执行结果未知的危险工具调用。

## 2. 当前基础与问题

Task 18 已完成 `TaskService.run()`、`LoopController` 的 Mock 决策执行、即时审批、SQLite 任务/审批/事件持久化。当前 API 已支持创建任务和一次性事件查询，但存在以下限制：

- `POST /api/tasks` 在 API 请求内创建任务，未启动真正的后台执行。
- 任务详情、取消、恢复和审批决定接口尚未实现。
- SSE 只返回当前已有事件，不能等待并推送后台新事件。
- `TaskService` 的审批回调是同步调用方回调，无法等待 API 决定。
- SQLite 连接尚未针对 API 请求线程和 worker 线程的并发访问建立统一保护。

## 3. 总体架构

新增 `TaskManager` 作为 API 与 `TaskService/LoopController` 之间的应用层协调器。

```text
POST /api/tasks
        │
        ├─ 校验 workspace、provider 和 Mock 决策
        ├─ 创建 Task、LoopSpec 与初始事件
        ├─ 注册运行上下文
        └─ 提交线程池，立即返回 task_id
                    │
                    ▼
             TaskManager worker
                    │
                    ├─ 调用 TaskService/LoopController
                    ├─ 持久化状态和有序事件
                    ├─ 审批时写入 pending approval 并等待
                    └─ 收到审批/取消信号后继续或终止
```

`TaskManager` 使用进程内 `ThreadPoolExecutor` 执行 Mock 任务；每个运行任务拥有独立的取消事件、审批条件变量和最近事件序号。SQLite 是任务状态、审批记录、检查点和事件的事实来源；内存上下文只负责当前进程中的唤醒与 worker 生命周期管理。

## 4. 任务状态机

允许的主要状态转换如下：

```text
pending ──worker started──> running
running ──policy ask──────> waiting_approval
waiting_approval ──allow──> running
waiting_approval ──reject─> needs_review
pending/running/waiting_approval ──cancel──> cancelled
running ──loop result─────> succeeded | needs_review | blocked |
                             failed | budget_exhausted
```

约束：

- 所有终态不可再次取消、恢复或审批。
- `forbidden` 策略结果直接进入 `needs_review`，不创建审批记录。
- 审批 `once` 只允许当前工具调用；`task` 将对应风险加入当前循环的临时授权集合。
- `resume` 只恢复当前服务仍管理且处于安全暂停状态的任务，不自动重放结果未知的危险动作。
- 任务最终状态、`task_completed` 事件和结果摘要必须持久化。

## 5. API 契约

### 5.1 创建任务

```text
POST /api/tasks
```

请求字段：

```json
{
  "workspace": "C:/repo",
  "goal": "修改目标文件",
  "mode": "supervised",
  "provider": "mock",
  "mock_decisions": [
    {
      "action": "tool_call",
      "tool_action": {
        "tool": "shell",
        "arguments": {"command": "python -c \"pass\""}
      }
    },
    {"action": "complete", "completion_message": "完成"}
  ],
  "acceptance_checks": []
}
```

`mock_decisions` 使用现有严格的 `AgentDecision` 规则校验，错误输入在执行工具前返回 `400`。本阶段只接受 `provider=mock`。workspace 必须存在且为目录。

接口创建任务、保存 LoopSpec 和初始事件后提交后台 worker，返回 `201`，不等待任务终态。响应至少包含 `id`、`status`、`workspace`、`goal`、`mode` 和 `provider`。

### 5.2 查询任务

```text
GET /api/tasks/{task_id}
```

返回任务领域模型、当前状态、关联 LoopSpec、最近结果摘要以及 pending approval 摘要。任务不存在返回 `404`。

### 5.3 取消与恢复

```text
POST /api/tasks/{task_id}/cancel
POST /api/tasks/{task_id}/resume
```

取消只允许作用于非终态任务。接口设置线程安全取消信号并唤醒等待中的 worker；循环在安全边界结束为 `cancelled`。终态任务返回 `409`。

恢复只允许当前进程仍管理且处于安全暂停状态的任务。恢复不会重放结果未知的危险动作；不满足条件返回 `409`。

### 5.4 审批决定

```text
POST /api/approvals/{approval_id}/decision
```

请求字段：

```json
{
  "approved": true,
  "scope": "once",
  "actor": "api-user"
}
```

审批必须仍为 `pending`，scope 只允许 `once` 或 `task`。决定写入 SQLite 后发布 `approval_decided` 并唤醒关联 worker。未知审批返回 `404`，重复决定或任务不可审批返回 `409`。

### 5.5 事件回放与 SSE

```text
GET /api/tasks/{task_id}/events?after=N
GET /api/tasks/{task_id}/events/stream?after=N
```

JSON 回放返回所有 `sequence > N` 的事件，并按序号升序排列。

SSE 先回放历史事件，再通过条件变量和数据库轮询等待新事件。每条事件格式为：

```text
id: 7
event: approval_requested
data: {"id":"...","task_id":"...","sequence":7,...}

```

任务进入终态并发送最后事件后，SSE 连接关闭。客户端断开只释放连接，不取消 worker；客户端可使用最后事件序号重新连接。

## 6. 持久化与并发安全

SQLiteStore 将扩展以下能力：

- `Approval` 增加任务关联信息，便于审批 API 定位 worker。
- 读取 LoopSpec 和 pending approval。
- 原子更新任务状态与审批状态。
- 在并发访问中保护 SQLite 连接和事件序号生成。
- 保持现有 `events_after(task_id, sequence)` 的有序重放接口。

事件顺序规则：

1. 状态变化先生成对应事件。
2. 事件在 SQLite 中按任务内递增 sequence 持久化。
3. `task_completed` 作为最终结果摘要事件写入最后。
4. worker、审批请求、取消请求不能产生跨任务序号冲突。

进程内状态包括：

- `Future`/worker 句柄。
- 取消 `Event`。
- 审批等待 `Condition`。
- 事件唤醒 `Condition`。

这些内存对象不能替代 SQLite 持久化。服务重启后的完整任务恢复不在本阶段范围内，重启时不得自动重放危险动作。

## 7. 错误处理与安全边界

- FastAPI 错误统一返回 `detail` JSON，不返回 traceback。
- 硬性禁止命令永远不进入审批流程。
- Provider 不为 `mock`、Mock 决策非法、workspace 不存在均在后台执行前拒绝。
- 同一个审批只能决定一次；决定结果不可覆盖。
- SSE 查询无权修改任务状态。
- API 默认继续监听回环地址；本阶段不新增远程访问能力。
- 不把 Provider 密钥写入任务请求、事件、SQLite 或报告。
- worker 异常必须转为持久化的 `failed` 状态和 `task_completed` 事件，而不是让线程静默退出。

## 8. 文件边界

- `src/code_agent/api/schemas.py`：新增任务详情、取消/恢复、审批决定和 Mock 决策请求/响应模型。
- `src/code_agent/api/app.py`：注册生命周期、审批和事件流路由；连接 `TaskManager`。
- `src/code_agent/application/task_manager.py`：新增线程池、运行上下文、审批等待、取消和事件广播。
- `src/code_agent/application/task_service.py`：抽取可注入的运行/事件/审批协调接口，保持现有 CLI 行为。
- `src/code_agent/core/loop.py`：增加取消检查和可被 API 唤醒的审批协作点。
- `src/code_agent/core/models.py`：补充任务详情和审批关联所需的领域字段。
- `src/code_agent/storage.py`：增加并发安全、任务/LoopSpec/审批查询与原子更新能力。
- `tests/integration/test_api_sse.py`：API、SSE、审批和生命周期测试。
- `tests/integration/test_task_manager.py`：后台执行、等待、唤醒和取消测试。
- `tests/integration/test_storage.py`：并发安全和审批关联持久化测试。
- `SPEC_PROCESS.md`：记录设计、计划、实施和验证证据。

## 9. 测试与验收标准

实施严格遵循 TDD：每个行为先写失败测试，确认红灯，再完成最小实现并确认绿灯。

必须覆盖：

1. 创建任务立即返回，worker 后台执行并持久化终态。
2. 任务详情正确反映 pending、running、waiting_approval、succeeded 和 cancelled。
3. 审批请求生成 pending 记录；批准/拒绝能分别唤醒或终止 worker。
4. `once` 与 `task` 授权范围正确传播。
5. 硬性禁止动作不创建审批。
6. 取消能唤醒等待中的任务，且不会改变已完成任务。
7. 事件 JSON 回放按 sequence 排序且不重复。
8. SSE 能回放历史并接收后台新事件，断开连接不影响任务。
9. 不存在资源、重复审批和终态操作返回正确 HTTP 状态码。
10. 既有 Python 测试、Ruff 和 Mypy 全部通过。

验收完成后，API 可以在无真实 API Key、无网络依赖的条件下创建一个 Mock 任务，通过 API 完成实时审批，并查询完整的任务状态、事件序列和最终结果证据。
