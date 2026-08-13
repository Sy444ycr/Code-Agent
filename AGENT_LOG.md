# AGENT_LOG

## 2026-08-13 — Task 25 / Task 5 final fix wave

- 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-25-restart-recovery` 按用户指定的唯一 fix wave 执行最终集中修复；修改范围严格限定为 `src/code_agent/api/app.py`、`tests/integration/test_api_sse.py`、`AGENT_LOG.md`、`SPEC_PROCESS.md`、`.superpowers/sdd/2026-08-13-task-25-restart-recovery/task-5-report.md`。
- TDD 新红灯：先在 `tests/integration/test_api_sse.py` 新增 `test_events_stream_replays_terminal_completion_before_closing`，通过受控替身让同一终态任务的 `/events/stream` 首轮只能看到 `feedback`、第二轮才返回 `task_completed`，精确复现“任务状态已终态，但 `task_completed` 尚未出现在当前批次 `events_after()` 结果中”的窗口。命令 `$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_events_stream_replays_terminal_completion_before_closing -q` 失败，实际只收到 `['feedback']`，证明当前 SSE 会在终态时过早关闭。
- 根因证据：`src/code_agent/api/app.py` 的 SSE generator 在每轮回放完成后只要看到任务 `status in _TERMINAL_STATES` 就立即 `return`，没有再次确认本轮之后是否已能读取到 `task_completed`；而 `TaskManager._run()` 中顺序是先 `update_task(final_task)`、后 `append_event("task_completed", ...)`，因此存在短窗口会漏掉最终完成事件。
- 最小修复：仅调整 `src/code_agent/api/app.py` 的 `/events/stream` generator。终态时若当前批次已看到 `task_completed` 则立即关闭；若未看到，则只做一次终态补回看/有限等待，再次读取 `events_after()`；对 `needs_review` 这类无活动 runtime 的终态任务仍直接关闭，并在等待 runtime 时捕获 `KeyError`，避免无限等待或再次因无 runtime 失败。
- 绿灯证据：新增红灯命令转为 `1 passed, 3 warnings`；原真实恢复 SSE 回归命令 `$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_restart_recovery_events_stream_replays_first_step_only_after_resume -q` 仍为 `1 passed, 5 warnings`，证明修复既补上终态漏事件窗口，也没有破坏“恢复前只能看到 recovery_required、resume 后才继续”的既有语义。
- 本轮完成后，旧的“隔离后、恢复前直接拉取无活动 runtime 的 SSE stream 仍可能失败” concern 已不再成立；`SPEC_PROCESS.md` 已改正，`task-5-report.md` 追加了新的红绿证据与最终边界说明。

## 2026-08-13 — Task 25 / Task 5 fix round 1

- 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-25-restart-recovery`、分支 `codex/task-25-restart-recovery` 接管 Task 5 修复，先按 TDD 只修改 `tests/integration/test_api_sse.py`，保留原先只覆盖 `/events` JSON 回放的测试并更名为 `events_endpoint`，同时新增真实消费 `/api/tasks/{id}/events/stream` 的重启恢复集成测试。
- 红灯：运行 `$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -k events_stream_replays_first_step_only_after_resume -q`。测试通过真实 SSE 打开重启隔离后的任务流，期望在人工 `resume` 前只看到 `recovery_required`，且旧 approval 决策返回 `409`；实际失败为 `KeyError`，根因是 SSE generator 回放完隔离态终态任务的现有事件后仍调用 `TaskManager.wait_for_event()`，而该任务没有活动 runtime。
- 绿灯：最小实现只触碰 `src/code_agent/api/app.py`，将 `/events/stream` generator 的终态关闭条件从“终态且当前批次无事件”改为“终态即在回放完当前批次后直接关闭”，避免对无 runtime 的隔离任务继续等待。随后同一目标测试转绿。
- 新增真实 SSE 测试 `test_restart_recovery_events_stream_replays_first_step_only_after_resume`：同一 `state.db` 中构造 `waiting_approval` 的 Mock 任务，关闭旧 app、启动新 app 后确认任务被隔离为 `needs_review`；先打开 `/events/stream?after=0` 只收到 `recovery_required`，确认不会自动出现 `task_completed`；再 `resume` 后从最后 sequence 继续打开 `/events/stream`，断言收到 `recovery_started`、`feedback`、`task_completed`，并通过 `feedback.payload.changed_files == ["restart-marker.txt"]` 与文件内容 `from-recovery` 证明恢复执行包含可区分的首步 `write_file`，而不是直接完成。
- 针对性验证：`tests/integration/test_api_sse.py -q` 结果为 `15 passed, 35 warnings`；warnings 为既有 FastAPI `on_event` 与 Starlette TestClient/httpx 弃用提示。
- 最终验证：`pytest -q` 结果 `159 passed, 1 skipped, 39 warnings`；`ruff check .` 为 `All checks passed!`；`mypy src` 为 `Success: no issues found in 33 source files`；`web\npm.cmd test -- --run` 为 `2 files passed / 8 tests passed`；`web\npm.cmd run build` 成功。Web 侧仍有既有 Vite `configLoader: 'native'` 迁移预警，不影响退出状态。
- 过程与边界已同步写入 `SPEC_PROCESS.md` 与 `.superpowers/sdd/2026-08-13-task-25-restart-recovery/task-5-report.md`。本轮只修复 Task 5 所需的真实 SSE 恢复覆盖与终态关闭行为；未扩展到 checkpoint 续跑、真实 Provider E2E 或其他恢复语义。

