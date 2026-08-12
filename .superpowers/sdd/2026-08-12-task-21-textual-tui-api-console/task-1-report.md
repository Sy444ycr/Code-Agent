# 任务 1 报告：可注入任务 API 客户端

## TDD 记录

### RED

命令：

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_tui_api.py -q
```

输出：

```text
ERROR tests/integration/test_tui_api.py
ModuleNotFoundError: No module named 'code_agent.tui.api'
1 error in 1.01s
```

失败原因符合预期：测试先于 `code_agent.tui.api` 模块实现，导入新客户端失败。

### GREEN

共享 Python 环境预先以可编辑安装方式指向主工作区 `C:\Users\sy444\Desktop\Agents\src`，不指向此 worktree。因此将当前 worktree 的 `src` 置于 `PYTHONPATH` 首位后执行验证：

```powershell
$env:PYTHONPATH = "$PWD\src"
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_tui_api.py -q
```

输出：

```text
... [100%]
3 passed in 0.54s
```

## 改动

- 新增 `src/code_agent/tui/api.py`：`TaskApiClient` 支持注入 `httpx.Client`，提供创建、查询、事件、取消、恢复与审批决定六个同步 API 方法；所有响应解码为字典。
- 新增 `TaskApiError`：HTTP 非 2xx、网络层异常及无效/非对象 JSON 均转换为不含服务端细节的界面安全错误。
- 新增 `tests/integration/test_tui_api.py`：使用 `httpx.MockTransport`，不发起真实网络请求；验证路由、方法、创建/审批负载、事件 `after` 游标和两类安全错误。

## 覆盖测试与验证

```powershell
$env:PYTHONPATH = "$PWD\src"
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m ruff check src/code_agent/tui/api.py tests/integration/test_tui_api.py
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m mypy src/code_agent/tui/api.py
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q
```

输出摘要：

```text
All checks passed!
Success: no issues found in 1 source file
57 passed, 15 warnings in 9.13s
```

15 条 warning 为既有 FastAPI `on_event` 与 Starlette TestClient 对 httpx 的弃用警告；本任务没有新增 warning。

## 自审结果

- 已逐项核对后端契约：`/api/tasks`、`/api/tasks/{task_id}`、`/events`、`/cancel`、`/resume`、`/api/approvals/{approval_id}/decision`。
- 已核对事件方法命名为 `get_events`，并且请求含 `after`。
- 已核对审批体始终带 `approved`、`scope`、`actor: "tui-user"`。
- 已核对错误消息不会包含 HTTP 响应正文或异常内部细节。
- `git diff --check` 对已跟踪内容无空白错误；新增文件以 no-index 检查也无空白错误（Git 仅提示仓库的 CRLF 转换策略）。
- 修改范围仅为任务指定的 API 模块、集成测试及本任务报告。
