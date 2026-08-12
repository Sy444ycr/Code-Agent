# Task 22 最终修复报告

## 修复范围

- `config.py`：Provider 表名统一复用凭据与 CLI 的名称规范化规则；同一配置文件内规范化后重名立即拒绝；用户级与项目级档案以规范化名称执行项目级整体覆盖；解析入口也规范化显式名称。
- `auth.py`：开发回退环境变量使用可逆分隔符编码：下划线编码为 `_U`，连字符编码为 `_H`；不含分隔符的 `openai` 仍保持 `CODE_AGENT_PROVIDER_OPENAI_API_KEY`，而 `foo_bar` 与 `foo-bar` 不再共享凭据。
- `config.py` URL 安全校验：在 Provider 解析、HTTP 请求前拒绝 userinfo、query、fragment、不可解析或越界端口；错误均为固定的中文 `ProviderConfigurationError`，不回显 URL 或其中的敏感值。
- `llm.py`：`api_key_getter`、HTTP client、响应解码与结构化解析边界的任意异常统一转为固定 `ProviderRequestError("Provider 请求失败。")`；已有 `ProviderRequestError` 原样继续抛出，避免不一致的二次包装。
- `task_manager.py`：Provider 错误固定报告为 `Provider 请求失败。`，其他意外错误固定报告为 `任务执行失败。`；不再将 `str(exc)` 写入报告、SQLite、事件或 SSE 的事件来源。

## 严格 TDD 证据

### RED

先只修改四个测试文件，然后运行：

```powershell
$env:PYTHONPATH='src'
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q tests/unit/test_config.py tests/unit/test_auth.py tests/unit/test_llm.py tests/integration/test_task_manager.py
```

结果：`12 failed, 15 passed in 2.12s`。失败与目标行为一一对应：

- 档案名未规范化、规范化重名未拒绝、非法表名未拒绝：3 项失败；
- userinfo、query、fragment、不可解析端口未拒绝：4 项失败；
- `foo_bar` 与 `foo-bar` 读取同一环境变量：1 项失败；
- `api_key_getter` 与 client 的任意 `RuntimeError` 原样逃逸：2 项失败；
- TaskManager 将 Provider/意外异常中的 sentinel 直接写入报告：2 项失败。

说明：首次尝试使用裸 `pytest` 时，PowerShell 报告命令不存在，测试未执行，因此未将其作为 RED 证据；随后使用仓库共享虚拟环境与 `PYTHONPATH=src` 得到以上有效 RED。

### GREEN

完成最小生产实现后重新运行同一聚焦命令，结果：`27 passed in 1.54s`。

安全回归测试使用 `sentinel-secret-provider`、`sentinel-secret-unexpected` 与 `sentinel-secret-boundary`，验证异常文本不出现在固定错误、任务完成事件 JSON 或 SQLite 文件字节中。任务完成事件是 SSE 的持久化来源，因此固定报告同时覆盖事件回放与 SSE 输出路径。

## 最终验证

- 唯一一次完整默认测试套件：`python.exe -m pytest -q` → `114 passed, 1 skipped, 15 warnings in 12.47s`。跳过项是真实 Provider E2E 的显式开关保护；15 条均为既有 FastAPI/Starlette 弃用警告。
- 全仓 Ruff：`ruff.exe check .` → `All checks passed!`。
- 全部源文件 Mypy：`mypy.exe src` → `Success: no issues found in 30 source files`。
- `git diff --check`：通过，无空白错误。

## 安全与兼容性说明

- 默认离线行为未改变，未启用真实 Provider E2E，未读取真实 keyring，未发起真实网络请求。
- `CODE_AGENT_PROVIDER_OPENAI_API_KEY` 兼容形式保留。
- 含 `_` 或 `-` 的开发回退环境变量名称现在采用新编码；这是消除别名、避免错误 Provider 读取密钥所必需的安全变化。
- 未修改 HTTP/SSE 协议、WebUI、TUI、数据库结构或 Mock 默认选择逻辑。
