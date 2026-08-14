# SPEC_PROCESS

本文档记录 `SPEC.md` 与 `PLAN.md` 的生成、评审和验证过程。

## Brainstorming 记录

在 brainstorming 阶段填写。

## Writing-plans 记录

2026-08-13 按已确认的 Task 23 设计与实施计划执行：在隔离 worktree 中完成 ProviderFactory、API artifact、CLI 生命周期命令、TUI/WebUI Provider 贯通、`code-agent web` 静态资源托管和四类离线规格演示。每个子项目均先运行红灯测试，再实现最小代码并运行绿灯测试；最终证据见 `AGENT_LOG.md`。

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

2026-08-14 在用户指定的隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-25-restart-recovery` 串行完成 Task 25 最终审查的 A–E Important。既有 Task 25 SDD 与用户给出的最终审查项作为已批准规格；因允许修改清单不包含新的设计/计划文件，本轮没有创建额外规格文档。

本轮严格执行 TDD。A 使用真实运行中的审批等待 worker，红灯证明 `TaskManager.shutdown()` 被 `ThreadPoolExecutor.shutdown(wait=True)` 阻塞；实现独立 service-stop Event 与 Condition 通知后，worker 不走用户 cancel/终态落库即可退出，任务留待下次 manager 启动隔离。B 的红灯证明 recovery claim 不会处理旧 pending approval；最小实现是在 claim 的 `BEGIN IMMEDIATE` 事务内将旧审批标为 `rejected`，随后恢复运行创建新审批，旧 decision 冲突且不能再次修改记录。C 通过替换 `executor.submit` 注入失败，红灯证明任务、recovery、runtime 与 `recovery_started` 会形成不一致；最小实现让 claim 返回事件 sequence，submit 失败先移除 runtime，再由 storage 补偿事务恢复 `needs_review + required=True` 并删除该伪事件。D 的红灯证明 `after == task_completed.sequence` 仍会进入事件等待；最小实现仅在终态增量为空时回查已持久化完成事件并立即关闭，同时保留终态先于完成事件落库的 staged 补回看测试。E 将随后读取/断言完成事件的测试统一改为等待 `task_completed`。

最终目标测试为 `35 passed, 39 warnings`；Python 全量为 `164 passed, 1 skipped, 43 warnings in 142.94s`；Ruff 输出 `All checks passed!`；Mypy 输出 `Success: no issues found in 33 source files`；Web Vitest 为 `2` 个文件、`8` 个测试通过；TypeScript/Vite build 成功。两份 `task-5-report.md` 已统一为相同内容。既有 FastAPI `on_event`、Starlette TestClient/httpx 弃用提示与 Vite `configLoader: 'native'` 迁移预警不影响退出状态。当前环境无通用 subagent 调度工具，因此无法执行独立 reviewer，改为按审查模板逐项自审并在最终 concern 中如实记录。

2026-08-13 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-25-restart-recovery` 执行 Task 25 / Task 5 最终集中修复（唯一一次 fix wave）。遵循用户限定范围，只修改 `src/code_agent/api/app.py`、`tests/integration/test_api_sse.py`、`AGENT_LOG.md`、`SPEC_PROCESS.md` 与 `.superpowers/sdd/2026-08-13-task-25-restart-recovery/task-5-report.md`。先按 TDD 在 `tests/integration/test_api_sse.py` 新增 `test_events_stream_replays_terminal_completion_before_closing`：通过受控替身让同一终态任务的 `/api/tasks/{id}/events/stream` 首轮只看到 `feedback`、第二轮才返回 `task_completed`，精确固定“任务状态已终态，但 `task_completed` 尚未出现在当前批次 `events_after()` 中”的竞态窗口。

