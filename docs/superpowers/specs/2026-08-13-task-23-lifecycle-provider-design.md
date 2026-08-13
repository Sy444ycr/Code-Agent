# Task 23：生命周期契约与全端 Provider 贯通设计

## 1. 目标与范围

Task 23 用于补齐当前规格缺口，不重做已完成的核心循环、治理、记忆、SubAgent、基础 TUI 或基础 WebUI。范围拆分为四个可独立验收的子项目，并按顺序实施：

1. CLI/API 生命周期契约补全。
2. Provider 贯通 API、TUI 和 WebUI。
3. `code-agent web`、静态资源托管与干净环境分发。
4. 规格级演示任务与最终验收证据。

本设计不引入云端多用户、远程任务队列、Provider 插件发现、在线代码编辑器或自动 PR/部署。

## 2. 当前状态与设计原则

现有 FastAPI、TaskManager、TaskService、SQLite 任务模型、SSE 事件流、Textual TUI 和 React WebUI 已共享任务与审批模型。当前缺口主要是：

- API 创建任务仍在边界固定构造 `MockLLMProvider`。
- CLI 仅实现运行与认证相关命令，生命周期命令和 diff/report 查询不完整。
- TUI/WebUI 创建任务的 Provider 类型被限定为 `mock`。
- `code-agent web`、静态资源托管和干净环境分发验收尚未形成完整闭环。
- 规格要求的四类可重复演示和最终验收证据尚未统一记录。

设计原则：复用现有状态机和事件模型；Provider 只在边界装配；默认测试离线；敏感值不进入客户端、任务、事件、报告、SQLite 或模型上下文；每个子项目采用严格 TDD 和独立评审门。

## 3. 统一 Provider 装配边界

新增 `src/code_agent/application/providers.py`，定义安全的 Provider 工厂：

```python
def build_provider(
    name: str,
    workspace: Path,
    *,
    mock_decisions: list[AgentDecision] | None = None,
    allow_development_fallback: bool = False,
) -> tuple[LLMProvider, str]: ...
```

行为规则：

- `name == "mock"` 时只接受显式的 `mock_decisions`，不得从配置或网络构造 Provider。
- 非 Mock 名称统一经过 Provider 名称规范化，读取用户级/项目级配置，校验 URL，再从 `code-agent` keyring 读取对应账户密钥。
- 默认不允许开发环境变量回退；只有明确传入 `allow_development_fallback=True` 才可启用。
- 工厂只抛出固定、简短、中文的 `ProviderFactoryError`；底层 keyring、httpx、配置异常只作为异常原因保存，不进入用户输出或持久化报告。
- 工厂不接受端点、模型或密钥作为客户端请求字段；这些值只能来自安全配置与钥匙串。

CLI、FastAPI API、TUI API client 和 WebUI 均消费同一工厂语义。API 只接收 Provider 名称和 Mock 决策，不接收 `base_url`、`model` 或 API key。

## 4. 子项目一：CLI/API 生命周期契约

### API

保留现有 REST/SSE 路由和事件格式，新增或补齐：

- `GET /api/tasks/{id}/diff`：返回当前 workspace 的受控 Git diff。
- `GET /api/tasks/{id}/report`：返回任务最终状态、报告、验证证据、反馈和修改文件。
- 创建任务时通过 ProviderFactory 装配 Provider，再调用现有 `TaskManager.submit(task, loop_spec, provider)`。
- Provider、workspace 和任务错误转换为固定中文 HTTP 错误；不返回底层异常文本。
- diff/report 只读取任务已记录的 workspace 和结果，不改变 SQLite schema。

### CLI

在不复制 TaskManager 状态机的前提下补齐：

- `code-agent status <task-id>`
- `code-agent approve <approval-id>`
- `code-agent reject <approval-id>`
- `code-agent resume <task-id>`
- `code-agent attach <url>`
- `code-agent web`

命令通过本地 TaskService 或 API client 调用已有生命周期接口；结构化输出使用稳定 JSON 字段，交互输出使用简短中文。`attach` 只连接用户提供的本地/已授权服务地址，不自动扩大 workspace 或 Provider 权限。

## 5. 子项目二：Provider 贯通 API、TUI、WebUI

