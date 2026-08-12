# Task 21：Textual TUI 接入任务 API 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` 按任务逐项实施。步骤使用 checkbox（`- [ ]`）跟踪。

**目标：** 让现有 Textual TUI 通过 Task 19 的任务 API 创建和观察单个 Mock 任务，并完成审批、取消、安全恢复与结果查看的完整控制台流程。

**架构：** 新增轻量 `TaskApiClient`，集中封装 REST 请求与可测试的错误转换；`CodeAgentTui` 持有任务会话状态和可注入客户端；Start、Run、Approval、Result 四个屏幕分别承担创建、轮询观察、审批决策和终态展示。运行屏幕每 500ms 获取任务详情并以 `after=last_sequence` 增量回放 JSON 事件，绝不直接解析 SSE 流。

**技术栈：** Python 3.11、Textual、httpx、pytest、pytest-asyncio、Ruff、Mypy。

## 全局约束

- 只改动 TUI、其测试及过程文档；不改变 Task 19 API、任务状态机和 WebUI。
- API 路径、字段和状态值以 `src/code_agent/api/app.py` 与 `src/code_agent/domain/models.py` 为准。
- 所有用户可见报错使用简短中文通知，不展示 traceback、请求头或认证信息。
- 事件游标单调递增：仅追加 `sequence > last_sequence` 的事件；断线或请求失败后保留游标并在下个轮询周期重试。
- `r` 仅在任务显示为 `cancelled` 时提供；服务端仍是恢复安全性的最终裁决者，收到 409 时仅通知用户并保持当前界面。

### 任务 1：建立可注入的任务 API 客户端

**文件：**

- 新建：`src/code_agent/tui/api.py`
- 新建：`tests/integration/test_tui_api.py`

- [ ] 先编写失败测试：用 `httpx.MockTransport` 模拟 Task 19 响应，断言客户端会向正确路径提交创建、详情、事件、取消、恢复和审批请求；事件请求带上 `after`，审批请求带上 `approved`、`scope` 与 `actor`。
- [ ] 增加失败测试：非 2xx 响应和无效 JSON 都被转换为不泄露内部细节的 `TaskApiError`，供界面统一提示。
- [ ] 运行 ` .venv\Scripts\python.exe -m pytest tests/integration/test_tui_api.py -q`，确认测试先失败。
- [ ] 实现 `TaskApiClient`：构造函数接受 `base_url` 与可选 `httpx.Client`；提供 `create_task`、`get_task`、`get_events`、`cancel_task`、`resume_task`、`decide_approval` 六个同步方法，并把响应解码为字典。
- [ ] 再运行同一测试，确认通过；执行 `ruff check` 与 `mypy` 覆盖新增模块。

### 任务 2：把启动屏幕改为可创建 Mock 任务的表单

**文件：**

- 修改：`src/code_agent/tui/app.py`
- 修改：`src/code_agent/tui/screens.py`
- 修改：`tests/integration/test_tui.py`

- [ ] 先编写失败的 Textual 集成测试：断言启动后存在 workspace、goal、mode、mock decisions 输入控件；填入值并提交后，伪客户端收到合法任务创建载荷，应用保存任务 ID 并切换到 RunScreen。
- [ ] 增加失败测试：空 workspace 或空 goal 不发请求，屏幕给出中文校验提示。
- [ ] 运行 ` .venv\Scripts\python.exe -m pytest tests/integration/test_tui.py -q`，确认新增断言失败。
- [ ] 在 `CodeAgentTui` 增加可注入 `TaskApiClient`、当前任务 ID、最新事件序号、任务详情和事件列表；不在构造或挂载阶段发起网络请求。
- [ ] 把 `StartScreen` 实现为表单：workspace、goal、mode 及 JSON 格式 mock decisions；提交时调用客户端、初始化会话状态并进入运行屏幕。对 JSON 格式错误和 API 错误只显示中文通知。
- [ ] 重跑 TUI 测试，确保既有“启动时处于 StartScreen”的回归测试仍通过。

### 任务 3：实现运行观察、审批、取消/恢复与结果界面

**文件：**

- 修改：`src/code_agent/tui/app.py`
- 修改：`src/code_agent/tui/screens.py`
- 修改：`tests/integration/test_tui.py`

- [ ] 先编写失败测试：RunScreen 首次轮询读取详情和 `after=0` 的事件；再次轮询只请求并追加更大 sequence 的事件，重复 sequence 不重复显示。
- [ ] 增加失败测试：进入 `waiting_approval` 且存在待审批项时自动进入 ApprovalScreen；按 `y`、`a`、`n` 分别提交一次允许、任务范围允许和拒绝，并返回运行观察。
- [ ] 增加失败测试：`c` 调用取消；任务为 `cancelled` 时 `r` 调用恢复；取消、恢复或轮询返回 API 错误时只显示通知，界面与游标保持可用。
- [ ] 增加失败测试：终态任务进入 ResultScreen，并显示状态、任务 ID、结果报告（若详情尚未提供则显示“服务端未提供结果报告”）及最近事件摘要。
- [ ] 运行针对性测试，确认先失败。
- [ ] 使用 Textual 定时器/worker 实现 500ms 单飞轮询：获取详情，再按当前游标获取事件；请求异常不清零游标，下一周期继续尝试；离开 RunScreen 时取消轮询。
- [ ] 实现状态面板、最近事件列表与快捷键。审批屏从 `pending_approvals` 提取当前项，actor 固定为 `tui-user`；取消和恢复完成后立即刷新详情。
- [ ] 实现终态路由：`succeeded`、`needs_review`、`blocked`、`failed`、`budget_exhausted`、`cancelled` 均停止轮询并进入 ResultScreen。
- [ ] 重跑 TUI 测试，确认交互、增量回放、错误恢复和终态渲染均通过。

### 任务 4：完成质量验证与过程记录

**文件：**

- 修改：`AGENT_LOG.md`
- 修改：`SPEC_PROCESS.md`

- [ ] 执行完整验证：` .venv\Scripts\python.exe -m pytest -q`、` .venv\Scripts\ruff.exe check .`、` .venv\Scripts\mypy.exe src`。
- [ ] 使用 Textual 的 `run_test` 覆盖核心流程，不引入真实网络、浏览器或 Playwright 依赖。
- [ ] 在过程文档以中文记录 Task 21 的完成范围、验证命令及实际结果；如存在外部环境限制，明确记录而不把它写成通过。
- [ ] 检查变更和文档，确认没有占位语、敏感信息或与任务无关的修改后提交。
