# Task 5 fix round 1 报告

## 范围

- 修改 `tests/integration/test_api_sse.py`
- 修改 `src/code_agent/api/app.py`
- 修改 `AGENT_LOG.md`
- 修改 `SPEC_PROCESS.md`

## 修复目标

- 将原先名含 stream、但实际只覆盖 `/api/tasks/{id}/events` JSON 回放的测试与真实 SSE 覆盖区分开。
- 新增真实打开 `/api/tasks/{id}/events/stream` 的端到端恢复测试。
- 证明服务重启隔离后不会自动发出执行完成事件，只有人工 `resume` 后才继续执行。
- 用至少两个可区分的 Mock 决策证明恢复是“从头重跑”，而不是直接完成。

## TDD 过程

### 先写失败测试

在 `tests/integration/test_api_sse.py` 中：

- 将旧的恢复测试更名为 `test_restart_recovery_events_endpoint_requires_manual_resume_and_preserves_order`，明确它只覆盖 `/events` JSON 回放。
- 新增 `test_restart_recovery_events_stream_replays_first_step_only_after_resume`，真实打开 `/events/stream`：
  - 重启隔离后先拉取 SSE，只允许看到 `recovery_required`
  - 旧 approval 决策必须返回 `409`
  - `resume` 后从最后 sequence 继续拉取 SSE
  - 必须看到 `recovery_started`、`feedback`、`task_completed`
  - 通过 `feedback.payload.changed_files == ["restart-marker.txt"]` 和文件内容 `from-recovery` 证明恢复执行包含首步 `write_file`

### 红灯验证

命令：

```powershell
$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -k events_stream_replays_first_step_only_after_resume -q
```

结果：失败。

真实缺口不是测试本身，而是实现问题：

- SSE generator 在重启隔离后的终态任务上回放完 `recovery_required` 后，仍调用 `TaskManager.wait_for_event()`
- 该任务没有活动 runtime
- 最终抛出 `KeyError`

这证明真实 `/events/stream` 覆盖确实缺失，且现实现无法正确处理“隔离后、恢复前”的 SSE 读取。

### 最小实现修复

只修改 `src/code_agent/api/app.py`：

- 将 `/events/stream` generator 的终态关闭条件从“终态且当前批次无事件”改为“终态即在回放完当前批次后直接关闭”

效果：

- 对已终态但无 runtime 的隔离任务，SSE 在回放完现有事件后直接结束
- 不再错误等待不存在的 runtime

### 绿灯验证

同一红灯命令重新运行后通过。

## 最终验证

### 目标测试

```powershell
$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_api_sse.py -q
```

结果：

- `15 passed, 35 warnings`

### 全量 Python

```powershell
$env:PYTHONPATH='src'; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest -q
```

结果：

- `159 passed, 1 skipped, 39 warnings`

### Ruff

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe check .
```

结果：

- `All checks passed!`

### Mypy

```powershell
C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe src
```

结果：

- `Success: no issues found in 33 source files`

### Web 测试

```powershell
web\npm.cmd test -- --run
```

结果：

- `2` 个文件通过
- `8` 个测试通过

### Web 构建

```powershell
web\npm.cmd run build
```

结果：

- 构建成功

## 修复结论

- 真实 SSE 恢复覆盖已补上。
- 测试现在能证明：重启隔离后不会自动执行完成，只有人工 `resume` 后才继续。
- 测试现在能证明：恢复执行包含可观察的首步行为，属于“从头重跑”而不是直接完成。
- 代码修复范围保持最小，只修正了终态隔离任务的 SSE 关闭条件。

## Concerns

- 仍保留既有 warnings：FastAPI `on_event`、Starlette TestClient/httpx 弃用提示，以及 Web 侧 Vite `configLoader: 'native'` 迁移预警；它们不影响本次任务结论。
- 本轮没有扩展到 checkpoint 续跑、真实 Provider E2E 或其他恢复语义，只覆盖 Task 5 所需的真实 SSE 与重跑证明。
