# Task 3 实施报告

## 范围

- 修改 `src/code_agent/api/app.py`
- 修改 `src/code_agent/api/schemas.py`
- 修改 `tests/integration/test_api_sse.py`

## TDD 过程

### 先写失败测试

在 `tests/integration/test_api_sse.py` 新增并先运行失败测试，覆盖以下行为：

- 任务详情返回 `recovery_required`、`recovery_reason`、`resumable`
- 仅 `status=needs_review` 且 `recovery.required=true` 的任务可恢复
- 创建 mock 任务时持久化 `mock_decisions`
- `POST /api/tasks/{task_id}/resume` 会在 workspace 缺失时返回 `409`，且不写入 `recovery_started`
- 重启隔离后的 mock 任务可通过 `/resume` 重建 provider 并恢复执行

首次运行指定 pytest 后得到预期红灯，失败点为：

- 详情接口缺少 recovery 摘要字段
- 未持久化 `mock_decisions`
- `/resume` 仍走旧的 `TaskManager.resume()` 路径

### 最小实现

1. 在 API schema 中补充任务摘要/详情响应模型，加入：
   - `recovery_required: bool`
   - `recovery_reason: str | null`
   - `resumable: bool`
2. 在创建任务时把 mock 场景决策写入 `TaskRecovery.mock_decisions`
3. 同时把 mock 决策写入 checkpoint，作为“服务重启隔离覆盖 recovery 时”的恢复兜底
4. 在任务详情接口中根据 `TaskRecovery` 计算恢复摘要，并严格限制 `resumable`
5. 把 `/api/tasks/{task_id}/resume` 改为：
   - 仅接受 `needs_review` 且 `recovery.required=true`
   - 先检查 workspace 目录是否存在，不存在则返回 `409`
   - 通过已有 `build_provider` 重建 provider
   - 调用 `TaskManager.recover()` 从头恢复

### 测试调整

- 将“mock 决策已持久化”的断言收紧为 `AgentDecision` 语义等价，而非比较原始最小 JSON
- 修正“重启后恢复 mock provider”测试，保留已持久化的 `mock_decisions`，只把 recovery 切换为 `required=true`

## 验证结果

使用临时虚拟环境执行验证（未写入仓库）：

```text
python -m pytest tests/integration/test_api_sse.py tests/integration/test_task_manager.py -q
26 passed, 27 warnings
```

```text
ruff check src/code_agent/api
All checks passed!
```

```text
mypy src
Success: no issues found in 33 source files
```

## 结果总结

- API 详情新增恢复摘要字段
- `/resume` 现在只对“服务重启隔离导致的 needs_review”任务开放
- workspace 缺失时会安全拒绝恢复，并保持任务状态不变
- mock provider 的恢复输入已持久化，恢复时可重新构造 provider

## Concerns

- 当前验证环境使用的是仓库外临时 Python 3.13 虚拟环境；项目声明 `requires-python >=3.12`，本机未发现 3.12 解释器，但本次测试、ruff、mypy 均已通过
- 指定 pytest 仍有 27 条现存 warning，主要来自 FastAPI `on_event` 和 Starlette `TestClient` 的弃用提示；本次未在 brief 范围内处理