红灯命令为 `$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_events_stream_replays_terminal_completion_before_closing -q`。失败表现为流只返回 `feedback`，缺少预期的 `task_completed`。根因是 `src/code_agent/api/app.py` 中 `/events/stream` generator 在每轮回放后只要看到任务 `status in _TERMINAL_STATES` 就立即关闭，而 `TaskManager._run()` 的顺序是先 `update_task(final_task)`、后 `append_event("task_completed", ...)`，两者之间存在短窗口，导致 SSE 可能在完成事件真正可读之前过早结束。

按 TDD 仅做最小修复：在 `src/code_agent/api/app.py` 的 SSE generator 中，终态时若当前批次已看到 `task_completed` 则正常关闭；若未看到，则先做一次终态补回看，并仅在需要时执行一次有限等待后再次检查 `events_after()`；若终态任务是无活动 runtime 的 `needs_review`，则直接关闭，不做无限等待；等待阶段若 runtime 不存在则捕获 `KeyError` 并结束流。随后同一红灯命令转绿为 `1 passed, 3 warnings`，既有真实恢复回归 `$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_restart_recovery_events_stream_replays_first_step_only_after_resume -q` 也保持 `1 passed, 5 warnings`。

2026-08-13 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-25-restart-recovery` 执行 Task 25 / Task 5 fix round 1。遵循用户限制，先只修改 `tests/integration/test_api_sse.py`，将原先只覆盖 `/events` JSON 回放的测试更名为 `test_restart_recovery_events_endpoint_requires_manual_resume_and_preserves_order`，并新增真实消费 `/api/tasks/{id}/events/stream` 的集成测试 `test_restart_recovery_events_stream_replays_first_step_only_after_resume`。该测试使用同一 `state.db` 中旧的 `waiting_approval` Mock 任务，验证服务重启后任务被隔离为 `needs_review`，旧 approval 决策返回 `409`，且在人工 `resume` 前直接打开 SSE 端点只能收到 `recovery_required`，不会自动出现 `task_completed`；`resume` 后再从最后 sequence 打开同一 SSE 端点，必须看到 `recovery_started`、`feedback`、`task_completed`，并通过 `feedback.payload.changed_files == ["restart-marker.txt"]` 与文件内容 `from-recovery` 证明恢复执行包含可区分的首步 `write_file`，而不是直接完成。

红灯命令为 `$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -k events_stream_replays_first_step_only_after_resume -q`。失败不是测试拼写或缺少导入，而是真实实现缺口：SSE generator 在重启隔离后的终态任务上回放完 `recovery_required` 后仍调用 `TaskManager.wait_for_event()`，而该任务没有活动 runtime，最终抛出 `KeyError`。按 TDD 仅做最小修复：修改 `src/code_agent/api/app.py`，将 `/events/stream` generator 的终态关闭条件从“终态且当前批次无事件”调整为“终态即在回放完当前批次后直接关闭”，避免对无 runtime 的隔离任务继续等待。随后同一红灯命令转绿。

完成修复后，执行 `$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -q`，结果为 `15 passed, 35 warnings`。再按 Task 5 brief 运行最终验证：`$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q` 结果 `159 passed, 1 skipped, 39 warnings`；`C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe check .` 输出 `All checks passed!`；`C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe src` 输出 `Success: no issues found in 33 source files`；`web\npm.cmd test -- --run` 结果为 `2` 个文件、`8` 个测试通过；`web\npm.cmd run build` 构建成功。warnings 仍是仓库既有范围：Python 侧为 FastAPI `on_event` 与 Starlette TestClient/httpx 弃用提示，Web 侧为 Vite `configLoader: 'native'` 迁移预警，均未影响退出状态。

2026-08-13 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-25-restart-recovery` 按 Task 25 / Task 5 brief 执行端到端验收与中文过程记录，严格限定修改范围为 `tests/integration/test_api_sse.py`、`task-5-report.md`、`AGENT_LOG.md`、`SPEC_PROCESS.md`。先按 TDD 在 `tests/integration/test_api_sse.py` 新增 `test_restart_recovery_stream_requires_manual_resume_and_preserves_order`，覆盖同一 `state.db` 中旧的待审批/未终态 Mock 任务，在旧 app 关闭、新 app 启动后被隔离为 `needs_review`，详情字段正确保留旧 `goal` 并暴露持久化 `loop_spec.goal`，旧 approval 不自动执行，人工 `resume` 后从头重新执行到终态，以及事件序号严格递增且包含 `recovery_required`、`recovery_started`、`task_completed`。红灯命令为 `$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_restart_recovery_stream_requires_manual_resume_and_preserves_order -q`：首次失败先暴露测试自身缺少 `Approval` 导入，补齐导入后继续使用同一命令验证真实恢复流程，并得到绿灯 `1 passed, 5 warnings`。随后执行针对性回归 `$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py -q`，结果为 `14 passed, 31 warnings`。

