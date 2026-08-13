# Task 23：生命周期契约与全端 Provider 贯通实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施。步骤使用 checkbox（`- [ ]`）跟踪。

**目标：** 补齐当前规格缺口，使 CLI/API 生命周期、真实 Provider、TUI/WebUI、Web 启动分发和规格级演示形成可离线验收的闭环。

**架构：** 新增统一 `ProviderFactory`，由 CLI、FastAPI、TUI 和 WebUI 共享 Provider 名称解析、配置校验、keyring 读取和安全错误边界。API 与客户端复用现有 TaskManager、SQLite 和 SSE；Web 启动负责装配 FastAPI 和已构建静态资源。

**技术栈：** Python 3.12、FastAPI、Pydantic、Typer、Textual、SQLite、httpx、keyring、pytest、Ruff、Mypy、React、TypeScript、Vite、Vitest、Playwright。

## 全局约束

- 默认测试不得访问网络或真实密钥；真实 Provider E2E 仅显式开启。
- 客户端只提交 Provider 名称和 Mock 决策，不提交端点、模型或密钥。
- 非 Mock 缺少档案、配置无效、URL 不安全或 keyring 缺失时，必须在请求前失败，绝不回退。
- 用户可见错误固定、简短、中文，不得包含密钥、Authorization、响应正文或底层异常。
- Task、Event、Approval、Report、SQLite 和模型上下文只保存 Provider 名称及非敏感证据。
- 不修改既有 SQLite 表结构、Task 19 HTTP/SSE 事件格式、Policy Engine 硬性拒绝规则或 Mock 语义。
- 文档和过程记录使用中文；不实现云端多用户、在线编辑器、自动 PR 或自动部署。

---

### Task 1：抽取 ProviderFactory 并接入 API

**文件：** 新建 `src/code_agent/application/providers.py`、`tests/unit/test_providers.py`；修改 `src/code_agent/cli.py`、`src/code_agent/api/app.py`、`src/code_agent/api/schemas.py`、`tests/integration/test_api_sse.py`。

**接口：** `build_provider(name, workspace, *, mock_decisions=None, allow_development_fallback=False) -> tuple[LLMProvider, str]`；`ProviderFactoryError(ValueError)`。

- [ ] **步骤 1：写失败测试。** 断言 `build_provider("mock", tmp_path, mock_decisions=[complete])` 返回 Mock 和名称 `mock`；API 以 `provider="openai"` 且无档案创建任务返回安全 400，且 TaskManager 未收到提交。
- [ ] **步骤 2：运行红灯。** `$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_providers.py tests/integration/test_api_sse.py -q`；预期因工厂模块和 API 装配不存在而失败。
- [ ] **步骤 3：最小实现。** `mock` 只接受显式决策；其他名称调用既有规范化、配置解析、keyring 和 OpenAICompatibleProvider；所有异常转换为固定中文 ProviderFactoryError。API 在边界调用工厂并把实例传给 `TaskManager.submit`；CLI 删除重复构造逻辑。
- [ ] **步骤 4：绿灯与静态检查。** 运行上述 pytest、`ruff check src tests/unit/test_providers.py`、`mypy src`。
- [ ] **步骤 5：提交。** `git add src/code_agent/application/providers.py src/code_agent/api src/code_agent/cli.py tests/unit/test_providers.py tests/integration/test_api_sse.py; git commit -m "refactor: share provider factory across cli and api"`。

### Task 2：补齐 API artifact 与 CLI 生命周期命令

**文件：** 修改 `src/code_agent/api/app.py`、`src/code_agent/cli.py`；新建 `src/code_agent/cli_api.py`、`tests/integration/test_api_artifacts.py`；修改 `tests/integration/test_cli.py`、`tests/integration/test_cli_runtime.py`。

