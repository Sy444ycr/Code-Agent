# Task 22：多 OpenAI-compatible Provider 安全配置实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施。步骤使用 checkbox（`- [ ]`）跟踪。

**目标：** 支持多个命名的 OpenAI-compatible Provider 档案，并在不破坏 Mock 离线流程的前提下提供双层配置、钥匙串凭据和安全的端到端调用路径。

**架构：** `config.py` 解析用户级和项目级 TOML 档案，并以项目级同名整体覆盖；`auth.py` 管理按 Provider 名称存储的钥匙串密钥与受控开发回退；`OpenAICompatibleProvider` 只接收已解析的档案和密钥；CLI、TaskService 与 TaskManager 注入统一的 `LLMProvider`，不再在运行内部硬编码 Mock。

**技术栈：** Python 3.12、Pydantic、TOML 标准库 `tomllib`、keyring、httpx、Typer、pytest、pytest-asyncio、Ruff、Mypy。

## 全局约束

- 配置优先级固定为：命令行显式 Provider 名称 > 项目级同名档案整体覆盖用户级档案 > 用户级档案 > 内置 `mock`；绝不按字段拼接同名档案。
- 非 Mock Provider 必须由 `--provider <名称>` 显式选择；档案不存在、配置无效、缺少密钥或 URL 不安全时在 HTTP 前用简短中文错误退出，绝不回退到其他档案或 Mock。
- 用户级路径为当前用户配置目录下的 `code-agent/config.toml`；项目级路径为 `<workspace>/.code-agent/config.toml`；配置文件只保存 `base_url` 和 `model`，不保存密钥。
- 仅 `localhost`、`127.0.0.1`、`::1` 可以使用 HTTP；任何其他主机必须使用 HTTPS。
- 钥匙串服务名为 `code-agent`，账户名为 Provider 名称。所有日志、事件、SQLite、报告、模型上下文、CLI 输出、命令参数与项目配置均不得出现密钥。
- `CODE_AGENT_PROVIDER_<规范化名称>_API_KEY` 仅在钥匙串缺失且显式允许开发回退时读取；所有该类环境变量必须在 Tool Executor 子进程中移除。
- 默认测试必须离线并使用 fake keyring/httpx transport；真实 Provider E2E 仅在 `CODE_AGENT_RUN_PROVIDER_E2E=1` 时运行，不进入默认 CI。
- 不修改 Task 19 的 HTTP/SSE 契约、WebUI、TUI 或数据库任务协议；文档和过程记录使用中文。

## 文件结构

- `src/code_agent/config.py`：`ProviderProfile`、TOML 读取、双层合并、URL 安全校验和档案解析。
- `src/code_agent/auth.py`：Provider 名称规范化、钥匙串读写、显式开发回退和密钥环境名列举。
- `src/code_agent/core/llm.py`：安全的 OpenAI-compatible HTTP 请求、响应校验与脱敏 Provider 异常。
- `src/code_agent/application/task_service.py`：接收外部 `LLMProvider` 与 Provider 名称，保留 Mock 分支兼容。
- `src/code_agent/application/task_manager.py`：后台 API 路径接收外部 Provider，而非内部固定 Mock。
- `src/code_agent/cli.py`：Provider 解析、CLI 中文错误、`auth` 命令和运行时依赖装配。
- `tests/unit/test_config.py`、`tests/unit/test_auth.py`、`tests/unit/test_llm.py`：配置、密钥与 HTTP 单元测试。
- `tests/integration/test_cli_runtime.py`、`tests/integration/test_task_manager.py`：Mock 回归与注入式真实 Provider 运行链路测试。
- `tests/integration/test_provider_e2e.py`：受环境开关保护的真实 Provider 最小集成测试。
- `.env.example`、`README.md`、`AGENT_LOG.md`、`SPEC_PROCESS.md`：开发回退说明、运行示例与中文验证证据。

### Task 1：实现 Provider 档案与双层配置解析

**文件：**

- 修改：`src/code_agent/config.py`
- 新建：`tests/unit/test_config.py`

**接口：**

- 产生：`ProviderProfile(name: str, base_url: str, model: str)`。
- 产生：`load_provider_profiles(workspace: Path, user_config_path: Path | None = None) -> dict[str, ProviderProfile]`。
- 产生：`resolve_provider_profile(name: str, workspace: Path, user_config_path: Path | None = None) -> ProviderProfile`。
- 产生：`ProviderConfigurationError(ValueError)`，其文本可安全显示给用户。