按 brief 执行最终验证：`$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q` 得到 `158 passed, 1 skipped, 35 warnings`；`C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe check .` 输出 `All checks passed!`；`C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe src` 输出 `Success: no issues found in 33 source files`；`web\npm.cmd test -- --run` 为 `2 passed` 个文件、`8 passed` 个测试；`web\npm.cmd run build` 构建通过。warnings 维持仓库既有范围：Python 侧为 `fastapi.testclient` / `starlette.testclient` 与 FastAPI `on_event` 弃用警告，Web 侧为 Vite `configLoader: 'native'` 迁移预告，均未影响退出状态。恢复边界在 `task-5-report.md` 明确记录：本任务验证“重启后隔离 + 人工 resume + 从头重跑 + 事件顺序”，不自动重放旧 approval，不验证 checkpoint 续跑位置，不触达真实 Provider E2E。该段先前记录的“隔离后、恢复前直接拉取无活动 runtime 的 SSE stream 仍可能失败”已被 2026-08-13 的最终 fix wave 修正，不再作为现存 concern 保留。

2026-08-13 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-24-web-package-release` 按 Task 24 计划完成 WebUI 发布链。新增发布顺序验收的红灯命令为 `$env:PYTHONPATH="src;."; .\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q`，结果 `1 failed, 3 passed`：`make package` 不存在且 GitHub CI 的 Python build 先于 Web build。随后实现 `make package`，将前端依赖安装、Vitest、Vite build、资源暂存、Python build 和干净 wheel 安装验收固定为同一顺序；GitHub Actions 配置 Node 22，GitLab CI 的 `web-build` job 将 `web/dist` 作为 `package` job 的依赖工件，两个 CI 都不会默认运行真实 Provider E2E。绿灯为同一集成测试 `4 passed`。

本机 Windows 未安装 GNU Make，`make package` 因命令不存在而无法直接启动；未将其误记为通过，而是顺序执行其完全等价的四个命令。结果：`npm.cmd ci` 成功；`npm.cmd test -- --run` 为 `2` 个测试文件、`6 passed`；`npm.cmd run build` 成功；资源暂存与 `python -m build` 成功；wheel 干净安装验收为 `4 passed`。Vite 输出既有 `configLoader: native` 迁移预告，退出码保持为 0。最终执行 `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest -q` 得到 `134 passed, 1 skipped, 21 warnings`；Ruff 为 `All checks passed!`；Mypy 为 `Success: no issues found in 33 source files`。21 条警告为既有 FastAPI/Starlette 弃用提示。默认 E2E 仍跳过，未读取 keyring、Provider 凭据或访问真实 Provider。

2026-08-13 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-22-multi-provider` 完成 Task 22 的多 Provider 收尾。所有 Python 命令使用仓库根目录共享 `.venv`，并设置 `PYTHONPATH=src`，以保证加载当前 worktree 源码。

