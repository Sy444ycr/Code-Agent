# Task 22：多 OpenAI-compatible Provider 安全配置设计

## 1. 目标与范围

Task 22 将现有仅支持 `mock` 的 CLI Provider 选择扩展为多个命名的 OpenAI-compatible Provider 档案。用户可以在用户级或项目级 TOML 配置中声明多个档案，并在运行任务时通过 `--provider <名称>` 显式选择。

本阶段范围：

- 支持用户级和项目级 Provider 档案；项目级同名档案整体覆盖用户级档案。
- 支持 `mock` 与任意命名的 OpenAI-compatible 档案；不为 OpenAI、DeepSeek 等厂商分别引入 SDK 或独立适配器。
- 使用系统钥匙串保存每个 Provider 名称对应的密钥，提供 `auth set/status/clear <名称>`。
- 调用 OpenAI-compatible Chat Completions 接口，并将响应校验为 `AgentDecision`。
- 在真实 HTTP 请求前校验配置、密钥和 URL；默认测试不访问网络。

本阶段不包含多模型路由、Provider 插件发现、厂商原生协议、WebUI/TUI Provider 管理、多任务调度、远程 API 托管或自动选择/回退 Provider。

## 2. 配置模型与优先级

用户级配置路径为当前用户配置目录下的 `code-agent/config.toml`；项目级配置路径为 `<workspace>/.code-agent/config.toml`。两者都只保存非敏感配置。

配置格式如下：

```toml
[providers.openai]
base_url = "https://api.openai.com/v1"
model = "gpt-4.1"

[providers.deepseek]
base_url = "https://api.deepseek.com/v1"
model = "deepseek-chat"
```

每个档案解析为 `ProviderProfile(name, base_url, model)`。配置优先级为：命令行显式选择的名称 > 项目级档案 > 用户级档案 > 内置 `mock`。命令行不接受端点、模型或密钥字段，避免敏感值进入命令历史。

当用户级和项目级配置均存在同名档案时，项目级档案整体覆盖用户级档案；不按字段合并。不同名称的档案会共同出现在可选集合中。

## 3. 选择、鉴权与运行

`code-agent run <workspace> "<goal>" --provider <name>` 必须显式选择非 Mock Provider。`mock` 仍是默认值，并保持现有 `--mock-decisions` 语义。对于非 Mock Provider，`--mock-decisions` 不参与运行。

运行前，Provider 解析器按以下顺序失败：

1. 档案不存在：输出简短中文错误并退出。
2. `base_url` 或 `model` 缺失/无效：输出简短中文错误并退出。
3. 非本机地址不是 HTTPS：输出简短中文错误并退出；`localhost`、`127.0.0.1` 与 `::1` 可使用 HTTP 以支持本地兼容服务。
4. 钥匙串中不存在对应密钥：输出简短中文错误并退出。

所有失败均不自动改用其他档案或 Mock。`OpenAICompatibleProvider` 只接收已解析的档案与在运行时获取的密钥，并继续以 `POST {base_url}/chat/completions` 发送模型、消息和 `AgentDecision` JSON Schema。HTTP 响应、无效 JSON 或不符合 `AgentDecision` 的内容转换为可报告的 Provider 错误，不泄露授权头或密钥。

## 4. 凭据与安全边界

钥匙串服务名保持 `code-agent`，账户名等于 Provider 名称。因此 `auth set openai` 保存 `code-agent/openai`，`auth status openai` 仅显示已配置或缺失，`auth clear openai` 删除该条目。

项目配置、用户配置、SQLite、任务事件、报告、模型上下文、CLI 输出和日志均不得写入密钥。开发环境变量仅作为明确的本地回退，命名为 `CODE_AGENT_PROVIDER_<规范化名称>_API_KEY`；其值只在钥匙串缺失且用户显式允许开发回退时读取，并在文档中说明明文和进程可见风险。