- [ ] **步骤 1：写入双层合并和 URL 拒绝测试**

```python
def test_project_profile_replaces_same_named_user_profile(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('[providers.openai]\nbase_url = "https://user.example/v1"\nmodel = "user"\n')
    project = tmp_path / ".code-agent"
    project.mkdir()
    (project / "config.toml").write_text(
        '[providers.openai]\nbase_url = "https://project.example/v1"\nmodel = "project"\n'
    )

    profiles = load_provider_profiles(tmp_path, user)

    assert profiles["openai"] == ProviderProfile(
        name="openai", base_url="https://project.example/v1", model="project"
    )


def test_rejects_non_local_http_profile_before_provider_creation(tmp_path: Path) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        '[providers.remote]\nbase_url = "http://example.com/v1"\nmodel = "x"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="HTTPS"):
        resolve_provider_profile("remote", tmp_path)
```

- [ ] **步骤 2：确认配置测试按预期失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -q
```

预期：失败原因是 `ProviderProfile` 和配置加载函数尚不存在。

- [ ] **步骤 3：实现最小配置模型与加载器**

```python
class ProviderProfile(BaseModel):
    name: str
    base_url: str
    model: str


def load_provider_profiles(
    workspace: Path, user_config_path: Path | None = None
) -> dict[str, ProviderProfile]:
    user_profiles = _read_profiles(user_config_path or default_user_config_path())
    project_profiles = _read_profiles(workspace / ".code-agent" / "config.toml")
    return {**user_profiles, **project_profiles}
```

`_read_profiles` 使用 `tomllib.loads`，拒绝未知字段、空名称、空模型、非字符串 URL 和错误 TOML；`resolve_provider_profile` 对缺失名称给出中文错误，并在解析阶段执行 HTTP/HTTPS 规则。

- [ ] **步骤 4：运行绿灯与静态检查**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -q
.\.venv\Scripts\ruff.exe check src/code_agent/config.py tests/unit/test_config.py
.\.venv\Scripts\mypy.exe src/code_agent/config.py
```

预期：测试与静态检查通过。

- [ ] **步骤 5：提交任务 1**

```powershell
git add src/code_agent/config.py tests/unit/test_config.py
git commit -m "feat: load multi-provider profiles"
```

### Task 2：实现命名钥匙串密钥与开发回退隔离

**文件：**

- 修改：`src/code_agent/auth.py`
- 修改：`src/code_agent/core/tools.py`
- 新建：`tests/unit/test_auth.py`
- 修改：`tests/unit/test_workspace_tools.py`
- 修改：`.env.example`

**接口：**

- 产生：`normalize_provider_name(provider: str) -> str`，只允许小写字母、数字、`-` 和 `_`。
- 产生：`get_provider_secret(provider: str, *, allow_development_fallback: bool) -> str | None`。
- 产生：`provider_secret_environment_names() -> set[str]`，至少覆盖实际读取过的 `CODE_AGENT_PROVIDER_*_API_KEY` 变量。

- [ ] **步骤 1：写入钥匙串账户与环境清理失败测试**

```python
def test_development_fallback_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("code_agent.auth.keyring.get_password", lambda *_: None)
    monkeypatch.setenv("CODE_AGENT_PROVIDER_OPENAI_API_KEY", "dev-secret")

    assert get_provider_secret("openai", allow_development_fallback=False) is None
    assert get_provider_secret("openai", allow_development_fallback=True) == "dev-secret"


def test_shell_removes_named_provider_development_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_AGENT_PROVIDER_DEEPSEEK_API_KEY", "dev-secret")
    result = ToolExecutor().execute(
        ToolAction(tool="shell", arguments={"command": "python -c \"import os; print(os.getenv('CODE_AGENT_PROVIDER_DEEPSEEK_API_KEY'))\""}),
        Workspace(tmp_path),
    )
    assert result.stdout.strip() == "None"
```

- [ ] **步骤 2：确认测试先失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_auth.py tests/unit/test_workspace_tools.py -q
```

预期：失败原因是受控开发回退和动态 Provider 环境变量清理不存在。

- [ ] **步骤 3：实现最小凭据与清理逻辑**

```python
def get_provider_secret(provider: str, *, allow_development_fallback: bool) -> str | None:
    normalized = normalize_provider_name(provider)
    secret = keyring.get_password(SERVICE_NAME, normalized)
    if secret is not None or not allow_development_fallback:
        return secret
    return os.environ.get(f"CODE_AGENT_PROVIDER_{normalized.upper().replace('-', '_')}_API_KEY")
