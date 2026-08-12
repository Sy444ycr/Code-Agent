# Task 21 最终审阅修复报告

## 状态与范围

已集中修复最终审阅指出的两项阻断问题。生产代码仅修改：

- `src/code_agent/tui/app.py`
- `src/code_agent/tui/screens.py`

回归测试仅修改 `tests/integration/test_tui.py`。未修改后端 API、WebUI、既有过程文档或 `api.py`。

## 修复内容

### 1. 默认 API 客户端

`CodeAgentTui()` 现在默认构造指向 `http://127.0.0.1:8000` 的 `TaskApiClient`。显式传入的 `client` 始终优先；显式 `api_base_url` 仍可覆盖默认地址。构造与挂载阶段仅创建客户端和启动页，不发送 HTTP 请求。

回归测试在构造前替换 `httpx.Client.send` 为一旦调用即失败的函数，并验证：

- 无参应用具有 `TaskApiClient`；
- 应用公开的 base URL 为 `http://127.0.0.1:8000`；
- 整个 `run_test` 启动及挂载阶段没有 HTTP 请求。

### 2. 终态详情不再依赖事件请求成功

`RunScreen._refresh_once` 现在分别处理详情与事件错误：

- `get_task` 失败：通知“刷新任务失败”并结束本周期；
- `get_task` 成功：立即提交 `app.task_detail`；
- `get_events` 失败：通知“刷新事件失败”，保留现有游标和事件，继续渲染详情并执行审批/终态路由；
- 终态仍进入 `ResultScreen`，离开 `RunScreen` 后计时器暂停且活动 worker 被取消。

回归测试使用 fake client 返回 `succeeded` 详情、随后让 `get_events` 抛出 `TaskApiError`，验证详情被提交、结果与既有事件可见、游标和事件不变、显示中文通知，并跨越一个 500ms 计时周期确认详情和事件读取次数均不再增长。

## TDD 记录

### RED

命令（共享虚拟环境，当前 worktree 的 `src` 置于 `PYTHONPATH` 首位）：

```powershell
$env:PYTHONPATH='C:\Users\sy444\Desktop\Agents\.worktrees\task-21-textual-api-console\src'
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_tui.py -q -k "default_tui_has_local_api_client_without_requesting_during_startup or terminal_detail_routes_to_result_when_event_refresh_fails"
```

结果：`2 failed, 22 deselected`。

- 默认客户端测试失败：`app.client` 实际为 `None`；
- 终态事件失败测试失败：当前屏幕仍为 `RunScreen`，未进入 `ResultScreen`。

两项均因待修复生产行为缺失而失败，不是测试语法、环境或 fixture 错误。

计划中的 `.venv\Scripts\python.exe` 相对路径在 worktree 内不存在；实际使用主仓库共享虚拟环境的绝对路径，并显式设置 `PYTHONPATH`，确保导入当前 worktree 源码。

### GREEN

同一 focused 命令结果：

```text
2 passed, 22 deselected in 1.35s
```

完整 TUI 测试：

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_tui.py -q
```

结果：`24 passed in 5.17s`。

## 最终验证

所有命令均在 Task 21 worktree 根目录执行，并设置当前 worktree `src` 为 `PYTHONPATH`。

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q
```

结果：`80 passed, 15 warnings in 11.66s`。15 条警告为既有 FastAPI `on_event` 和 Starlette TestClient/httpx 弃用警告，退出码为 0。

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe check .
```

结果：`All checks passed!`

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe src
```

结果：`Success: no issues found in 30 source files`

```powershell
git diff --check
```

结果：退出码 0；仅显示仓库既有的 LF/CRLF 转换提示，无空白错误。

## 已知问题

无本次修复引入或遗留的已知功能问题。全量 pytest 的 15 条既有弃用警告未在本次 TUI 限定范围内处理。
