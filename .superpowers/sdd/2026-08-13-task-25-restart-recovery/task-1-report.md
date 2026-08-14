# Task 1 实施报告：恢复描述持久化与幂等启动隔离

## 修改文件

- `src/code_agent/core/models.py`
  - 新增 `TaskRecovery(required: bool = False, reason: str | None = None, mock_decisions: list[AgentDecision] | None = None)`
- `src/code_agent/storage.py`
  - 新增 `recoveries` 表
  - 新增 `save_recovery(task_id, recovery)` 与 `get_recovery(task_id)`
  - 新增 `isolate_interrupted_tasks()`
  - 将任务、恢复记录、事件写入拆分为锁内辅助方法
- `tests/integration/test_storage.py`
  - 新增 `test_recovery_roundtrip`
  - 新增 `test_isolate_interrupted_tasks_marks_only_non_terminal_tasks_once`
  - 补充对恢复 reason 的精确断言

## 测试命令与结果

1. 失败验证（TDD 红灯）
   - 命令：`& '.venv/Scripts/python.exe' -m pytest tests/integration/test_storage.py -q`
   - 结果：先因 `SQLiteStore` 缺少 `isolate_interrupted_tasks` / `TaskRecovery` 等功能而失败，符合预期的功能缺失失败。

2. 定向测试
   - 命令：`$env:PYTHONPATH='C:\\Users\\sy444\\Desktop\\Agents\\.worktrees\\task-25-restart-recovery\\src'; & 'C:\\Users\\sy444\\Desktop\\Agents\\.venv\\Scripts\\python.exe' -m pytest tests/integration/test_storage.py -q`
   - 结果：`8 passed in 0.72s`

3. 代码风格
   - 命令：`$env:PYTHONPATH='C:\\Users\\sy444\\Desktop\\Agents\\.worktrees\\task-25-restart-recovery\\src'; & 'C:\\Users\\sy444\\Desktop\\Agents\\.venv\\Scripts\\python.exe' -m ruff check src tests`
   - 结果：`All checks passed!`

4. 类型检查
   - 命令：`$env:PYTHONPATH='C:\\Users\\sy444\\Desktop\\Agents\\.worktrees\\task-25-restart-recovery\\src'; & 'C:\\Users\\sy444\\Desktop\\Agents\\.venv\\Scripts\\python.exe' -m mypy src`
   - 结果：`Success: no issues found in 33 source files`

## 自审

- 恢复记录已可持久化与读取，且能携带 `mock_decisions`。
- 启动隔离只影响 `PENDING`、`RUNNING`、`WAITING_APPROVAL` 三类任务，终态任务保持不变。
- 隔离后任务状态会原子地改为 `NEEDS_REVIEW`，reason 固定为 `服务重启后需人工复核`，并追加一次 `recovery_required` 事件。
- 重复调用不会再产生新事件，返回空列表。
- SQLite 新表采用 `CREATE TABLE IF NOT EXISTS`，对既有数据库兼容。

## 疑问 / 备注

- 当前工作区的包解析路径曾指向其他 worktree，因此验证命令显式设置了 `PYTHONPATH` 指向当前 worktree 的 `src`，以确保测试与实现来自同一份源码。
- 简报未要求新增自动重放或 checkpoint 恢复，本次未实现。

## 修复轮次 1 追加说明（并发幂等性）

### 问题

复核发现，`isolate_interrupted_tasks()` 在两个独立 `SQLiteStore` 连接并发调用时仍可能同时读到同一批 interrupted tasks，导致重复写入 `recovery_required` 事件。

### 处理

- 为 `isolate_interrupted_tasks()` 增加 `BEGIN IMMEDIATE` 事务边界，把读取、状态改写、恢复记录写入和事件追加收敛在同一个数据库事务中。
- 保持其余写路径不变，仅修复跨连接并发下的原子认领问题。

### 新增回归测试

- `test_isolate_interrupted_tasks_claims_once_across_connections`
  - 使用同一 SQLite 文件的两个独立 `SQLiteStore` 连接并发调用隔离逻辑
  - 断言只有一个调用返回非空结果
  - 断言只产生一次 `recovery_required` 事件
  - 断言任务最终进入 `NEEDS_REVIEW`

### 本轮验证

- `pytest tests/integration/test_storage.py -q -k 'claims_once_across_connections'`
- `pytest tests/integration/test_storage.py -q`
- `ruff check src tests`
- `mypy src`

以上命令均通过。