**接口：** 新增 `GET /api/tasks/{id}/diff`、`GET /api/tasks/{id}/report`；新增 CLI `status`、`approve`、`reject`、`resume`、`attach`、`web`；client 提供 `get_status`、`decide_approval`、`resume_task`、`get_diff`、`get_report`。

- [ ] **步骤 1：写失败测试。** API artifact 路由断言返回 status/report/verification/diff；CliRunner 调用 `status <id> --url http://127.0.0.1:8000 --json` 断言稳定 JSON。
- [ ] **步骤 2：运行红灯。** `$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -m pytest tests/integration/test_api_artifacts.py tests/integration/test_cli.py tests/integration/test_cli_runtime.py -q`；预期路由和命令不存在。
- [ ] **步骤 3：最小实现。** artifact 只读任务结果、事件和受控 workspace diff；CLI 通过 client 调用现有状态机，不复制审批逻辑；错误固定中文。
- [ ] **步骤 4：绿灯、Ruff、Mypy；检查错误输出不含底层响应正文。**
- [ ] **步骤 5：提交。** `git add src/code_agent/api/app.py src/code_agent/cli.py src/code_agent/cli_api.py tests/integration/test_api_artifacts.py tests/integration/test_cli.py tests/integration/test_cli_runtime.py; git commit -m "feat: complete api artifacts and lifecycle cli"`。

### Task 3：贯通 TUI Provider 与生命周期客户端

**文件：** 修改 `src/code_agent/tui/api.py`、`src/code_agent/tui/screens.py`、`src/code_agent/tui/app.py`；新建/修改 `tests/integration/test_tui_provider.py`、`tests/integration/test_tui.py`。

**接口：** Provider 表单接受任意合法名称；Mock 决策只在 `mock` 时发送；任务详情只显示名称；审批、取消、恢复和事件游标保持既有契约。

- [ ] **步骤 1：写失败测试。** fake client 接收 `provider="openai"` 时断言 payload 不含 `mock_decisions`，并断言详情不渲染密钥/端点。
- [ ] **步骤 2：运行红灯。** `$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -m pytest tests/integration/test_tui_provider.py tests/integration/test_tui.py -q`。
- [ ] **步骤 3：最小实现。** 复用名称规范化；非 Mock 禁用 Mock 输入；错误转换为固定中文通知；不改变轮询、游标、审批 actor 和终态页面。
- [ ] **步骤 4：运行 TUI pytest、Ruff、Mypy。**
- [ ] **步骤 5：提交。** `git add src/code_agent/tui tests/integration/test_tui_provider.py tests/integration/test_tui.py; git commit -m "feat: select providers from textual task console"`。

### Task 4：贯通 WebUI Provider 与生命周期操作

**文件：** 修改 `web/src/types.ts`、`web/src/api.ts`、`web/src/components/TaskForm.tsx`、`web/src/App.tsx`、`web/src/App.test.tsx`；新建 `web/src/provider.test.tsx`。

**接口：** `TaskCreateInput.provider: string`；Mock 决策仅对 `mock` 显示/发送；详情面板提供状态、审批、取消、恢复、diff/report；SSE 重连保留游标。

- [ ] **步骤 1：写失败 Vitest。** 输入 `openai` 创建任务，断言请求 body 含 provider 且不含 `mock_decisions`；错误界面不渲染服务端原始异常。
- [ ] **步骤 2：运行红灯。** `cd web; npm.cmd test -- --run src/provider.test.tsx`。
- [ ] **步骤 3：最小实现。** 扩展类型、client 和表单；详情控件调用已存在 API/SSE；不保存端点、模型或密钥到前端状态。
- [ ] **步骤 4：运行 `npm.cmd test -- --run`、`npm.cmd run build`。**
- [ ] **步骤 5：提交。** `git add web/src; git commit -m "feat: expose providers and lifecycle controls in web console"`。

### Task 5：实现 `code-agent web` 与干净环境分发

