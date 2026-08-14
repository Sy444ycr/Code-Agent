# Task 2 报告

## 任务概述

本任务实现了两部分能力：

1. `TaskManager` 在服务启动时自动隔离中断任务。
2. 用户确认后，`recover()` 让符合条件的任务从头重新执行。

本轮 fix round 1 又补上了一个并发安全缺口：

- 当两个 `TaskManager` / `SQLiteStore` 连接共享同一个 SQLite 数据库时，`recover()` 现在具备 claim-once 语义；同一个恢复任务只会被成功 claim 一次，只会启动一个 runtime。

本任务实际修改文件：

- `src/code_agent/application/task_manager.py`
- `src/code_agent/storage.py`
- `tests/integration/test_task_manager.py`
- `.superpowers/sdd/2026-08-13-task-25-restart-recovery/task-2-report.md`

## 初始实现（Task 2）

### RED

先在 `tests/integration/test_task_manager.py` 增加失败测试，覆盖：

1. `TaskManager.__init__()` 会调用 `store.isolate_interrupted_tasks()`
2. `recover(task_id, provider)` 成功路径
3. 非 recoverable 任务拒绝恢复，且不创建 runtime
4. 无 runtime 的旧 approval 决策返回冲突

首次 RED 验证命令：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py -q
```

首次失败点：

- 启动后任务仍是 `running`
- `TaskManager` 缺少 `recover()`
- orphaned approval 当前抛 `KeyError`，不是冲突

### GREEN

在 `src/code_agent/application/task_manager.py` 中完成最小实现：

1. `__init__()` 调用 `self.store.isolate_interrupted_tasks()`
2. 增加 `recover(task_id, provider) -> Task`
3. 抽取 `_start_runtime(task, loop_spec, provider)`，让 `submit()` 与 `recover()` 共用
4. `decide_approval()` 对 orphaned approval 改为抛 `ValueError("approval runtime conflict")`

其中 `recover()` 的语义为：

- 仅接受：
  - 任务状态为 `TaskStatus.NEEDS_REVIEW`
  - recovery 记录存在且 `required=True`
  - 持久化 `LoopSpec` 存在
- 恢复时：
  - 将任务置为 `RUNNING`
  - 清除 recovery 的 `required`
  - 写入 `recovery_started`
  - 使用持久化 `LoopSpec` 从头执行

### 初始实现验证

修正测试假设后再次运行：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py -q
```

结果：

- `13 passed in 1.63s`

随后按 brief 做完整验证：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py tests/unit/test_loop.py tests/unit/test_loop_approvals.py -q
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe' check src/code_agent/application/task_manager.py src/code_agent/storage.py tests/integration/test_task_manager.py
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe' src
```

结果：

- pytest：`15 passed in 5.06s`
- ruff：`All checks passed!`
- mypy：`Success: no issues found in 33 source files`

## Fix round 1：并发 recover claim-once 修复

### 问题

代码审查指出一个重要缺口：

- `recover()` 只有单个 `TaskManager` 实例内的 `_lock`
- 当两个 manager / store 连接共享同一个 `state.db` 时，这个锁无法跨连接保护数据库状态
- 结果是两个恢复请求可能都看到“可恢复”，然后都成功 claim、都启动 runtime

这是典型的 TOCTOU 竞态：

1. 连接 A 读取 task / recovery / spec
2. 连接 B 读取 task / recovery / spec
3. 两边都认为任务还处于 `needs_review + required=True`
4. 两边各自写入 `RUNNING`、清掉 recovery、写 `recovery_started`
5. 产生重复执行

### RED

先增加并发回归测试：

- 两个 `TaskManager`
- 两个 `SQLiteStore`
- 共享同一个 SQLite 文件
- 同时对同一个恢复任务执行 `recover()`

测试要求：

- 恰好一个成功
- 恰好一个抛 `ValueError`
- 只写入一条 `recovery_started`
- provider 只执行一次
- 只产生一次 `task_completed`

首次 RED 验证命令：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py -q -k concurrent_recover_claims_task_only_once_across_connections
```