```

Tool Executor 在构造子进程环境时过滤静态遗留密钥变量与名称匹配 `CODE_AGENT_PROVIDER_*_API_KEY` 的所有变量。`.env.example` 只示例空值，明确开发回退是明文且进程可见。

- [ ] **步骤 4：运行绿灯与静态检查**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_auth.py tests/unit/test_workspace_tools.py -q
.\.venv\Scripts\ruff.exe check src/code_agent/auth.py src/code_agent/core/tools.py tests/unit/test_auth.py tests/unit/test_workspace_tools.py
.\.venv\Scripts\mypy.exe src/code_agent/auth.py src/code_agent/core/tools.py
```

- [ ] **步骤 5：提交任务 2**

```powershell
git add src/code_agent/auth.py src/code_agent/core/tools.py tests/unit/test_auth.py tests/unit/test_workspace_tools.py .env.example
git commit -m "feat: secure named provider credentials"
```

### Task 3：加固 OpenAI-compatible HTTP Provider

**文件：**

- 修改：`src/code_agent/core/llm.py`
- 修改：`tests/unit/test_llm.py`

**接口：**

- 产生：`ProviderRequestError(RuntimeError)`，错误文本不含密钥、Authorization 值或响应正文。
- 修改：`OpenAICompatibleProvider(base_url: str, model: str, api_key_getter: Callable[[], str], client: httpx.Client | None = None)`。
- 保持：`decide(context: str) -> AgentDecision`。

- [ ] **步骤 1：写入 HTTP 契约与脱敏错误失败测试**

```python
import json

def test_openai_compatible_provider_posts_schema_and_parses_decision() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"action":"complete"}'}}]})

    provider = OpenAICompatibleProvider(
        "https://provider.example/v1", "model-x", lambda: "secret-value",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.decide("context").action == ActionType.COMPLETE
    assert seen["url"] == "https://provider.example/v1/chat/completions"
    assert seen["authorization"] == "Bearer secret-value"


def test_provider_error_does_not_echo_secret_or_response_body() -> None:
    provider = OpenAICompatibleProvider(
        "https://provider.example/v1",
        "model-x",
        lambda: "secret-value",
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, text="upstream-internal")
            )
        ),
    )
    with pytest.raises(ProviderRequestError) as exc_info:
        provider.decide("context")
    assert "secret-value" not in str(exc_info.value)
    assert "upstream-internal" not in str(exc_info.value)
```

- [ ] **步骤 2：确认 Provider 测试先失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_llm.py -q
```

预期：失败原因是构造函数尚不接受注入 HTTP client，且安全错误类型不存在。

- [ ] **步骤 3：实现最小 HTTP 与响应验证**

```python
try:
    response = self.client.post(
        f"{self.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {self.api_key_getter()}"},
        json=payload,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return AgentDecision.model_validate_json(content)
except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
    raise ProviderRequestError("Provider 返回无效响应") from exc
```

请求体固定包含模型、单条 user 消息与 `AgentDecision.model_json_schema()`；client 未注入时创建 `httpx.Client(timeout=60)`。异常消息不嵌入异常文本、请求头或响应 body。

- [ ] **步骤 4：运行绿灯与静态检查**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_llm.py -q
.\.venv\Scripts\ruff.exe check src/code_agent/core/llm.py tests/unit/test_llm.py
.\.venv\Scripts\mypy.exe src/code_agent/core/llm.py
```

- [ ] **步骤 5：提交任务 3**

```powershell
git add src/code_agent/core/llm.py tests/unit/test_llm.py
git commit -m "feat: harden openai compatible provider"
```

### Task 4：将 Provider 注入 TaskService 和后台 TaskManager

**文件：**

- 修改：`src/code_agent/application/task_service.py`
- 修改：`src/code_agent/application/task_manager.py`
- 修改：`src/code_agent/api/app.py`
- 修改：`tests/integration/test_task_service.py`
- 修改：`tests/integration/test_task_manager.py`
- 修改：`tests/integration/test_api_sse.py`

**接口：**

