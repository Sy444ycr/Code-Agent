# Task 2 报告

## 任务概述

本任务实现了 TaskManager 在服务启动时对中断任务的隔离，以及用户确认后的“从头重新执行”恢复能力。修改范围严格限制在 brief 允许的文件内：

- `src/code_agent/application/task_manager.py`
- `tests/integration/test_task_manager.py`

`src/code_agent/storage.py` 本任务未做代码改动，因为现有 `isolate_interrupted_tasks()`、`get_recovery()`、`get_spec()` 已满足 Task 2 所需接口。

## TDD 过程

### RED：先补失败测试

先在 `tests/integration/test_task_manager.py` 新增并运行以下覆盖：

1. `TaskManager.__init__()` 启动即调用 `store.isolate_interrupted_tasks()`，把 `RUNNING` 任务隔离为 `NEEDS_REVIEW`，并写入 `recovery_required` 事件。
2. `recover(task_id, provider)`：
   - 仅接受同时满足 `TaskStatus.NEEDS_REVIEW`、`TaskRecovery.required == True`、存在持久化 `LoopSpec` 的任务；
   - 将状态切换为 `RUNNING`；
   - 清除 recovery 的 `required`；
   - 追加 `recovery_started` 事件，payload 为 `{"reason": "用户确认从头重新执行"}`；
   - 复用持久化 `LoopSpec` 从头运行，并最终成功完成。
3. 不可恢复任务抛出：
   - `ValueError("not restart-recoverable")`
   - `ValueError("not awaiting recovery")`
   且不创建 runtime、不写入 `recovery_started`。
4. 没有 runtime 的旧 approval 决策返回冲突，不创建 runtime，也不修改 approval 状态。

首次失败验证命令：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py -q
```

首次 RED 结果：

- `test_manager_startup_isolates_interrupted_tasks` 失败：`TaskManager` 初始化后任务仍是 `running`
- 多个 `recover` 测试失败：`TaskManager` 缺少 `recover`
- `test_deciding_orphaned_approval_conflicts_without_creating_runtime` 失败：当前抛出 `KeyError`，不是冲突

说明新增测试确实抓到了缺失行为。

### GREEN：最小实现

在 `src/code_agent/application/task_manager.py` 中完成以下最小实现：

1. `__init__()` 中调用 `self.store.isolate_interrupted_tasks()`
2. 新增 `recover(task_id, provider) -> Task`
3. 抽取 `_start_runtime(task, loop_spec, provider)`，让 `submit()` 与 `recover()` 共用
4. `decide_approval()` 在 approval 存在但 runtime 缺失时改抛 `ValueError("approval runtime conflict")`

实现细节：

- `recover()` 只在全部前置条件满足时才改状态、清除 recovery、写 `recovery_started`
- `recover()` 使用持久化 `LoopSpec`，并将运行中的 task goal 更新为 `loop_spec.goal`，保证“从头重新执行”使用持久化规格，而不是旧内存状态
- 无 runtime 的旧 approval 不会创建 `_Runtime`

### 修正测试假设

实现后第一次回归时，我修正了两处测试假设，使其与现有 loop 事件语义一致：

1. 恢复成功后除了 `recovery_started` / `task_completed` 之外，还会自然产生 `task_started`、`decision_made`，因此测试改为断言首尾关键事件，而不是把完整事件列表写死。
2. 验证“状态不是 `NEEDS_REVIEW` 时 recover 拒绝”时，不能在 `TaskManager` 初始化前放入 `RUNNING` 任务，因为启动隔离会先把它改成 `NEEDS_REVIEW`；因此改为先构造 manager，再写入该测试任务。

修正后再次运行：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py -q
```

GREEN 结果：

- `13 passed in 1.63s`

## 最终验证

按 brief 指定命令完成最终验证。

### pytest

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py tests/unit/test_loop.py tests/unit/test_loop_approvals.py -q
```

结果：

- `15 passed in 5.06s`

### ruff

```powershell
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe' check src/code_agent/application/task_manager.py src/code_agent/storage.py tests/integration/test_task_manager.py
```

结果：

- `All checks passed!`

### mypy

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe' src
```

结果：

- `Success: no issues found in 33 source files`

## 修改摘要

### `src/code_agent/application/task_manager.py`

- 启动时调用 `store.isolate_interrupted_tasks()`
- 新增 `recover(task_id, provider) -> Task`
- 新增 `_start_runtime(...)`
- `submit()` 改为复用 `_start_runtime(...)`
- `decide_approval()` 对 orphaned approval 返回 `ValueError("approval runtime conflict")`

### `tests/integration/test_task_manager.py`

新增覆盖：

- 启动隔离中断任务
- recover 成功路径
- recover 非法状态/缺失 recovery/spec 的拒绝路径
- orphaned approval 冲突路径

## 非目标/未实现

按 brief 要求，本任务未实现以下能力：

- 自动恢复
- checkpoint 恢复
- 跨进程 worker 接管

## Concerns

1. 当前 `recover()` 通过将 `Task.goal` 更新为持久化 `LoopSpec.goal` 来保证“从头执行”的规格一致性；如果后续 API/UI 需要同时展示“原始任务文案”和“实际运行规格”，可能需要单独建模，而不是复用 `Task.goal`。
2. orphaned approval 目前返回的是 `ValueError("approval runtime conflict")`，已满足本任务测试与冲突语义，但如果后续 API 要暴露更可读的中文错误文案，建议在 API 层统一映射，而不是继续在 `TaskManager` 中内嵌面向终端用户的文案。