首次 RED 结果：

- 失败原因为 `len(successes) == 2`
- 说明两个并发 `recover()` 都成功返回，竞态确实存在

### 根因

原始 `recover()` 的步骤是：

1. `get_task()`
2. `get_recovery()`
3. `get_spec()`
4. 在 manager 本地锁下更新状态、清 recovery、写事件、启动 runtime

这里的问题不是“有没有锁”，而是：

- 读取条件和 claim 写入不在同一个数据库事务里
- manager 的 `_lock` 只保护单个 Python 对象
- 它不保护其他 SQLite 连接

所以跨连接下会双 claim。

### GREEN

在 `src/code_agent/storage.py` 中新增：

```python
claim_recovery(task_id: str, reason: str) -> tuple[Task, LoopSpec]
```

该方法使用 `BEGIN IMMEDIATE`，在单个数据库事务内完成：

1. 读取 task / recovery / spec
2. 校验：
   - task 存在
   - recovery 存在
   - `recovery.required is True`
   - spec 存在
   - task 状态是 `NEEDS_REVIEW`
3. 更新 task 为 `RUNNING`
4. 更新 recovery 为 `required=False`
5. 追加 `recovery_started`
6. 成功后提交

如果任一前置条件不满足：

- 抛出 `ValueError("not restart-recoverable")` 或 `ValueError("not awaiting recovery")`
- 回滚事务

随后在 `src/code_agent/application/task_manager.py` 中把 `recover()` 改成：

1. 在本地 `_lock` 下先检查当前 manager 是否已有 runtime
2. 调用 `store.claim_recovery(...)`
3. 只有 claim 成功后才 `_start_runtime(...)`

这样就把跨连接的争抢保护下沉到了共享数据库这一层。

### 修复后验证

先单跑并发回归测试：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py -q -k concurrent_recover_claims_task_only_once_across_connections
```

结果：

- `1 passed, 13 deselected in 0.93s`

再做本轮 focused 验证：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_task_manager.py tests/unit/test_loop.py tests/unit/test_loop_approvals.py -q
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe' check src/code_agent/application/task_manager.py src/code_agent/storage.py tests/integration/test_task_manager.py
$env:PYTHONPATH='src'
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe' src
```

结果：

- pytest：`16 passed in 4.98s`
- ruff：`All checks passed!`
- mypy：`Success: no issues found in 33 source files`

## 本轮修改摘要

### `src/code_agent/application/task_manager.py`

- `recover()` 不再分步读写恢复状态
- 改为调用 `store.claim_recovery(...)`
- claim 成功后才启动 runtime
- 继续复用 `_start_runtime(...)`
- 保留已有 orphaned approval 冲突语义

### `src/code_agent/storage.py`

- 新增 `claim_recovery(task_id, reason)`
- 在单事务内原子完成：
  - 条件检查
  - task 状态切换
  - recovery 清理
  - `recovery_started` 事件写入

### `tests/integration/test_task_manager.py`

- 新增跨两个 manager / store 连接的并发 recover 回归测试
- 验证：
  - 恰好一个成功
  - 恰好一个失败
  - 不重复执行
  - 不重复写 `recovery_started`

## 非目标

本任务及本轮 fix 都没有实现：

- 自动恢复
- checkpoint 恢复
- 跨进程 worker 接管

## Concerns

1. 当前 `recover()` 仍通过把运行中 `Task.goal` 同步到持久化 `LoopSpec.goal` 来表达“从头执行”；这轮修复没有处理“展示原始 goal 与实际执行 goal 分离”的建模问题。
2. `claim_recovery()` 已经保证 claim 原子性，但如果未来还要把 provider 构建等前置条件也纳入同一套“claim 前检查”，更合适的边界可能是在更上层先完成 provider / workspace 可用性判断，再进入数据库 claim。