- 修改：`TaskService.run(workspace, goal, mode, provider: LLMProvider, provider_name: str, acceptance_checks) -> TaskRunResult`。
- 修改：`TaskManager.submit(task: Task, loop_spec: LoopSpec, provider: LLMProvider) -> Task`。
- 保持：Mock 调用方传入 `MockLLMProvider(decisions)` 与名称 `"mock"`。

- [ ] **步骤 1：写入 Provider 注入与任务名称持久化失败测试**

```python
def test_task_service_uses_injected_provider_and_persists_name(tmp_path: Path) -> None:
    provider = MockLLMProvider([AgentDecision(action=ActionType.COMPLETE)])
    service = TaskService(SQLiteStore(tmp_path / "state.db"))

    result = service.run(tmp_path, "finish", PermissionMode.AUTO, provider, "openai", [])

    assert result.status == TaskStatus.SUCCEEDED
    assert service.store.list_tasks()[0].provider == "openai"
    assert provider.contexts_seen
```

- [ ] **步骤 2：确认服务与后台测试先失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_task_service.py tests/integration/test_task_manager.py -q
```

预期：失败原因是运行链路仍要求 decisions 列表并固定创建 `MockLLMProvider`。

- [ ] **步骤 3：实现最小依赖注入**

```python
task = Task(workspace=str(resolved_workspace), goal=goal, mode=mode, provider=provider_name)
loop = LoopController(
    provider=provider,
    policy=PolicyEngine(),
    tools=ToolExecutor(),
    feedback=FeedbackAdapter(),
    approval_handler=self._approval_handler,
)
```

`TaskManager._run` 接收保存于运行时对象的 provider；API 当前的 Mock 请求解析在 API 边界构造 `MockLLMProvider` 后传给 TaskManager。不得修改现有 HTTP 路由、事件类型、审批状态机或 SQLite schema。

- [ ] **步骤 4：运行绿灯与相关回归**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_task_service.py tests/integration/test_task_manager.py tests/integration/test_api_sse.py -q
.\.venv\Scripts\ruff.exe check src/code_agent/application tests/integration/test_task_service.py tests/integration/test_task_manager.py
.\.venv\Scripts\mypy.exe src/code_agent/application
```

- [ ] **步骤 5：提交任务 4**

```powershell
git add src/code_agent/application/task_service.py src/code_agent/application/task_manager.py src/code_agent/api/app.py tests/integration/test_task_service.py tests/integration/test_task_manager.py tests/integration/test_api_sse.py
git commit -m "refactor: inject providers into task runtime"
```

### Task 5：接入 CLI Provider 选择、认证命令与离线回归

**文件：**

- 修改：`src/code_agent/cli.py`
- 修改：`tests/integration/test_cli.py`
- 修改：`tests/integration/test_cli_runtime.py`
- 修改：`README.md`

**接口：**

- 产生：`build_provider(name: str, workspace: Path, *, allow_development_fallback: bool = False) -> tuple[LLMProvider, str]`。
- 保持：`code-agent run <workspace> <goal> --provider mock --mock-decisions <path>`。
- 新增：`code-agent run <workspace> <goal> --provider openai`。

- [ ] **步骤 1：写入非 Mock 显式选择和无回退失败测试**

```python
def test_cli_rejects_unknown_provider_without_loading_mock(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", str(tmp_path), "goal", "--provider", "missing"])

    assert result.exit_code == 2
    assert "Provider 档案不存在" in result.output
    assert "mock" not in result.output.lower()


def test_cli_runs_injected_openai_compatible_profile_without_mock_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("code_agent.cli.build_provider", lambda *args, **kwargs: (MockLLMProvider([AgentDecision(action=ActionType.COMPLETE)]), "openai"))

    result = CliRunner().invoke(app, ["run", str(tmp_path), "goal", "--provider", "openai", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "succeeded"
```

- [ ] **步骤 2：确认 CLI 测试先失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_cli.py tests/integration/test_cli_runtime.py -q
```

预期：失败原因是 CLI 仅接受 `mock`，并且非 Mock 运行需要 `--mock-decisions`。

- [ ] **步骤 3：实现最小选择与认证行为**

```python
if provider == "mock":
    if mock_decisions is None:
        raise typer.BadParameter("mock Provider 必须提供 --mock-decisions")
    llm_provider = MockLLMProvider(load_mock_decisions(mock_decisions))
