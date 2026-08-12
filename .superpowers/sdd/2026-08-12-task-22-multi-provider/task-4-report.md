# 任务 4 执行报告：Provider 注入运行链路

## 改动范围

- `TaskService.run` 现在接收 `LLMProvider` 与 `provider_name`，并将名称保存到 `Task.provider`。
- `TaskManager.submit` 接收 `LLMProvider`，仅将其保存到内存运行时对象；后台执行直接使用该 Provider。
- API 在 Mock 请求解析边界创建 `MockLLMProvider(request.mock_decisions)` 后提交给管理器。
- CLI Mock 调用方改为传入 `MockLLMProvider(decisions)` 与名称 `"mock"`，保持现有命令契约。
- 未修改 HTTP 路由、事件类型、审批状态机、SQLite schema、WebUI 或 TUI 契约。

## TDD 证据

### RED

先在 `tests/integration/test_task_service.py` 新增
`test_task_service_uses_injected_provider_and_persists_name`，并在
`tests/integration/test_task_manager.py` 新增 `test_submit_uses_injected_provider`。

首次命令（工作树没有独立 `.venv`，故该命令未启动解释器）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_task_service.py tests/integration/test_task_manager.py -q
```

实际 RED 命令（使用父工作区共享虚拟环境）：

```powershell
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_service.py tests/integration/test_task_manager.py -q
```

结果：`2 failed, 4 passed`。

- 服务测试报 `TypeError: TaskService.run() takes 6 positional arguments but 7 were given`，证明旧签名仍接收 decisions。
- 管理器测试超时，证明旧链路将传入 Provider 当作 decisions，并在运行时固定创建 `MockLLMProvider`。

实现后，首次在当前 worktree 运行测试发现共享 editable 安装指向主工作区；通过设置
`PYTHONPATH=$PWD\src` 确认加载的是当前 worktree 的模块。该次验证只剩一项测试失败：
`SQLiteStore` 没有 `list_tasks()`。测试改为通过运行事件的 task id 使用真实存储 API
`get_task()` 验证持久化名称，没有新增不相关的存储接口。

完整套件还发现两项既有 CLI 集成测试因旧调用签名失败：
`TaskService.run() missing 1 required positional argument: 'acceptance_checks'`。在 CLI 边界显式构造
`MockLLMProvider(decisions)` 并传入 `"mock"` 后复测。

### GREEN

聚焦集成测试：

```powershell
$env:PYTHONPATH = "$PWD\src"
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_service.py tests/integration/test_task_manager.py tests/integration/test_api_sse.py -q
```

结果：`13 passed, 15 warnings in 2.82s`。15 条 warnings 均为 FastAPI/Starlette 的已存在弃用警告。

CLI 回归测试：

```powershell
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_cli_runtime.py -q
```

结果：`2 passed in 1.11s`。

静态检查：

```powershell
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe' check src/code_agent/application src/code_agent/cli.py tests/integration/test_task_service.py tests/integration/test_task_manager.py
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe' src/code_agent/application src/code_agent/cli.py
```

第一次 Ruff 检查发现新增 CLI 调用行 `E501`（101 字符）；仅换行格式化后，最终验证如下。

最终聚焦验证：

```powershell
$env:PYTHONPATH = "$PWD\src"
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_service.py tests/integration/test_task_manager.py tests/integration/test_api_sse.py tests/integration/test_cli_runtime.py -q
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe' check src/code_agent/application src/code_agent/cli.py tests/integration/test_task_service.py tests/integration/test_task_manager.py
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe' src/code_agent/application src/code_agent/cli.py
```

结果：`15 passed, 15 warnings in 3.36s`、`All checks passed!`、`Success: no issues found in 5 source files`。

最终全套验证：

```powershell
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest -q
```

结果：`91 passed, 15 warnings in 12.90s`。warnings 均为 FastAPI/Starlette 的既有弃用告警，未引入测试失败。

## 结论

Provider 的构造职责已留在 API/CLI 调用边界，服务与后台管理器均不再硬编码创建
`MockLLMProvider`。Provider 实例仅保存在 `TaskManager` 的内存 `_Runtime` 中，持久化的
`Task.provider` 只保存 provider 名称。