## 2026-08-13 — Task 25 / Task 5：重启恢复端到端验收与中文过程记录

- TDD 红灯：先在 `tests/integration/test_api_sse.py` 新增 `test_restart_recovery_stream_requires_manual_resume_and_preserves_order`，命令 `$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_restart_recovery_stream_requires_manual_resume_and_preserves_order -q` 首次失败；第一次为测试自身缺少 `Approval` 导入，修正后继续用同一条命令验证真实恢复链路。
- TDD 绿灯：新增验收测试覆盖同一 `state.db` 中旧的待审批/未终态任务，在新 app 启动后被隔离为 `needs_review`，详情字段正确暴露 `goal`、`loop_spec.goal`、`recovery_required`、`recovery_reason` 与 `pending_approvals`；旧 approval 不自动执行，`resume` 后从头运行到 `succeeded`；事件序号严格递增，且包含 `recovery_required`、`recovery_started`、`task_completed`。目标命令最终结果为 `1 passed, 5 warnings`。
- 针对性回归：`$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py -q` 结果为 `14 passed, 31 warnings`。
- 最终验证：
  - `$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q` → `158 passed, 1 skipped, 35 warnings`
  - `C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe check .` → `All checks passed!`
  - `C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe src` → `Success: no issues found in 33 source files`
  - `web\npm.cmd test -- --run` → `2 passed (files), 8 passed (tests)`
  - `web\npm.cmd run build` → 构建通过，`✓ built in 307ms`
- warnings 记录：Python 侧仍为既有 `fastapi.testclient` / `starlette.testclient` 弃用警告，以及 FastAPI `on_event` 弃用警告；Web 侧仍为既有 Vite `configLoader: 'native'` 迁移预告，均未影响退出状态。
- 恢复边界：本任务只验证“重启后隔离 + 人工 resume + 从头重跑 + 事件顺序”；不自动重放旧 approval，不验证 checkpoint 续跑位置，不触达真实 Provider E2E。另有一个现存 concern：隔离后、恢复前若直接拉取无活动 runtime 的 SSE stream，当前实现仍可能失败；因 brief 明确限制修改范围，本任务未扩展到源码修复。

## 2026-08-13 — Task 24：WebUI 打包、CI 与干净安装验收