**文件：** 修改 `src/code_agent/cli.py`、`src/code_agent/api/app.py`、`pyproject.toml`；新建 `src/code_agent/web_assets.py`；修改 `tests/integration/test_cli_runtime.py`、`tests/integration/test_api_sse.py`、`web/vite.config.ts`。

**接口：** `code-agent web` 默认 `127.0.0.1:8000`，支持 host/port；`static_dist_path() -> Path | None`；`mount_web_assets(app) -> None`。

- [ ] **步骤 1：写失败测试。** monkeypatch `uvicorn.run`，调用 `web`，断言 host/port；静态目录存在时断言非 API 路径返回 index，API 路径优先。
- [ ] **步骤 2：运行红灯。** `$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -m pytest tests/integration/test_cli_runtime.py -q`；预期命令和挂载不存在。
- [ ] **步骤 3：最小实现。** `web` 调用 `uvicorn.run(create_app(), host, port)`；静态目录不存在时只提供 API；pyproject 声明静态包数据。
- [ ] **步骤 4：运行 WebUI test/build、Python pytest/Ruff/Mypy 和 `.venv\\Scripts\\python.exe -m build`；临时环境安装 wheel 后验证 `code-agent --help`、Mock run、`code-agent web --help`。**
- [ ] **步骤 5：提交。** `git add src/code_agent/cli.py src/code_agent/api/app.py src/code_agent/web_assets.py pyproject.toml web/vite.config.ts tests/integration/test_cli_runtime.py tests/integration/test_api_sse.py; git commit -m "feat: package and serve web console"`。

### Task 6：四类规格级演示与最终验收记录

**文件：** 新建 `demos/task23_feature.py`、`demos/task23_bugfix.py`、`demos/task23_tests.py`、`demos/task23_refactor.py`、`tests/integration/test_task23_demos.py`；修改 `AGENT_LOG.md`、`SPEC_PROCESS.md`、`README.md`、`.github/workflows/ci.yml`、`.gitlab-ci.yml`。

**接口：** 每个演示接受临时 workspace，使用 Mock Provider，输出结构化 JSON 结果和验证证据；CI 默认离线执行 Python/前端检查、包构建和凭据扫描。

- [ ] **步骤 1：写失败测试。** 参数化四类 demo，断言 `status == "succeeded"`、verification 非空、provider 为 `mock`。
- [ ] **步骤 2：运行红灯。** `$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -m pytest tests/integration/test_task23_demos.py -q`；预期 demo 入口不存在。
- [ ] **步骤 3：最小实现。** 仅使用临时目录和 Mock 场景；bugfix 必须注入一次失败反馈并证明下一轮动作改变；输出不含凭据或原始 transcript。
- [ ] **步骤 4：更新 CI 和中文过程文档，记录红绿命令、跳过项、警告和环境限制。**
- [ ] **步骤 5：最终验证。** `$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -m pytest -q; .\\.venv\\Scripts\\ruff.exe check .; .\\.venv\\Scripts\\mypy.exe src; cd web; npm.cmd test -- --run; npm.cmd run build; cd ..; .\\.venv\\Scripts\\python.exe -m build`。
- [ ] **步骤 6：提交。** `git add demos tests/integration/test_task23_demos.py AGENT_LOG.md SPEC_PROCESS.md README.md .github/workflows/ci.yml .gitlab-ci.yml; git commit -m "test: add task 23 demos and final acceptance evidence"`。

## 计划自检

- 规格覆盖：Task 1 ProviderFactory/API；Task 2 API artifacts/CLI 生命周期；Task 3/4 TUI/WebUI Provider 与共享操作；Task 5 web 启动、静态资源和干净安装；Task 6 演示、CI 和最终证据。
- 类型一致性：Task 1 定义 ProviderFactory，Task 2–4 消费同一工厂和 API；Task 5 复用 create_app；Task 6 只调用已验证 Mock 路径。
- 占位扫描：无 TBD、TODO、implement later、模糊错误处理或未定义后续接口。