- Task 1：红灯为 Provider 配置接口尚不存在；绿灯完成双层档案解析、项目同名整体覆盖、严格字段和安全 URL 验证。
- Task 2：红灯为命名 keyring 凭据及显式开发回退接口缺失；绿灯完成 keyring 优先、明文回退隔离和 shell 子进程密钥环境清理。
- Task 3：红灯为安全 HTTP Provider 与统一错误类型缺失；绿灯完成 OpenAI-compatible 调用、JSON 决策校验及敏感错误信息隔离。
- Task 4：红灯为服务/管理器仍使用旧的 Mock 决策调用链；绿灯完成 Provider 注入，运行时不再硬编码 Mock，持久化只保存 Provider 名称。
- Task 5：红灯为 CLI 没有显式 Provider 选择、认证命令边界和安全错误转换；绿灯完成 `build_provider`、`auth set/status/clear`、无回退策略和离线回归，并修复无效 Mock 场景输入值泄露。
- Task 6：新增 `tests/integration/test_provider_e2e.py`。先运行默认 E2E 命令，结果为 `1 skipped`；开关 `CODE_AGENT_RUN_PROVIDER_E2E=1` 未设置时，skipif 在档案解析、keyring 读取和 HTTP 前生效，故默认 CI 无 keyring 访问、无网络访问。可选的 `CODE_AGENT_PROVIDER_E2E_NAME` 默认为 `openai`，仅选择非敏感档案。

最终执行 `python -m pytest -q`、`ruff check .` 和 `mypy src`；结果与具体警告数记录在 Task 6 报告。真实 E2E 未启用，因此没有 Provider、密钥或响应正文可记录。文档要求真实 E2E 必须同时显式设置开关、配置非敏感档案并运行 `auth set <name>`；keyring 是首选，开发回退必须由调用方显式允许，且明文/进程可见风险已说明。环境限制为 linked worktree 没有独立 `.venv`，以及 pytest 保留既有 FastAPI/Starlette 弃用警告。

冷启动验证完成后，在隔离 worktree 中按 Task 1–17 执行严格 TDD。每个任务均记录红灯、绿灯、静态检查和提交；Windows 环境缺少 `make` 时，使用等价的 pytest、Ruff 和 Mypy 命令验证底层行为。

2026-08-09 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-18-mock-runtime` 的 `codex/task-18-mock-runtime` 分支实施 Task 18。基线为 pytest `36 passed`。实施分为四个 TDD 单元：严格 Mock 场景解析的红灯为缺少 `code_agent.application`，绿灯为 `2 passed`；审批主循环的红灯为缺少 `ApprovalResolution`，绿灯为新增审批测试和既有循环测试 `2 passed`；SQLite 状态与审批持久化的红灯为缺少 `update_task`，绿灯为存储测试 `3 passed`；TaskService/CLI 集成的红灯为缺少 `TaskService`。集成绿灯阶段发现 SQLite 对不存在的 `.code-agent` 父目录直接连接会失败，按 `superpowers:systematic-debugging` 复现并定位到 `SQLiteStore.__init__`，新增最小回归测试后由存储层创建父目录。最终验证：pytest `44 passed`（1 个既有 Starlette 弃用警告）、Ruff 通过、Mypy 在 28 个源文件中无错误，机制演示输出 `guardrail=denied`、`feedback_loop=succeeded`、`focus_mechanism=passed`。

2026-08-10 在当前工作区按 Inline Execution 实施 Task 19，严格执行 TDD：

- Task 1 的红灯为新增存储接口不存在和并发事件 sequence 冲突，结果为 `2 failed, 4 passed`；加入 `Approval.task_id`、SQLite `RLock`、LoopSpec/审批查询和原子审批决定后绿灯为 `6 passed`，提交 `5ed1047`。
- Task 2 的红灯为缺少 `TaskManager`，结果为测试收集阶段 `ModuleNotFoundError`；加入后台线程池、审批等待、取消信号、事件回调和循环取消检查后绿灯为 `3 passed`，核心审批回归为 `5 passed`，提交 `9f8293b` 与类型修复提交 `fbd07f7`。
- Task 3 的红灯为生命周期路由尚未存在，结果为 `2 passed, 5 failed` 且查询响应缺少 `status`；加入 Mock 决策请求模型、任务查询/取消/恢复、审批决定和阻塞 SSE 后绿灯为 `7 passed`，提交 `a1d3240`。
- 静态检查初次发现 4 个 Ruff 格式问题和 2 个 Mypy 类型问题，完成最小清理后 Ruff 通过、Mypy 在 29 个源文件中无错误。
- 最终全量验证为 pytest `54 passed`、Ruff 通过、Mypy 通过。测试输出包含 15 个 FastAPI/Starlette 弃用警告，不影响退出状态。

Task 19 的已知边界：运行时是单进程内存 TaskManager，服务重启后不自动恢复 worker，也不自动重放结果未知的危险动作；API 仍只支持 Mock Provider；SSE 客户端断开不会取消任务，客户端必须使用最后事件序号重新连接。

2026-08-11 至 2026-08-12 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-20-webui-console` 的 `codex/task-20-webui-console` 分支实施 Task 20。设计规格为 `docs/superpowers/specs/2026-08-11-task-20-webui-console-design.md`，实施计划为 `docs/superpowers/plans/2026-08-11-task-20-webui-console.md`。WebUI 的 Vitest 从 2 项基线测试扩展为 5 项，通过；Vite build 通过；Python 基线为 pytest `54 passed`、Ruff 通过、Mypy 通过。已配置 Playwright 桌面和 390px 验收，但 Chromium 未安装，连续两次浏览器下载在网络阶段超时，故 `npm run e2e` 未通过。用户授权暂时将 Task 20 标记完成并继续 Task 21；该任务保留“需补跑 Playwright”验收项，不得表述为全量验证通过。

