# 任务 3 报告：运行观察、审批、取消/恢复与结果界面

## TDD 记录

### RED

先在 `tests/integration/test_tui.py` 增加 Textual 集成测试，覆盖：首次 `after=0`
轮询、递增 sequence 与重复去重、三种审批快捷键、取消/恢复及立即刷新、API 错误后的
界面和游标保留、六种终态路由、结果报告和缺失报告回退文案。测试仅使用可注入的 fake
client，不发起真实网络请求。

命令：

```powershell
$env:PYTHONPATH = "src"
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_tui.py -q
```

输出摘要：

```text
16 failed, 6 passed in 3.80s
```

失败原因符合预期：空的 `RunScreen`、`ApprovalScreen`、`ResultScreen` 尚无
`refresh_task`、快捷键处理、轮询、审批与终态渲染行为；原有 6 项测试继续通过。

### GREEN

完成最小实现后重跑同一命令：

```text
22 passed in 3.89s
```

收紧 Textual `Screen` 构造器类型后再次验证：

```text
22 passed in 3.82s
```

## 改动

- `src/code_agent/tui/app.py`
  - 集中定义六种终态：`succeeded`、`needs_review`、`blocked`、`failed`、
    `budget_exhausted`、`cancelled`。
- `src/code_agent/tui/screens.py`
  - `RunScreen` 使用 500ms Textual timer 和 worker，详情请求完成后按当前游标请求事件；
    `_refreshing` 防止并发轮询，离开屏幕时暂停 timer 并取消 worker。
  - 仅追加 sequence 严格递增的事件；API 错误只通知，不清空游标、详情或已有事件。
  - 显示任务状态、目标、最近十条事件和取消快捷键；取消成功后立即刷新。
  - 检测 `waiting_approval` 和首个 `pending_approvals` 项后进入审批屏；`y`、`a`、
    `n` 分别提交允许一次、任务范围允许和拒绝，提交期间屏蔽重复输入，成功后回到运行屏。
  - 六种终态均停止运行屏轮询并进入结果屏；结果屏显示状态、任务 ID、结果报告和最近
    事件摘要，缺失报告时显示“服务端未提供结果报告”。`cancelled` 状态可按 `r` 恢复，
    成功后立即回到运行屏刷新。
- `tests/integration/test_tui.py`
  - 新增 16 个测试场景（含参数化用例），验证上述可观察行为及 fake client 边界参数。

## 验证

使用当前 worktree 的 `src` 作为 `PYTHONPATH`，并固定使用指定虚拟环境 Python：

```powershell
$env:PYTHONPATH = "src"
$python = "C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe"
& $python -m pytest tests/integration/test_tui.py -q
& $python -m pytest -q
& $python -m ruff check .
& $python -m mypy src/code_agent
```

最终输出：

```text
22 passed in 3.98s
78 passed, 15 warnings in 10.35s
All checks passed!
Success: no issues found in 30 source files
```

裸 `mypy` 在共享虚拟环境中会优先识别指向主工作区的 editable 安装，并因该已安装包缺少
`py.typed` 而退出；显式传入当前 worktree 的 `src/code_agent` 后，全包 30 个源文件通过。
全量 pytest 的既有 FastAPI/Starlette 弃用 warning 与本任务无关，本任务未新增 warning。

## 自审

- 逐项对照任务简报：详情先于事件、首次 `after=0`、游标去重与失败保留、500ms 单飞、
  离屏停止、三种审批、取消/恢复立即刷新、六种终态和回退文案均有实现及测试覆盖。
- API 客户端仍由外部注入；测试没有启动服务或访问真实网络。
- 审查 Textual 生命周期：运行屏 suspend/unmount 时停止 timer 并取消活动 worker；审批/结果
  屏 pop 后运行屏 resume，恢复 timer 并立即刷新。
- 审查错误路径：轮询、取消和恢复失败均保留当前屏幕与游标；审批失败解除提交锁，允许重试。
- 修改范围仅为任务指定的三个源码/测试文件和本报告；未修改 API、WebUI 或 docs。
- `git diff --check` 无空白错误；Git 仅提示仓库既有 CRLF 转换策略。

## 问题

无阻塞问题。全量测试会报告既有 FastAPI `on_event` 与 Starlette TestClient/httpx 弃用警告。

## 审阅修复：取消与在途轮询竞态

审阅指出：取消成功后直接调用 `refresh_task()`，如果定时轮询仍在执行，旧实现会因
`_refreshing` 为真而立即返回，导致“取消后立即刷新”请求被丢弃，只能等待下一次 500ms
定时周期。

### RED

新增阻塞 fake client：首次 `get_task` 捕获取消前的 `running` 快照并阻塞，测试在该请求
在途时触发取消，取消成功后释放首次读取。旧实现没有补发详情请求，因此稳定失败：

```powershell
$env:PYTHONPATH = "src"
C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_tui.py::test_cancel_during_slow_poll_queues_single_refresh_before_next_interval -q
```

```text
FAILED: assert client.task_reads >= 2
1 failed in 1.35s
```

### GREEN

将忙碌期间的刷新请求合并为一个 `_refresh_requested` 标记；当前刷新结束后，若运行屏仍为
当前屏幕，则在同一 worker 内再执行一次详情→事件刷新。该机制不会并发启动第二个轮询，
同时保证取消后的显式刷新不被丢弃。

```text
1 passed in 1.15s
23 passed in 4.52s
All checks passed!
Success: no issues found in 1 source file
```

同一回归测试还断言：慢请求期间 `get_task` 最大并发数为 1；补偿刷新取得 `cancelled`
详情并进入 ResultScreen 后，再跨过一个 500ms 周期也不会继续读取。

提交前完整验证：

```text
23 passed in 4.53s
79 passed, 15 warnings in 10.85s
All checks passed!
Success: no issues found in 30 source files
```
