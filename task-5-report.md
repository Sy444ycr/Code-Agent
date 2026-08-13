# Task 5 报告：端到端验收与中文过程记录

## 范围

- 修改文件：
  - `tests/integration/test_api_sse.py`
  - `task-5-report.md`
  - `AGENT_LOG.md`
  - `SPEC_PROCESS.md`
- 未扩展实现范围到 brief 之外的源码文件。

## TDD 记录

### RED

- 先新增端到端验收测试 `test_restart_recovery_stream_requires_manual_resume_and_preserves_order`。
- 首次执行命令：

```powershell
$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_restart_recovery_stream_requires_manual_resume_and_preserves_order -q
```

- 首次失败结果：
  - 第一次失败是测试自身缺少 `Approval` 导入，报 `NameError: name 'Approval' is not defined`。
  - 修正导入后再次执行，测试按预期进入真实行为验证；随后通过。

### GREEN

- 在 `tests/integration/test_api_sse.py` 中保留新的端到端验收测试，覆盖：
  - 同一 `state.db` 中存在旧的运行未终态/待审批任务；
  - 新 app 启动后自动隔离为 `needs_review`；
  - 详情字段中保留旧 `goal`，同时 `loop_spec.goal` 为持久化规格；
  - 旧 `pending_approval` 不会被自动执行；
  - `resume` 后从头重新运行，并最终进入 `succeeded`；
  - 事件序号严格递增；
  - 事件序列包含 `recovery_required`、`recovery_started`、`task_completed`。

- 目标测试命令：

```powershell
$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py::test_restart_recovery_stream_requires_manual_resume_and_preserves_order -q
```

- 结果：`1 passed, 5 warnings`。

## 针对性测试

- 命令：

```powershell
$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests\integration\test_api_sse.py -q
```

- 结果：`14 passed, 31 warnings`。

## 最终验证

按 brief 要求执行以下命令：

### 1. Python 全量测试

```powershell
$env:PYTHONPATH="src"; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q
```

- 结果：`158 passed, 1 skipped, 35 warnings in 136.28s`
- warnings 构成：
  - `fastapi.testclient` / `starlette.testclient` 的既有弃用警告；
  - FastAPI `on_event` 的既有弃用警告；
  - 均为仓库现存警告，本任务未新增新的 warning 类型。

### 2. Ruff

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe check .
```

- 结果：`All checks passed!`

### 3. Mypy

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe src
```

- 结果：`Success: no issues found in 33 source files`

### 4. Web 测试

```powershell
npm.cmd test -- --run
```

- 结果：`2 passed (files), 8 passed (tests)`
- 附带既有 Vite `configLoader: 'native'` 迁移预告，不影响退出状态。

### 5. Web build

```powershell
npm.cmd run build
```

- 结果：构建通过，`✓ built in 307ms`
- 附带既有 Vite `configLoader: 'native'` 迁移预告，不影响退出状态。

## 恢复边界记录

- 本次验收覆盖的是：
  - 服务重启后对未终态任务的隔离；
  - 人工确认后从头重新执行；
  - 旧审批不自动执行；
  - 恢复相关事件顺序与终态完成。

- 本次未扩展覆盖的边界：
  - 不自动重放旧审批动作；
  - 不验证 checkpoint 恢复执行位置，本任务仅验证“从头重新执行”语义；
  - 不触达真实 Provider E2E，仍只使用 Mock provider；
  - 不在本任务内修复“隔离后、恢复前对无活动 runtime 直接拉取 SSE stream 会失败”的现有行为，该现象不属于本 brief 允许的源码修改范围，故仅作为 concern 保留。
