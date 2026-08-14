# Task 25 / Task 5 最终修复报告

## 范围

本轮严格在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-25-restart-recovery` 工作，只修改用户允许的文件：

- `src/code_agent/application/task_manager.py`
- `src/code_agent/storage.py`
- `src/code_agent/api/app.py`
- `tests/integration/test_task_manager.py`
- `tests/integration/test_api_sse.py`
- `AGENT_LOG.md`
- `SPEC_PROCESS.md`
- 两份 `task-5-report.md`

未修改 Web/TUI 源码。

## 最终审查修复

### A. shutdown 不再被审批等待 worker 阻塞

- runtime 新增独立的服务停止信号，与用户 cancel 信号分离。
- `shutdown()` 先通知所有 runtime；审批 handler 收到服务停止后退出 worker，但不写入取消或其他终态。
- 下次创建 `TaskManager` 时，仍处于 `waiting_approval` 的任务会被启动隔离逻辑转换为 `needs_review`。
- 集成测试通过真实 `submit` 运行到审批等待，确认 future 仍在运行，没有用手工数据库状态代替 worker。

### B. 恢复运行拒绝旧审批并生成新审批

- `claim_recovery` 在同一个 `BEGIN IMMEDIATE` 事务内，将该任务所有旧 pending approval 标记为 `rejected`，actor 为 `recovery`。
- 恢复 worker 生成全新的 approval。
- 对旧 approval 再提交 decision 会冲突，旧记录保持不变；新 approval 仍可批准并完成任务。

### C. recovery submit 失败补偿

- `claim_recovery` 的 `BEGIN IMMEDIATE` 事务只原子 claim task/recovery 并拒绝旧 pending approvals，不再预写 `recovery_started`。
- `_start_runtime` 先向 executor 提交一个受启动门闩控制的 worker；提交成功后才追加 `recovery_started`，事件提交完成后再放行 worker，保证恢复事件早于 runtime 事件。
- `executor.submit` 失败时移除刚注册的 runtime；storage 补偿事务只恢复 `needs_review + recovery.required=True`，不删除事件、不复用 sequence，旧 approvals 保持 `rejected`。
- 确定性测试在注入的 submit 失败函数内部和失败返回后读取事件历史，均确认没有 `recovery_started`；随后成功重试确认 sequence 连续，客户端从失败前游标可收到 `recovery_started` 与 `task_completed`。

### D. SSE 完成游标立即关闭

- 当任务已终态、当前增量为空时，SSE 回查持久化的 `task_completed`。
- 若完成事件 sequence 已不大于 cursor（包括 `after == task_completed.sequence`），流立即关闭，不再调用事件等待。
- 若真实活动 runtime 已进入 `needs_review` 但尚未追加 `task_completed`，SSE 通过 `wait_for_event` 做有限等待并继续回放；只有 runtime 不存在、`wait_for_event` 抛出 `KeyError` 时才立即关闭。
- 确定性测试使用真实 worker，并将其阻塞在 `task_completed` 追加前；原有无 runtime `needs_review`、完成游标立即关闭和终态补回看测试继续保留并通过。

### E. 时序测试与文档统一

- 对随后读取或断言完成事件的集成测试，显式等待 `task_completed`，不再只等待终态 status。
- 根目录与 SDD 目录的 `task-5-report.md` 内容统一为本报告。
- `AGENT_LOG.md` 与 `SPEC_PROCESS.md` 同步记录本轮红绿证据与最终验证。

## TDD 红绿证据

- A 红灯：真实审批等待 worker 的 shutdown 线程在 0.5 秒后仍存活，`assert shutdown_returned` 失败；修复后通过，并确认重启隔离为 `needs_review`。
- B 红灯：恢复 claim 后旧 approval 实际仍为 `pending`，期望 `rejected` 的断言失败；原子失效后通过。
- C 新红灯：注入的 submit 失败函数内部实际读到 sequence 2 的伪 `recovery_started`；事件延后至提交成功并使用启动门闩后，失败窗口与失败后历史均无伪事件，成功重试的 sequence 和游标回放通过。
- D 新红灯：真实活动 runtime 已持久化 `needs_review`、但被阻塞在 `task_completed` 追加前时，SSE 未调用 `wait_for_event` 就关闭；改为按 runtime 存在性判断后通过。
- A–D 每项均先运行单测确认预期失败，再写最小实现并运行同一测试确认转绿。

## 最终验证

所有命令均在指定 worktree 执行，并确保 Python 导入当前 worktree 的 `src`。

- 目标集成测试：
  - `python -m pytest tests/integration/test_task_manager.py tests/integration/test_api_sse.py -q`
  - `36 passed, 41 warnings`
- Python 全量：
  - `python -m pytest -q`
  - `165 passed, 1 skipped, 45 warnings`
- Ruff：
  - `ruff check .`
  - `All checks passed!`
- Mypy：
  - `mypy src`
  - `Success: no issues found in 33 source files`
- Web 测试：
  - `npm.cmd test -- --run`
  - `2 passed (files), 8 passed (tests)`
- Web 构建：
  - `npm.cmd run build`
  - TypeScript 与 Vite 构建成功，`21 modules transformed`

## Concerns

- Python 仍有仓库既有的 FastAPI `on_event` 与 Starlette TestClient/httpx 弃用警告；Web 仍有既有 Vite `configLoader: 'native'` 迁移预警，均未影响退出状态。
- 当前环境未提供通用 subagent 调度工具，无法执行独立 reviewer；已按审查模板逐项检查需求、diff、错误路径、测试与范围。
- 本轮没有扩展到 checkpoint 续跑、真实 Provider E2E 或 Web/TUI 行为。