- 红灯：新增发布顺序验收后执行 `$env:PYTHONPATH="src;."; .\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q`，结果为 `1 failed, 3 passed`；`Makefile` 缺少 `package` 目标，GitHub CI 也在 Python 打包之后运行前端构建。
- 绿灯：新增 `make package`，固定执行 `npm ci`、Vitest、Vite build、`prepare_web_package.py`、`python -m build` 与 wheel 安装验收；GitHub Actions 使用 Node 22，GitLab 将 Web build 产物作为 package 阶段依赖，两者均在 Python 打包前完成前端 build 和资源暂存。相同针对性命令结果为 `4 passed`。
- 发布链：本 Windows 环境未安装 GNU Make，`make package` 报“`make` 不是可识别命令”；因此按 Makefile 的完全等价命令逐步执行。`npm.cmd ci` 成功，Vitest 为 `2` 个文件、`6 passed`，Vite build 成功，`python -m build` 成功，wheel 干净安装验收为 `4 passed`。Vite 仍输出既有 `configLoader: native` 配置迁移预告，未影响退出状态。
- 最终验证：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest -q` 为 `134 passed, 1 skipped, 21 warnings`；`.\.venv\Scripts\ruff.exe check .` 为 `All checks passed!`；`.\.venv\Scripts\mypy.exe src` 为 `Success: no issues found in 33 source files`。警告为既有 FastAPI `on_event` 与 Starlette TestClient/httpx 弃用提示。
- 默认链路未设置 `CODE_AGENT_RUN_PROVIDER_E2E`，真实 Provider E2E 保持跳过；执行过程未读取 keyring、Provider 凭据或访问真实 Provider。

## 2026-08-13 — Task 22：多 Provider 收尾验证

- Task 1 红灯为缺少 Provider 配置解析接口；绿灯为 `test_config.py` 通过，完成双层档案、同名整体覆盖、未知字段拒绝和 HTTP(S) URL 规则。
- Task 2 红灯为缺少命名凭据和开发回退接口；绿灯为认证与子进程环境回归通过，完成 keyring 优先、显式开发回退及 Provider 密钥环境清理。
- Task 3 红灯为缺少安全 HTTP Provider 错误类型和响应验证；绿灯为 LLM 单测通过，完成 OpenAI-compatible 请求、结构化决策验证和不回显敏感异常。
- Task 4 红灯为运行时仍以旧签名和硬编码 Mock 构造 Provider；绿灯为服务、管理器、API 和 CLI 回归通过，Provider 已由边界注入且仅名称持久化。
- Task 5 红灯为 CLI 缺少 `build_provider`、显式选择与认证边界；绿灯为 CLI/API 离线回归通过，非 Mock Provider 不回退到 Mock，并修复无效 Mock 场景不得回显输入值。
- Task 6 先新增受 `CODE_AGENT_RUN_PROVIDER_E2E=1` 保护的真实 Provider E2E；默认命令 `python -m pytest tests/integration/test_provider_e2e.py -q` 返回 `1 skipped`。skipif 在 `build_provider`、keyring 和 HTTP 请求之前生效，默认 CI 保持离线。
- 文档明确：档案仅含非敏感地址和模型；密钥优先 `code-agent auth set <name>` 写入 keyring；开发环境变量回退必须显式允许，且明文对进程可见；E2E 同时要求开关、非敏感档案和 `auth set <name>`，名称默认 `openai` 且不承载密钥。
- 最终验证命令及结果记录于本任务报告；未启用真实 E2E、未读取 keyring、未访问网络。环境限制：linked worktree 不含独立 `.venv`，命令使用仓库根目录共享虚拟环境并设置 `PYTHONPATH=src`；pytest 的既有 FastAPI/Starlette 弃用警告须如实保留。

## 2026-08-12 — Task 20：补跑 Playwright 浏览器验收

- Chromium 下载在本环境再次等待 5 分钟后超时；检测到本机已安装 Microsoft Edge，用户授权改用 Playwright 的 `msedge` 通道执行同一份 E2E 用例。`web/playwright.config.ts` 现显式声明 `Microsoft Edge` 项目，并保留本地 Vite WebServer。
- 先用 `npm.cmd ci` 按 `package-lock.json` 恢复本地遗漏的 Playwright 包；随后在 `web` 目录执行 `npm.cmd run e2e`，结果为 2 项通过：桌面视口创建 Mock 任务并显示审批控件，以及 390px 视口核心控件可见且无横向溢出。
- 同次验证执行 `npm.cmd test -- --run`，结果为 Vitest `5 passed`；执行 `npm.cmd run build`，TypeScript 与 Vite 构建通过。Vite 输出一条既有配置迁移预告：未来 native config loader 不支持当前 CommonJS 加载的 ESM `vite.config.ts`，未影响退出状态。
- Task 20 的浏览器 E2E 验收现已通过；验证浏览器为本机 Microsoft Edge，而非下载失败的 Playwright Chromium。

## 2026-08-12 — Task 21 / Task 4：质量验证与过程记录

- 在隔离 worktree `C:\Users\sy444\Desktop\Agents\.worktrees\task-21-textual-api-console` 执行最终 Python 质量验证，并将当前 worktree 的 `src` 置于 `PYTHONPATH` 首位，避免共享虚拟环境的 editable 安装覆盖本分支源码。
- 实际结果：`python -m pytest -q` 为 `79 passed, 15 warnings`；`ruff check .` 为 `All checks passed!`；`mypy src` 为 `Success: no issues found in 30 source files`。15 条警告为既有 FastAPI `on_event` 与 Starlette TestClient/httpx 弃用警告，未影响命令退出状态。
- Task 21 的 Textual TUI 核心流程已由 `tests/integration/test_tui.py` 的 `run_test` 与可注入 fake client 覆盖；测试不发起真实网络请求，也不依赖浏览器或 Playwright。Task 3 的最终针对性结果为 `23 passed`，覆盖创建后进入运行观察、增量事件回放/去重、审批、取消/恢复、错误恢复和终态结果界面。
- 已检查本任务变更的过程文档与任务报告，无占位语、凭据或不相关改动。Task 20 的 `npm run e2e` 仍未补跑：Chromium 两次下载均在网络阶段超时；因此不能将全仓浏览器 E2E 验收表述为通过。

## 2026-08-12 — Task 20（暂定完成，待补 Playwright）

- 已在隔离分支 `codex/task-20-webui-console` 实现浏览器 WebUI 的 Mock 任务创建、任务详情、取消/恢复、审批决定、事件时间线、基础 SSE 接入和响应式布局。
- 红绿证据：任务表单红灯为 2 项失败，绿灯为 Vitest `2 passed`；观察组件红灯为缺失组件，绿灯为 Vitest `4 passed`；REST 详情/取消红灯为详情未加载，绿灯为 Vitest `5 passed`。Vite build 均通过。
- Playwright：已配置桌面和 390px 验收，首次运行因 Chromium 缺失失败；两次 `npx playwright install chromium` 均在下载阶段超时（最后一次等待 5 分钟无输出），因此 `npm run e2e` 尚未通过，需在网络可下载浏览器的环境补跑。
- 用户于 2026-08-12 授权暂时将 Task 20 视为已完成，并继续 Task 21；不得将 Playwright 验收写为通过。
- 代码提交：`8ac0a57`、`3f3e170`、`416ef28`、`b5d30f2`。

## 2026-08-11 — Task 20 / Task 1

- 红灯：`cd web; npm test -- --run src/App.test.tsx`，结果为 2 项失败；页面未调用 `POST /api/tasks`，且缺少 Mock 决策输入。
- 绿灯：新增前端类型、`createTask` API 客户端及 `TaskForm` 后，同一命令为 `2 passed`；`npm run build` 通过。
- 修正：首次绿灯检查发现 user-event 将 `{` 解析为按键描述符、API 泛型响应未完成运行时收窄；将测试改为字面量转义输入，并在客户端检查错误响应对象后通过。
- 代码提交：`8ac0a57`（`feat: add web task creation client`）。

## 2026-08-09 — Task 18

- 使用 `superpowers:brainstorming`、`writing-plans` 和 `executing-plans` 完成单机、单任务、Mock LLM CLI 闭环；在 `codex/task-18-mock-runtime` 隔离 worktree 中实施。
- 红灯：场景加载器、审批结果模型、SQLite 状态更新和 TaskService 均按预期先缺失；分别以最小实现转绿。
- 调试：TaskService 集成测试暴露嵌套 `.code-agent/state.db` 的父目录不存在；根因是 `SQLiteStore` 直接连接路径。新增回归测试后由存储层创建父目录。
- 绿灯与最终验证：pytest `44 passed`，Ruff、Mypy 通过，Mock 机制演示通过。
- 实现：严格 JSON Mock 场景、`y/a/n` CLI 审批、任务和审批 SQLite 持久化、`TaskService` 与真实 `code-agent run` 执行链路。

## 2026-08-06 — Final branch review

- Task 4–17 已完成最小实现并分别提交；完整 Python 验证为 `36 passed`，Ruff/Mypy/diff check 通过。
- WebUI 验证：Vitest `2 passed`，Vite build 成功。
- Windows 无 `make` 命令，故使用等价底层命令验证；CI 文件仍保留课程要求的 `make verify` 入口。

## 2026-08-06 — Task 17

- 红灯：demo smoke test 因 `demos/mock_feedback_loop.py` 缺失而失败。
- 绿灯与最终验证：demo 输出 `guardrail=denied`、`feedback_loop=succeeded`；完整 pytest `36 passed`；Ruff、Mypy、diff check 通过。
- 添加 GitHub/GitLab CI、机制 demo、README 和过程文档收尾记录。

## 2026-08-06 — Task 16

- 红灯：WebUI 测试因文件不存在而失败。
- 修正后验证：Vitest `2 passed`；Vite build 成功；实现紧凑任务控制台、Goal 校验和基础响应式样式。

## 2026-08-06 — Task 15

- 红灯：TUI 测试因 `CodeAgentTui` 缺失而失败。
- 绿灯：目标测试 `1 passed`；Ruff、Mypy 通过；实现启动屏及最小 Run/Approval/Result 屏幕骨架。

## 2026-08-06 — Task 14

- 红灯：CLI 测试因 `code_agent.cli` 缺失而失败。
- 绿灯：目标测试 `2 passed`；Ruff、Mypy 通过；实现 Typer 基础命令和不回显密钥的 keyring auth 状态管理。

## 2026-08-06 — Task 13

- 红灯：API 测试因 `create_app` 缺失而失败。
- 绿灯：目标测试 `2 passed`；Ruff、Mypy 通过；实现任务创建、workspace 校验、事件 JSON 回放和 SSE 流。

## 2026-08-06 — Task 12

- 红灯：storage 集成测试因 `SQLiteStore` 缺失而失败。
- 绿灯：目标测试 `2 passed`；完整 pytest `30 passed`；Ruff、Mypy 通过；实现任务、事件顺序回放和 checkpoint 往返持久化。

## 2026-08-06 — Task 10–11

- Task 10 红灯：loop 测试因 `LoopController` 缺失而失败；绿灯后完整测试 `25 passed`。
- Task 11 红灯：SubAgent 测试因 scheduler 缺失而失败；绿灯后完整测试 `28 passed`。
- Ruff、Mypy 均通过；实现反馈驱动循环、验收检查、事件记录、SubAgent 深度/预算/写入约束和结构化结果。

## 2026-08-06 — Task 9

- 红灯：hook 测试因 `HookRunner` 缺失而失败。
- 绿灯：目标测试 `2 passed`；Ruff、Mypy 通过；实现注册顺序、阻断合并、反馈合并与异常反馈。

## 2026-08-06 — Task 8

- 红灯：memory/context 测试因模块缺失而失败。
- 绿灯：目标测试 `3 passed`；Ruff、Mypy 通过；实现候选/已验证记忆、检索、上下文分节与敏感信息脱敏。

## 2026-08-06 — Task 7

- 红灯：LLM provider 测试因 `code_agent.core.llm` 缺失而失败。
- 绿灯：目标测试 `2 passed`；Ruff、Mypy 通过；实现 Mock 顺序决策、耗尽错误和兼容 OpenAI 的 provider。

## 2026-08-06 — Task 6

- 红灯：`test_feedback.py` 因 `FeedbackAdapter` 缺失而失败。
- 绿灯：目标测试 `3 passed`；Ruff、Mypy 通过；实现 exit code、pytest、TypeScript、Go、Maven 和通用 stderr 指纹解析。

## 2026-08-06 — Task 5

- TDD 红灯：新增检测/shell 测试后，因 `project_detection` 缺失而失败。
- 绿灯与质量验证：完整 pytest `14 passed`；Ruff 和 Mypy 通过。
- 实现：项目生态检测、验证命令生成、安全 shell/run_check 执行、超时处理和凭据环境变量过滤。

## 2026-08-06 — Task 4

- TDD 红灯：`.venv\\Scripts\\python.exe -m pytest tests/unit/test_workspace_tools.py -q`；按预期缺少 `code_agent.core.tools`。
- 绿灯与质量验证：目标测试 `3 passed`；完整 pytest `12 passed`；Ruff 和 Mypy 通过。
- 实现：workspace 路径边界、写锁、UTF-8 文件读写、搜索、目录列举、删除、git diff 和受控错误结果。

## 2026-08-06 — Task 3

- 触发技能：`subagent-driven-development`、`test-driven-development`。
- 红灯：`.venv\Scripts\python.exe -m pytest tests/unit/test_policy.py -q`；按预期因 `code_agent.core.policy` 缺失而在收集阶段失败。
- 初次绿灯：策略测试 `4 passed`，完整 pytest `9 passed`；随后 Ruff/Mypy 发现测试行过长和可选字典类型窄化问题。
- 修正后验证：策略测试 `4 passed`；完整 pytest `9 passed`；Ruff `All checks passed!`；Mypy `Success: no issues found in 5 source files`。
- 人工干预：委派 subagent 因运行环境无响应而关闭，随后由主 Agent 接手；未实现 Task 4。
- 提交：代码 `b808855`；验证日志 `b02d5df`。评审 subagent 因环境无响应关闭；人工按 brief 复核策略矩阵、禁止片段、临时授权和审批追加式语义，未发现 Critical/Important 问题。

## 2026-08-06 — Task 2

- 触发技能：`subagent-driven-development`、`test-driven-development`。
- 红灯：`.venv\Scripts\python.exe -m pytest tests/unit/test_models.py -q`；按预期因 `code_agent.core.models` 缺失而在收集阶段失败。
- 绿灯：目标测试 `4 passed`；完整 pytest `5 passed`；Ruff `All checks passed!`；Mypy `Success: no issues found in 4 source files`。
- 人工干预：委派 subagent 因运行环境无响应而关闭，随后由主 Agent 按 Task 2 brief 接手；未实现 Task 3。
- 提交：代码 `5817d2e`；验证日志 `002a5c4`。独立评审 subagent 同样因环境无响应关闭；人工按 brief 对照接口、枚举值、字段、协议和范围复核，未发现 Critical/Important 问题。

## 2026-08-06 — Task 1

- 触发技能：`using-git-worktrees`、`subagent-driven-development`、`test-driven-development`。
- 工作区：`codex/task-1-package-skeleton`。
- 红灯：`.venv\Scripts\python.exe -m pytest tests/unit/test_imports.py -q`；按预期失败，原因是 `ModuleNotFoundError: No module named 'code_agent'`。
- 绿灯：`.venv\Scripts\python.exe -m pip install -e ".[dev]"` 后运行目标测试，结果 `1 passed`。
- 相关验证：完整 pytest `1 passed`；Ruff `All checks passed!`；Mypy `Success: no issues found in 2 source files`。
- 环境说明：Windows 环境未提供 `make` 命令，因此未能直接执行 Makefile 入口；对应底层 pytest、Ruff 和 Mypy 命令均已验证。
- 人工干预：委派 subagent 因运行环境无响应而关闭，随后由主 Agent 按同一 brief 接手；未实现后续任务。
- 提交：代码 `c48babf`；验证日志 `28f3ce4`。任务级人工规格/质量复核未发现超出 Task 1 范围的问题；`code-agent` CLI 的实际实现属于后续任务。

按时间顺序记录 AI 协作开发过程中的关键事件。

## 2026-07-10

- 初始化本地 Git 仓库。
- 添加课程要求文档和基础 `.gitignore`。
- 确定项目方向为 AI4SE 项目 A：Coding Agent Harness。
- 在实现开始前添加项目文档占位文件。
- 连接 GitHub 远程仓库并推送 `main` 分支。
# 2026-08-13：Task 23

- 使用 `superpowers:executing-plans` 在隔离 worktree `codex/task-23-lifecycle-provider` 中执行。
- Task 1 红灯：ProviderFactory 模块不存在；绿灯：Provider/API 测试 `10 passed`，Ruff 与 Mypy 通过。
- Task 2 红灯：artifact 路由不存在；绿灯：CLI/API 测试 `17 passed`，Ruff 与 Mypy 通过。
- Task 3 红灯：TUI 无 Provider 输入；绿灯：TUI 测试 `29 passed`，Ruff 与 Mypy 通过。
- Task 4 红灯：WebUI 无 Provider 控件；绿灯：Vitest `6 passed`，Vite/TypeScript build 通过。
- Task 5 红灯：`web_assets` 与 `web` 命令不存在；绿灯：Python 全量 `124 passed, 1 skipped`，Ruff/Mypy、WebUI 测试/build、sdist/wheel、CLI help/web help 通过。
- Task 6 红灯：四个 demo 入口不存在；绿灯：demo 验收 `5 passed`，bugfix 记录一次失败反馈并改变下一轮动作。
- 已知警告：既有 FastAPI/Starlette `on_event` 弃用警告；Vite 配置存在 native config loader 迁移警告，均不影响退出状态。