### API 数据流

```text
POST /api/tasks {provider, mock_decisions, ...}
  -> ProviderFactory
  -> TaskManager.submit(..., provider)
  -> LoopController
  -> SQLite task.provider + ordered events
```

非 Mock 请求缺少档案、配置无效、URL 不安全或 keyring 缺失时，在 HTTP 请求前失败，不回退到 Mock 或其他 Provider。

### TUI/WebUI

- 创建任务表单将 Provider 从字面量 `mock` 扩展为用户输入的 Provider 名称。
- Mock 场景字段只在 Provider 为 `mock` 时可用；真实 Provider 不发送 Mock 决策、端点、模型或密钥字段。
- 任务详情继续展示非敏感 Provider 名称、状态、审批和事件；不展示配置内容或密钥。
- 审批、取消、恢复和事件回放继续复用同一 API、事件序号和状态机。
- 客户端断线后按游标恢复，不因重连清零已消费的事件。

默认测试使用 fake keyring、MockLLMProvider、httpx MockTransport、FastAPI TestClient、Textual fake client 和浏览器请求拦截，不访问真实网络。

## 6. 子项目三：Web 启动与干净环境分发

- `code-agent web` 启动本地 FastAPI，默认监听 `127.0.0.1:8000`。
- 若包内存在已构建 WebUI 静态资源，FastAPI 提供静态文件和前端入口；API 路径继续由后端处理。
- `pyproject.toml` 明确包数据和 Web 构建产物的包含规则；构建流程先运行 WebUI 类型检查/测试/构建，再执行 Python 包构建。
- 干净环境验收使用隔离虚拟环境或 `pipx`，验证安装后的 `code-agent`、`code-agent web`、默认 Mock 运行和 `--help`。
- 该子项目不把真实密钥写入镜像、包、日志或测试夹具；CI 默认不启用真实 Provider E2E。

## 7. 子项目四：规格级演示与最终验收

提供四个可重复、默认离线的演示场景：

1. 功能实现：Mock 决策驱动文件修改并通过验收命令。
2. Bug 修复：首次验证失败后，反馈改变下一轮动作并最终通过。
3. 测试补充：任务新增测试并以确定性测试命令验证。
4. 小型重构：保持行为不变，通过回归测试和 diff 证明结果。

最终验收记录：

- Python pytest、Ruff、Mypy、包构建和安装后 CLI 验证。
- WebUI Vitest、TypeScript/Vite build、Playwright（可用浏览器通道）结果。
- CLI/API/TUI/WebUI 共享任务、审批、取消、恢复和事件游标的集成证据。
- Provider 默认离线路径、真实 E2E 开关状态和环境限制。
- 所有失败、跳过和弃用警告如实记录，不把环境限制表述为通过。

## 8. 错误处理与安全边界

- ProviderFactory、API、CLI、TUI 和 WebUI 只显示固定安全错误；不得拼接密钥、Authorization、响应正文、底层异常或配置敏感字段。
- Task、Event、Approval、Report、SQLite 和模型上下文只保存 Provider 名称及非敏感验证证据。
- API 与客户端拒绝端点、模型和密钥字段，避免命令历史、浏览器状态和任务事件泄露凭据。
- 所有 Provider 异常在边界转换为固定安全错误；TaskManager 的失败报告也使用固定安全文本。
- 现有 workspace 边界、Policy Engine、审批状态机和强制拒绝规则保持不变。

## 9. 验收门槛

每个子项目必须先有失败测试，再有最小实现、绿灯验证、Ruff/Mypy 或前端等价静态检查，并通过规格合规和代码质量两阶段评审。所有子项目完成后，必须在最终合并前重新运行完整默认验证；真实 Provider E2E 只有在显式设置环境开关和安全凭据后才允许单独运行。

## 10. 明确不在本设计内

- Provider 插件发现、厂商原生 SDK、多模型路由。
- WebUI/TUI 在线代码编辑器。
- 云端账号、远程队列、分布式 worker、多用户权限。
- 自动提交、推送、创建 PR、部署或强制 Git 操作。
- 重型向量 RAG、LSP/AST 深度集成和递归 SubAgent。
