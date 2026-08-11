# Task 20：WebUI 任务控制台接入任务 API 设计

## 1. 目标与范围

Task 20 将现有 React WebUI 从静态表单升级为浏览器中的单任务控制台与观察台，消费 Task 19 已提供的 Mock 任务 API、审批状态机和可按事件序号恢复的 SSE 事件流。

本阶段范围：

- 创建 Mock 任务，并选择/填写必要的任务参数。
- 显示任务状态、结果摘要、待审批项和事件时间线。
- 允许一次、允许本任务、拒绝审批，以及取消与安全恢复。
- SSE 断线后从最后成功处理的事件序号恢复，且忽略重复事件。
- React Testing Library 单元交互测试与 Playwright 桌面/移动端验收。

本阶段不包含：

- 桌面 App、移动 App、Textual TUI 或浏览器内代码编辑器。
- OpenAI-compatible Provider、真实密钥配置、多任务控制、跨进程恢复或 SubAgent 实际派发。
- 后端 Task 19 API、状态机或持久化协议的改动。

## 2. 已有能力与约束

Task 19 已提供以下稳定接口：

- `POST /api/tasks`：创建 Mock 任务并立即返回。
- `GET /api/tasks/{task_id}`：查询任务、LoopSpec、结果摘要和 pending approvals。
- `POST /api/tasks/{task_id}/cancel` 与 `POST /api/tasks/{task_id}/resume`：取消及安全恢复。
- `POST /api/approvals/{approval_id}/decision`：提交 `approved`、`scope` 与 `actor`。
- `GET /api/tasks/{task_id}/events?after=N`：有序 JSON 回放。
- `GET /api/tasks/{task_id}/events/stream?after=N`：SSE 回放和实时推送，事件 `id` 为任务内递增 sequence。

WebUI 只将后端状态作为事实来源：不得在浏览器端推断审批是否成功、伪造终态或用事件替代任务详情。SSE 断开不取消任务；终态事件处理完成后关闭连接。

## 3. 页面与组件边界

首屏为实际控制台，不设置营销页或 Hero 区。桌面端采用三栏高密度布局；窄视口（390px）改为单列，按照创建、状态/审批、时间线的顺序排列。

### `App.tsx`

管理选中任务 ID、当前任务详情、连接状态、最后已处理 sequence、全局错误和任务刷新。它只负责状态编排与组件装配，不直接拼接 HTTP 或 SSE 协议。

### `api.ts`

封装 `createTask`、`getTask`、`cancelTask`、`resumeTask`、`decideApproval` 和 `connectTaskEvents`。SSE 连接接收 `after` 游标和事件回调，调用方负责保存游标与重连策略。所有 HTTP 非成功响应转换为含 `detail` 的可显示错误。

### `TaskForm.tsx`

渲染 workspace、goal、mode、Mock 决策 JSON、acceptance checks 和“创建任务”按钮。提交前校验 workspace/goal 非空、Mock 决策为 JSON 数组；提交期间防止重复创建。创建成功后通知 `App` 选中返回任务。

### `TaskSummary.tsx`

显示状态徽标、目标、workspace、mode、provider、结果摘要及当前连接状态。非终态显示取消按钮；只有后端详情表明处于可安全恢复状态时显示恢复按钮。操作完成后刷新任务详情，冲突响应显示后端错误而不乐观改写状态。

### `ApprovalPanel.tsx`

仅在 `pending_approvals` 非空时显示审批理由、风险/影响范围与三种决定：允许一次（`scope=once`）、允许本任务（`scope=task`）及拒绝。请求进行中禁用全部审批按钮；成功后刷新详情，事件流负责呈现状态演变。

### `Timeline.tsx`

按 sequence 升序显示事件类型、时间和可读 payload 摘要。维护已见 sequence 集合，忽略小于或等于最后已处理序号的事件；列表保留本次任务全部事件。连接状态显示“连接中 / 实时 / 正在重连 / 已结束 / 失败”。

## 4. 数据流与重连

```text
TaskForm --POST /api/tasks--> task id --GET detail--> App 状态
                                            |
                                            +--SSE ?after=lastSequence--> Timeline
                                                                        |
审批/取消/恢复 --REST action--> refresh detail <--最新 SSE 事件---------+
```

1. 创建任务成功后，`App` 保存任务 ID、清空旧时间线和游标，拉取详情并以 `after=0` 建立 SSE。
2. 每个 SSE 事件先验证 sequence 大于 `lastSequence`，再追加时间线、更新游标，并触发任务详情刷新（可合并短时间内的多次刷新）。
3. 连接错误时保留当前时间线和游标，标记“正在重连”，按有限递增延迟重连；新连接始终携带 `after=lastSequence`。
4. 若 REST 操作成功，只刷新详情；不在前端自行插入事件或改变终态。
5. 收到 `task_completed` 后刷新详情并在该事件处理完成后结束连接。用户切换/创建另一任务或组件卸载时关闭旧连接与重连计时器。

## 5. 错误处理与可访问性

- 字段校验错误与 API 错误分开显示；错误使用 `role="alert"`。
- 操作中的按钮使用 `disabled` 与明确文案，避免双击产生重复审批或取消请求。
- 所有输入均有可见标签；状态徽标以文本而非仅颜色表达。
- 颜色使用中性灰底色、白色面板和克制的绿/黄/红状态色，不使用渐变营销样式。
- 390px 与 1440px 下不得出现横向溢出、文本重叠或无法触达的审批按钮。

## 6. 测试与验收

React Testing Library/Vitest 必须覆盖：

1. 表单字段、空 goal 校验、非法 Mock 决策 JSON 与成功创建后的任务选中。
2. 任务状态/结果、取消与仅在允许时展示的恢复按钮。
3. pending approval 的三种决定、请求中的禁用及失败提示。
4. SSE 顺序追加、重复 sequence 忽略、断线后携带最后 sequence 重连和组件卸载清理。

Playwright 必须覆盖：

1. 1440px 桌面视口中创建 Mock 任务、查看事件、完成审批并显示终态。
2. 390px 视口中核心控件、审批操作和时间线可见且无重叠/横向滚动。

实现结束时运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
cd web; npm test -- --run
cd web; npm run build
cd web; npm run e2e
```

若 Playwright 浏览器尚未安装，记录确切失败原因与安装/执行命令；不得将该失败误报为应用验收通过。

## 7. 文件边界

- 修改：`web/src/App.tsx`、`web/src/api.ts`、`web/src/types.ts`、`web/src/styles.css`。
- 创建或修改：`web/src/components/TaskForm.tsx`、`TaskSummary.tsx`、`ApprovalPanel.tsx`、`Timeline.tsx`。
- 修改：`web/src/App.test.tsx`、`web/e2e/app.spec.ts` 及必要的测试配置。
- 修改：`SPEC_PROCESS.md`、`AGENT_LOG.md`，记录 TDD 红绿证据与最终验证。

除上述 WebUI、测试与中文过程文档外，不修改 Task 19 后端 API，也不推进 Task 21 或 Task 22。

## 8. 自检

- 没有占位性描述或未决接口；所有端点、事件游标和审批 scope 与 Task 19 契约一致。
- 页面范围只涵盖 WebUI；TUI、真实 Provider、多任务和跨进程恢复均明确排除。
- 重连使用持久化事件 sequence，而非浏览器时间戳或客户端生成 ID。
