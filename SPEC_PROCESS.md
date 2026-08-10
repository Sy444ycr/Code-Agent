# SPEC_PROCESS

本文档记录 `SPEC.md` 与 `PLAN.md` 的生成、评审和验证过程。

## Brainstorming 记录

在 brainstorming 阶段填写。

## Writing-plans 记录

2026-07-11 使用 `superpowers:writing-plans` 将已确认的 `SPEC.md` 拆分为 17 个可执行任务，正式计划保存到 `PLAN.md` 与 `docs/superpowers/plans/2026-07-11-code-agent.md`。计划按 TDD 顺序组织：项目骨架、核心模型、治理策略、workspace 工具、Shell 与语言适配、反馈、LLM Provider、记忆与上下文、Hook、主循环、SubAgent、SQLite、API、CLI/TUI/WebUI、CI 与机制演示。

本轮计划自查覆盖三项：规格覆盖、占位词扫描和接口命名一致性。占位词扫描命令为：

```powershell
rg -n "TBD|TODO|implement later|fill in details|Similar to|类似|适当|后续补" PLAN.md docs/superpowers/plans/2026-07-11-code-agent.md
```

检查结果为空；`PLAN.md` 与默认计划文件的 SHA256 哈希一致。

2026-07-13 根据用户要求，将 `PLAN.md` 调整为明确的 TDD 执行版：新增 `TDD Execution Contract`，要求每个行为变更必须先写失败测试、确认红灯、再写最小实现、确认绿灯、绿灯后重构，并在 `AGENT_LOG.md` 记录红绿证据。此次调整只修改计划与过程文档，不编写实现代码。

2026-08-09 用户确认 `docs/superpowers/specs/2026-08-09-task-service-design.md` 中的 Task 18 设计：先实现单机、单任务、Mock LLM 的 CLI 端到端闭环，采用 JSON 场景文件和即时 `y/a/n` 审批；真实 Provider、API 后台任务、WebUI 与并发任务留到后续独立阶段。随后使用 `superpowers:writing-plans` 将该设计拆分为 Mock 场景解析、审批主循环、SQLite 持久化和 TaskService/CLI 闭环四个严格 TDD 任务，计划保存至 `docs/superpowers/plans/2026-08-09-task-service-runtime.md`。用户明确授权继续实施，并要求在本文档记录实施和验证证据。

2026-08-10 用户确认 Task 19 范围为后端任务生命周期 API、实时 SSE 与 API 审批，继续只使用 Mock Provider，暂不实现 TUI、WebUI 和真实 Provider。经 brainstorming 讨论，选择进程内 `TaskManager + ThreadPoolExecutor`：API 创建任务后立即返回，worker 在线程池中运行，SQLite 保存任务/审批/事件，审批通过 `Condition` 唤醒，SSE 通过事件序号回放并等待新事件。设计规格保存至 `docs/superpowers/specs/2026-08-10-task-api-lifecycle-design.md`，并经用户确认；实施计划保存至 `docs/superpowers/plans/2026-08-10-task-api-lifecycle.md`。

## 关键对话节选

记录至少三轮关键交互，以及这些交互如何影响项目决策。

## 采纳与拒绝的建议

在规格和计划评审过程中填写。

## 冷启动验证

在全新 agent 仅使用 `SPEC.md` 与 `PLAN.md` 尝试实现一到两个任务后填写。

## 实现阶段记录

冷启动验证完成后，在隔离 worktree 中按 Task 1–17 执行严格 TDD。每个任务均记录红灯、绿灯、静态检查和提交；Windows 环境缺少 `make` 时，使用等价的 pytest、Ruff 和 Mypy 命令验证底层行为。

2026-08-09 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-18-mock-runtime` 的 `codex/task-18-mock-runtime` 分支实施 Task 18。基线为 pytest `36 passed`。实施分为四个 TDD 单元：严格 Mock 场景解析的红灯为缺少 `code_agent.application`，绿灯为 `2 passed`；审批主循环的红灯为缺少 `ApprovalResolution`，绿灯为新增审批测试和既有循环测试 `2 passed`；SQLite 状态与审批持久化的红灯为缺少 `update_task`，绿灯为存储测试 `3 passed`；TaskService/CLI 集成的红灯为缺少 `TaskService`。集成绿灯阶段发现 SQLite 对不存在的 `.code-agent` 父目录直接连接会失败，按 `superpowers:systematic-debugging` 复现并定位到 `SQLiteStore.__init__`，新增最小回归测试后由存储层创建父目录。最终验证：pytest `44 passed`（1 个既有 Starlette 弃用警告）、Ruff 通过、Mypy 在 28 个源文件中无错误，机制演示输出 `guardrail=denied`、`feedback_loop=succeeded`、`focus_mechanism=passed`。

2026-08-10 在当前工作区按 Inline Execution 实施 Task 19，严格执行 TDD：

- Task 1 的红灯为新增存储接口不存在和并发事件 sequence 冲突，结果为 `2 failed, 4 passed`；加入 `Approval.task_id`、SQLite `RLock`、LoopSpec/审批查询和原子审批决定后绿灯为 `6 passed`，提交 `5ed1047`。
- Task 2 的红灯为缺少 `TaskManager`，结果为测试收集阶段 `ModuleNotFoundError`；加入后台线程池、审批等待、取消信号、事件回调和循环取消检查后绿灯为 `3 passed`，核心审批回归为 `5 passed`，提交 `9f8293b` 与类型修复提交 `fbd07f7`。
- Task 3 的红灯为生命周期路由尚未存在，结果为 `2 passed, 5 failed` 且查询响应缺少 `status`；加入 Mock 决策请求模型、任务查询/取消/恢复、审批决定和阻塞 SSE 后绿灯为 `7 passed`，提交 `a1d3240`。
- 静态检查初次发现 4 个 Ruff 格式问题和 2 个 Mypy 类型问题，完成最小清理后 Ruff 通过、Mypy 在 29 个源文件中无错误。
- 最终全量验证为 pytest `54 passed`、Ruff 通过、Mypy 通过。测试输出包含 15 个 FastAPI/Starlette 弃用警告，不影响退出状态。

Task 19 的已知边界：运行时是单进程内存 TaskManager，服务重启后不自动恢复 worker，也不自动重放结果未知的危险动作；API 仍只支持 Mock Provider；SSE 客户端断开不会取消任务，客户端必须使用最后事件序号重新连接。