2026-08-12 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-21-textual-api-console` 完成 Task 21 的 Textual API Console 后，执行 Task 4 质量验证与过程记录。为保证检查使用本 worktree 的源码而非共享虚拟环境中指向其他工作区的 editable 安装，所有 Python/Mypy 命令均在该 worktree 运行，且设置 `$env:PYTHONPATH = "src"`。实际执行 `C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q`，结果为 `79 passed, 15 warnings in 10.98s`；警告是既有 FastAPI `on_event` 及 Starlette TestClient/httpx 弃用提示，退出状态为 0。随后执行 `C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe check .`，输出 `All checks passed!`；执行 `C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe src`，输出 `Success: no issues found in 30 source files`。Task 3 的 `tests/integration/test_tui.py` 最终针对性验证为 `23 passed`，基于 Textual `run_test` 和可注入 fake client，覆盖运行观察、详情先于事件、`after=0` 首次拉取、递增 sequence 去重、审批决定、取消/恢复、API 错误保留界面与游标，以及终态结果渲染；测试未访问真实网络，未引入浏览器或 Playwright 依赖。已审查过程文档和任务报告，未发现占位语或敏感凭据。Task 20 的 Chromium 下载超时限制仍未解除，`npm run e2e` 仍需在可下载浏览器的环境补跑；该未通过项继续影响全仓浏览器 E2E 验收，不能写为通过。

2026-08-12 补跑 Task 20 的浏览器 E2E 验收。再次执行 `npm.cmd exec playwright install chromium` 后下载在 5 分钟无输出时超时；诊断确认本机存在 Microsoft Edge，但无 Playwright Chromium 或 Google Chrome。用户授权在 `web/playwright.config.ts` 中显式使用 Playwright `msedge` 通道，并以 `npm.cmd ci` 根据锁文件恢复遗漏的 Playwright 包。随后执行 `npm.cmd run e2e`，桌面任务创建/审批可见性与 390px 无横向溢出两项均通过（`2 passed`）。同次执行 `npm.cmd test -- --run` 为 Vitest `5 passed`，`npm.cmd run build` 通过 TypeScript 和 Vite 构建。Vite 给出既有 native config loader 迁移预告，但所有命令退出状态均为 0。因此 Task 20 的浏览器 E2E 验收已通过；其验证浏览器为本机 Microsoft Edge，而非因网络超时无法下载的 Playwright Chromium。
