# 任务 2 报告：Textual 启动表单创建 Mock 任务

## TDD 记录

### RED

先在 `tests/integration/test_tui.py` 增加启动表单、创建任务、必填校验的集成测试，再执行：

```powershell
$env:PYTHONPATH = "$PWD\src"
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_tui.py -q
```

输出摘要：

```text
.FFF
TypeError: CodeAgentTui.__init__() got an unexpected keyword argument 'client'
3 failed, 1 passed
```

失败原因符合预期：应用尚未支持注入 API 客户端及表单行为。

### GREEN

实现最小表单与会话状态后执行同一命令：

```text
...... [100%]
6 passed in 1.63s
```

## 改动

- `src/code_agent/tui/app.py`
  - 支持注入 `TaskApiClient`；仅在提供 `api_base_url` 时构造客户端。
  - 初始化当前任务 ID、最后事件序号、任务详情和事件列表；构造与挂载阶段不请求网络。
- `src/code_agent/tui/screens.py`
  - 将 `StartScreen` 改为包含 workspace、goal、mode 与 mock decisions JSON 的表单。
  - 提交有效表单时透传创建负载，保存任务会话状态并进入 `RunScreen`。
  - workspace/goal、JSON 和 `TaskApiError` 均显示简短中文通知，校验失败不发送请求。
- `tests/integration/test_tui.py`
  - 覆盖控件存在、合法 Mock 创建负载、任务 ID 保存、切换运行屏幕、必填校验、JSON 错误和 API 错误。

## 验证

```powershell
$env:PYTHONPATH = "$PWD\src"
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m ruff check src/code_agent/tui/app.py src/code_agent/tui/screens.py tests/integration/test_tui.py
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m mypy src/code_agent/tui/app.py src/code_agent/tui/screens.py
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q
```

输出摘要：

```text
All checks passed!
Success: no issues found in 2 source files
62 passed, 15 warnings in 9.41s
```

15 条 warning 均为既有 FastAPI/Starlette 弃用警告，本任务没有引入新 warning。

另以注入会在调用时抛错的客户端构造应用，确认启动时仅初始化会话状态、不调用客户端：

```text
startup session state initialized without client request
```

## 自审

- 创建负载固定 `provider: "mock"`，并保留用户填写的 `mode` 和 JSON 数组形式的 `mock_decisions`。
- 成功响应的 `id` 经过类型检查后才写入状态和切屏。
- 所有失败通知为中文短句，未泄露客户端异常细节。
- `git diff --check` 无空白错误；Git 仅提示既有 CRLF 转换策略。

## 担忧

- `RunScreen` 目前仍为空壳；后续任务应利用本任务保留的会话状态实现轮询、事件展示与任务控制。