Tool Executor 启动子进程前继续移除所有 Provider 密钥环境变量。Provider 请求的异常、调试信息和响应正文必须经过安全错误转换，确保已知密钥值不会进入用户可见通知或持久化记录。

## 5. 模块边界

### `config.py`

定义 `ProviderProfile` 和加载/合并/校验函数；负责 TOML 路径解析、用户级与项目级档案读取、同名整体覆盖及 URL 安全校验。不读取密钥，也不执行 HTTP 请求。

### `auth.py`

保持 `code-agent` 钥匙串服务，增加 Provider 名称规范化、密钥读取与开发回退的受控入口。状态接口不返回密钥内容。

### `core/llm.py`

保留 `MockLLMProvider`，将 `OpenAICompatibleProvider` 的 HTTP 调用与响应校验集中在此处。它不读取文件、不解析 CLI 参数，也不向子进程传递密钥。

### `application/task_service.py` 与运行时调用方

将 `TaskService` 与 API 后台运行路径从“内部固定创建 `MockLLMProvider`”改为接收已经构造的 `LLMProvider` 与 Provider 名称；创建任务时持久化该名称。Mock 场景加载只保留在 `mock` 分支，真实 Provider 不需要或读取 `mock_decisions`。这样 CLI、API、TUI 和 WebUI 都可复用同一 Provider 选择语义，而不会让配置逻辑泄入 LoopController。

### `cli.py`

在 `run` 命令中解析 Provider 名称和 workspace 配置，构造已校验的 Provider 并将其交给现有运行链路。`auth` 子命令继续操作命名 Provider 的钥匙串条目。用户可见错误均为简短中文。

## 6. 数据流

```text
CLI --provider name + workspace
  -> 配置加载（用户级 + 项目级整体覆盖）
  -> ProviderProfile 校验（名称、模型、URL/HTTPS）
  -> auth 读取 code-agent/name 密钥
  -> OpenAICompatibleProvider
  -> POST /chat/completions
  -> AgentDecision Pydantic 校验
  -> 既有 TaskService / LoopController
```

`mock` 直接使用现有 Mock 场景加载器，不进入配置、钥匙串或 HTTP 流程。

## 7. 测试与验收

默认单元/集成测试使用临时 TOML 文件、假的钥匙串后端和 `httpx.MockTransport`，不得依赖真实密钥或网络。至少覆盖：

1. 用户级与项目级不同名称合并、同名项目级整体覆盖，以及非法 TOML/字段的中文错误。
2. 不存在档案、缺失模型、非 HTTPS 远端、缺失密钥均在 HTTP 请求前失败，且不回退到 Mock 或其他档案。
3. `auth set/status/clear` 使用 Provider 名称作为钥匙串账户，状态输出不包含密钥。
4. OpenAI-compatible 请求路径、鉴权头、模型、JSON Schema 与 `AgentDecision` 响应校验；错误消息不含密钥或响应敏感内容。
5. 子进程环境清理所有 Provider 开发回退变量。
6. `mock` CLI 回归保持可运行。

真实 Provider 端到端测试仅在 `CODE_AGENT_RUN_PROVIDER_E2E=1` 时启用，并要求调用者已在钥匙串配置测试档案密钥。该测试不进入默认 CI，不打印请求/响应敏感内容，并以最小只读任务验证一次结构化决策。

## 8. 文件边界与自检

预计修改 `src/code_agent/config.py`、`auth.py`、`core/llm.py`、`application/task_service.py`、`application/task_manager.py`、`cli.py` 及对应测试、`README.md`、`AGENT_LOG.md`、`SPEC_PROCESS.md`；不修改 Task 19 API 的 HTTP/SSE 契约、WebUI、TUI 或数据库任务协议。

本设计没有未决接口或占位项：配置优先级、同名覆盖、凭据键、URL 规则、显式选择与真实 E2E 开关均已确定。实现计划必须继续遵守严格 TDD、默认离线测试、中文过程记录和每个任务的独立评审门。