else:
    if mock_decisions is not None:
        raise typer.BadParameter("非 Mock Provider 不接受 --mock-decisions")
    llm_provider, provider_name = build_provider(provider, workspace)
```

`build_provider` 解析档案、读取密钥、创建 `OpenAICompatibleProvider`。`auth set/status/clear` 规范化 Provider 名称；所有 CLI 错误使用简短中文，不输出 keyring/httpx 原始异常。README 只展示不含密钥的 TOML 和 `auth set <name>` 示例。

- [ ] **步骤 4：运行绿灯与 Mock 回归**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_cli.py tests/integration/test_cli_runtime.py tests/integration/test_api_sse.py -q
.\.venv\Scripts\ruff.exe check src/code_agent/cli.py tests/integration/test_cli.py tests/integration/test_cli_runtime.py
.\.venv\Scripts\mypy.exe src/code_agent/cli.py
```

- [ ] **步骤 5：提交任务 5**

```powershell
git add src/code_agent/cli.py tests/integration/test_cli.py tests/integration/test_cli_runtime.py README.md
git commit -m "feat: select configured providers from cli"
```

### Task 6：添加受开关保护的真实 Provider E2E 与完成记录

**文件：**

- 新建：`tests/integration/test_provider_e2e.py`
- 修改：`.env.example`
- 修改：`README.md`
- 修改：`AGENT_LOG.md`
- 修改：`SPEC_PROCESS.md`

**接口：**

- 产生：真实 E2E 启用条件 `CODE_AGENT_RUN_PROVIDER_E2E=1`。
- 产生：可选环境变量 `CODE_AGENT_PROVIDER_E2E_NAME`，默认 `openai`，仅用于选择档案名称而不存放密钥。

- [ ] **步骤 1：写入默认跳过的真实 E2E 测试**

```python
@pytest.mark.skipif(
    os.environ.get("CODE_AGENT_RUN_PROVIDER_E2E") != "1",
    reason="真实 Provider E2E 需要显式启用",
)
def test_configured_provider_returns_a_structured_decision(tmp_path: Path) -> None:
    provider, _ = build_provider(os.environ.get("CODE_AGENT_PROVIDER_E2E_NAME", "openai"), tmp_path)

    decision = provider.decide("只返回 action 为 complete 的 JSON 决策")

    assert isinstance(decision, AgentDecision)
```

- [ ] **步骤 2：确认默认测试会跳过且不访问网络**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_provider_e2e.py -q
```

预期：`1 skipped`，不读取钥匙串、不发送 HTTP 请求。

- [ ] **步骤 3：实现最小文档与环境示例**

在 `.env.example` 和 README 说明：密钥优先保存于 keyring；开发回退需显式允许；真实 E2E 需同时设置开关、配置非敏感档案并通过 `auth set <name>` 提供密钥。不得在示例中出现真实密钥。

- [ ] **步骤 4：运行最终默认验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
```

预期：默认全量测试通过，真实 E2E 跳过；若用户另行启用真实 E2E，则单独记录实际 Provider、命令和结果，不记录密钥或响应正文。

- [ ] **步骤 5：记录证据并提交任务 6**

在 `AGENT_LOG.md` 和 `SPEC_PROCESS.md` 以中文记录每个任务的红灯/绿灯摘要、最终命令、跳过的真实 E2E 及任何环境限制。

```powershell
git add tests/integration/test_provider_e2e.py .env.example README.md AGENT_LOG.md SPEC_PROCESS.md
git commit -m "test: document multi-provider verification"
```

## 计划自检

- 规格覆盖：Task 1 实现双层配置、同名整体覆盖与 URL 规则；Task 2 实现钥匙串和开发回退隔离；Task 3 实现安全 HTTP/响应验证；Task 4 移除运行时 Mock 硬编码；Task 5 实现 CLI 显式选择与无回退；Task 6 实现可选真实 E2E 与中文过程记录。
- 占位检查：每个任务包含确切文件、接口、红灯测试、预期失败、最小实现、绿灯命令和提交命令；没有 `TBD`、`TODO`、未决接口或“类似任务”的引用。
- 类型一致性：`ProviderProfile` 由 Task 1 定义并由 Task 5 消费；`LLMProvider` 是 Task 4、Task 5 的共同注入接口；`build_provider` 在 Task 5 定义并由 Task 6 调用；所有非 Mock Provider 使用 `OpenAICompatibleProvider`。
