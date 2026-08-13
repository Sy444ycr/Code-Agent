# Task 25：服务重启后的任务隔离与显式恢复设计

## 1. 目标与范围

Task 25 为单进程 `TaskManager` 增加服务重启后的安全恢复边界。服务启动时不自动重放任何结果未知的工具调用；此前未终态的任务统一进入 `needs_review`，由用户显式确认后从头发起一次新的运行尝试。

本任务处理 SQLite 中的任务运行规格持久化、启动隔离、恢复 API 与 TUI/WebUI 提示。不实现跨进程 worker 接管、循环中间检查点续跑、工具调用幂等性推断或自动恢复。

## 2. 恢复策略

启动时扫描状态为 `pending`、`running`、`waiting_approval` 的任务。每个任务在同一存储操作中更新为 `needs_review`，记录恢复原因“服务重启后需人工复核”，并追加 `recovery_required` 事件。终态任务保持不变。

此前待处理的审批不再可用于唤醒 worker；恢复操作不会沿用旧审批，也不会恢复旧进程的内存上下文。

`POST /api/tasks/{id}/resume` 仅接受带有上述恢复原因的 `needs_review` 任务。成功恢复表示一次新的运行尝试：重新构造 Provider、从持久化的 `LoopSpec` 和原始运行输入开始执行，并追加 `recovery_started` 事件。旧事件、报告与审批记录保留，事件序号继续递增。

## 3. 持久化边界

除现有 `Task` 与 `LoopSpec` 外，存储层保存恢复描述：Provider 名称、原始 Mock 决策（仅 `provider=mock`）以及恢复原因/可恢复标志。

- Mock 的 `AgentDecision` 序列可以持久化，以支持离线、确定性的重新执行。
- 非 Mock Provider 只持久化档案名称；恢复时通过既有 ProviderFactory、项目配置和 keyring 重新解析凭据。
- 不持久化 Provider 密钥、Authorization、Provider 响应正文、内存 worker 状态或工具调用中间结果。

如果 workspace 不存在、Provider 档案不可用或凭据无法读取，恢复请求返回安全错误，任务保持 `needs_review`，且不启动 worker、不执行工具调用。

## 4. API 与客户端契约

任务详情响应新增恢复摘要，例如 `recovery_required`、`recovery_reason` 与 `resumable`。`needs_review` 不再笼统表示可恢复：仅由服务重启隔离产生的任务可通过恢复接口重新运行。

恢复成功后返回 `running` 任务；恢复失败返回 `409` 或安全的 Provider/workspace 错误，且不改变任务状态。TUI 和 WebUI 对可恢复任务显示“服务重启后需人工复核”，恢复控件明确说明“将从头重新执行”。

```text
服务启动
  -> 发现非终态持久化任务
  -> needs_review + recovery_required
  -> 用户检查历史事件
  -> POST resume
  -> 重新解析 Provider 与 workspace
  -> recovery_started
  -> 新 worker 从头运行
```

## 5. 并发与错误处理

启动隔离必须幂等：同一任务最多生成一次 `recovery_required` 事件。恢复与取消、审批决定互斥；没有活动 runtime 的旧审批决定必须返回冲突而非创建运行时状态。

所有状态变更与事件写入保持任务内序号递增。异常不会泄露密钥、配置路径或 Provider 响应正文。恢复失败后不写入伪造的 `recovery_started` 或 `task_completed` 事件。

## 6. 验收标准

- 重启后 `pending`、`running`、`waiting_approval` 均转为带恢复原因的 `needs_review`；终态任务不变。
- 启动隔离重复执行不重复产生恢复事件。
- Mock 任务显式恢复后从头完成，历史事件保留且新事件序号连续。
- workspace 或 Provider 不可用时，恢复安全拒绝、任务仍为 `needs_review`，无工具调用。
- API 详情、TUI 与 WebUI 均展示恢复原因和“从头重新执行”的提示。
- 默认测试不读取 keyring、不访问真实 Provider 网络；所有文档与过程记录使用中文。
