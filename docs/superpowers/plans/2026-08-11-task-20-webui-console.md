# Task 20：WebUI 任务控制台接入任务 API 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实施。步骤使用 checkbox（`- [ ]`）跟踪。

**目标：** 将 React WebUI 实现为消费 Task 19 Mock 任务 REST API 与 SSE 事件模型的单任务控制台和观察台。

**架构：** `App` 保存选中任务、详情与事件游标；`api.ts` 仅封装 REST/SSE 协议；TaskForm、TaskSummary、ApprovalPanel、Timeline 分别负责创建、观察/操作、审批和有序事件显示。断线重连从最后成功处理的 sequence 请求事件，不以浏览器时间替代服务端游标。

**技术栈：** React、TypeScript、Vite、Vitest、React Testing Library、Playwright、FastAPI Task 19 API。

## 全局约束

- 页面仅为浏览器 WebUI，不实现桌面 App、移动 App、TUI 或内嵌代码编辑器。
- 只消费既有 Mock API；不修改 Task 19 后端接口、审批状态机或 SQLite 存储。
- 所有行为遵循红灯、最小实现、绿灯、回归检查和独立提交的 TDD 顺序。
- SSE 重连必须携带 `after=lastSequence`，并忽略小于或等于已处理 sequence 的事件。
- 终态、审批和取消/恢复的可用性以服务端详情为准，不做乐观状态伪造。
- UI 文案与过程文档使用中文；代码标识符及 API 字段保留英文。
- 不修改未跟踪的 `.idea/` 目录。

---

## 文件结构

- `web/src/types.ts`：Task 19 API 的前端领域类型、终态与审批 scope。
- `web/src/api.ts`：REST 请求、错误标准化与可关闭的 SSE 连接。
- `web/src/components/TaskForm.tsx`：Mock 任务创建和客户端表单校验。
- `web/src/components/TaskSummary.tsx`：任务状态、取消与安全恢复。
- `web/src/components/ApprovalPanel.tsx`：审批详情及三种决定。
- `web/src/components/Timeline.tsx`：有序事件、去重和连接状态呈现。
- `web/src/App.tsx`：任务选择、详情刷新、SSE 生命周期和组件编排。
- `web/src/styles.css`：桌面三栏/窄屏单栏的紧凑控制台样式。
- `web/src/App.test.tsx`：RTL 组件集成测试与 fetch/EventSource 替身。
- `web/e2e/app.spec.ts`：桌面和 390px Playwright 端到端验收。
- `web/package.json`：Playwright 脚本和开发依赖。
- `SPEC_PROCESS.md`、`AGENT_LOG.md`：红绿证据与最终验证记录。

## 任务依赖

```text
Task 1 类型、API 客户端与表单
                 │
                 ├── Task 2 状态、审批与时间线组件
                 │                │
                 └────────────────┴── Task 3 App 编排、SSE 重连与样式
                                                   │
                                                   └── Task 4 Playwright、完整验证与记录
```

### Task 1：定义 API 契约并接入任务创建表单

**文件：**

- 创建：`web/src/types.ts`
- 创建：`web/src/api.ts`
- 创建：`web/src/components/TaskForm.tsx`
- 修改：`web/src/App.test.tsx`
- 修改：`web/src/App.tsx`

**接口：**

- `TaskCreateInput`：`workspace`、`goal`、`mode`、`provider`、`mock_decisions`、`acceptance_checks`。
- `TaskDetail`：`id`、`status`、`workspace`、`goal`、`mode`、`provider`、`pending_approvals`、`loop_spec`。
- `createTask(input: TaskCreateInput): Promise<TaskDetail>`。
- `TaskFormProps.onCreated(task: TaskDetail): void`。

- [ ] **步骤 1：编写创建与表单校验的失败测试**

在 `web/src/App.test.tsx` 中替换现有静态断言，先加入：

```tsx
it("creates a mock task and selects its response", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
    id: "task-1", status: "running", workspace: "/repo", goal: "inspect",
    mode: "supervised", provider: "mock", pending_approvals: [],
  })));
  render(<App />);

  await user.clear(screen.getByLabelText(/workspace/i));
  await user.type(screen.getByLabelText(/workspace/i), "/repo");
  await user.type(screen.getByLabelText(/goal/i), "inspect");
  await user.click(screen.getByRole("button", { name: /创建任务/i }));

  expect(fetch).toHaveBeenCalledWith("/api/tasks", expect.objectContaining({ method: "POST" }));
  expect(await screen.findByText("task-1")).toBeInTheDocument();
});

it("shows a field error for invalid mock decision JSON", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText(/目标/i), "inspect");
  await user.clear(screen.getByLabelText(/Mock 决策/i));
  await user.type(screen.getByLabelText(/Mock 决策/i), "{");
  await user.click(screen.getByRole("button", { name: /创建任务/i }));
  expect(screen.getByRole("alert")).toHaveTextContent(/JSON 数组/i);
});
```

- [ ] **步骤 2：确认测试按预期失败**

运行：

```powershell
cd web; npm test -- --run src/App.test.tsx
```

预期：失败原因是 `TaskForm`、`createTask` 和任务详情渲染尚未实现。

- [ ] **步骤 3：实现最小 API 客户端、类型和表单**

创建 `web/src/types.ts`，定义稳定的字符串联合：

```ts
export type PermissionMode = "plan" | "supervised" | "auto";
export type TaskStatus = "pending" | "running" | "waiting_approval" | "succeeded" | "needs_review" | "blocked" | "failed" | "budget_exhausted" | "cancelled";
export interface Approval { id: string; task_id: string; reason: string; status: string; }
export interface TaskDetail { id: string; status: TaskStatus; workspace: string; goal: string; mode: PermissionMode; provider: string; pending_approvals: Approval[]; loop_spec?: { acceptance_checks: string[] } | null; }
export interface TaskCreateInput { workspace: string; goal: string; mode: PermissionMode; provider: "mock"; mock_decisions: unknown[]; acceptance_checks: string[]; }
```

创建 `web/src/api.ts`，使用 `requestJson` 检查 `response.ok` 并抛出 `Error(detail)`，再导出：

```ts
export async function createTask(input: TaskCreateInput): Promise<TaskDetail> {
  return requestJson("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
}
```

实现 `TaskForm`：初值为 workspace `.`、mode `supervised`、provider `mock`、Mock 决策 `[]`；提交时要求 goal 非空，解析后要求 `Array.isArray`。解析成功时传递 `TaskCreateInput`；网络异常作为 `role="alert"` 显示。

`App` 暂时仅渲染 `TaskForm` 和最新创建任务 ID，收到 `onCreated` 后保存任务。

- [ ] **步骤 4：运行绿灯与构建检查**

运行：

```powershell
cd web; npm test -- --run src/App.test.tsx
cd web; npm run build
```

预期：目标测试和 TypeScript/Vite 构建均通过。

- [ ] **步骤 5：提交**

```powershell
git add web/src/types.ts web/src/api.ts web/src/components/TaskForm.tsx web/src/App.tsx web/src/App.test.tsx
git commit -m "feat: add web task creation client"
```

### Task 2：实现状态、审批和时间线组件

**文件：**

- 创建：`web/src/components/TaskSummary.tsx`
- 创建：`web/src/components/ApprovalPanel.tsx`
- 创建：`web/src/components/Timeline.tsx`
- 修改：`web/src/types.ts`
- 修改：`web/src/App.test.tsx`

**接口：**

- `TaskSummaryProps.task: TaskDetail`、`onCancel(): Promise<void>`、`onResume(): Promise<void>`。
- `ApprovalPanelProps.approvals: Approval[]`、`onDecision(id, approved, scope): Promise<void>`。
- `TimelineProps.events: TaskEvent[]`、`connection: ConnectionState`。
- `TaskEvent` 至少包含 `sequence`、`type`、`payload`、`created_at`。

- [ ] **步骤 1：编写操作、审批与排序的失败测试**

在 `web/src/App.test.tsx` 追加：

```tsx
it("submits task-scoped approval once and disables duplicate decisions", async () => {
  const user = userEvent.setup();
  const onDecision = vi.fn(() => new Promise<void>(() => {}));
  render(<ApprovalPanel approvals={[{ id: "approval-1", task_id: "task-1", reason: "shell", status: "pending" }]} onDecision={onDecision} />);
  await user.click(screen.getByRole("button", { name: /允许本任务/i }));
  expect(onDecision).toHaveBeenCalledWith("approval-1", true, "task");
  expect(screen.getByRole("button", { name: /允许一次/i })).toBeDisabled();
});

it("renders timeline events in sequence order", () => {
  render(<Timeline connection="realtime" events={[
    { sequence: 2, type: "task_completed", payload: {}, created_at: "2026-08-11T00:00:02Z" },
    { sequence: 1, type: "task_started", payload: {}, created_at: "2026-08-11T00:00:01Z" },
  ]} />);
  expect(screen.getAllByRole("listitem").map((node) => node.textContent)).toEqual([
    expect.stringContaining("task_started"), expect.stringContaining("task_completed"),
  ]);
});
```

- [ ] **步骤 2：确认测试按预期失败**

运行：

```powershell
cd web; npm test -- --run src/App.test.tsx
```

预期：失败原因是三个组件及其 props 尚不存在。

- [ ] **步骤 3：实现最小组件**

为 `types.ts` 增加：

```ts
export interface TaskEvent { sequence: number; type: string; payload: Record<string, unknown>; created_at: string; }
export type ConnectionState = "connecting" | "realtime" | "reconnecting" | "ended" | "failed";
```

`TaskSummary` 输出任务 ID、状态、目标、workspace、结果区域；status 属于 `pending`、`running`、`waiting_approval` 时显示取消。仅当父组件传入 `canResume` 时显示安全恢复，不在组件内猜测安全状态。

`ApprovalPanel` 对每个 pending approval 显示理由，三种按钮传入 `once`、`task` 与拒绝的 `once`；点击后设置本地 pending 标记，直到 promise resolve/reject 后恢复或由父组件移除审批。

`Timeline` 复制 events 后按 `sequence` 数值升序渲染，并以可见文本展示连接状态；payload 用简短 JSON 字符串显示。

- [ ] **步骤 4：运行绿灯**

运行：

```powershell
cd web; npm test -- --run src/App.test.tsx
cd web; npm run build
```

预期：测试和构建通过。

- [ ] **步骤 5：提交**

```powershell
git add web/src/types.ts web/src/components/TaskSummary.tsx web/src/components/ApprovalPanel.tsx web/src/components/Timeline.tsx web/src/App.test.tsx
git commit -m "feat: add web task observation panels"
```

### Task 3：编排 REST 操作、SSE 重连和响应式控制台

**文件：**

- 修改：`web/src/api.ts`
- 修改：`web/src/App.tsx`
- 修改：`web/src/styles.css`
- 修改：`web/src/App.test.tsx`

**接口：**

- `getTask(id: string): Promise<TaskDetail>`。
- `cancelTask(id: string): Promise<TaskDetail>`、`resumeTask(id: string): Promise<TaskDetail>`。
- `decideApproval(id, approved, scope): Promise<void>`。
- `connectTaskEvents(id, after, handlers): () => void`，返回关闭 EventSource 的函数。

- [ ] **步骤 1：编写 SSE 游标与 REST 操作的失败测试**

在 `web/src/App.test.tsx` 中提供可控 `FakeEventSource`，并添加：

```tsx
it("reconnects from the last processed sequence and ignores replayed events", async () => {
  const sources: FakeEventSource[] = [];
  vi.stubGlobal("EventSource", vi.fn((url: string) => {
    const source = new FakeEventSource(url); sources.push(source); return source;
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(taskDetail("task-1"))));
  render(<App initialTaskId="task-1" />);

  await waitFor(() => expect(sources[0].url).toContain("after=0"));
  sources[0].emit("task_started", { sequence: 1, type: "task_started", payload: {}, created_at: "2026-08-11T00:00:01Z" });
  sources[0].fail();
  await vi.advanceTimersByTimeAsync(250);
  expect(sources[1].url).toContain("after=1");
  sources[1].emit("task_started", { sequence: 1, type: "task_started", payload: {}, created_at: "2026-08-11T00:00:01Z" });
  expect(screen.getAllByText(/task_started/)).toHaveLength(1);
});
```

再加入取消测试，断言点击“取消任务”会 `POST /api/tasks/task-1/cancel` 并重新读取详情。

- [ ] **步骤 2：确认测试按预期失败**

运行：

```powershell
cd web; npm test -- --run src/App.test.tsx
```

预期：失败原因是 EventSource 客户端、重连和取消逻辑不存在。

- [ ] **步骤 3：实现最小 SSE 与 App 编排**

`api.ts` 中使用：

```ts
export function connectTaskEvents(taskId: string, after: number, handlers: EventHandlers): () => void {
  const source = new EventSource(`/api/tasks/${taskId}/events/stream?after=${after}`);
  source.onmessage = (event) => handlers.onEvent(JSON.parse(event.data));
  for (const type of ["task_started", "approval_requested", "approval_decided", "task_completed"]) {
    source.addEventListener(type, (event) => handlers.onEvent(JSON.parse((event as MessageEvent).data)));
  }
  source.onerror = () => handlers.onError();
  return () => source.close();
}
```

`App` 在任务 ID 变化时拉取详情并连接 SSE；仅在新事件 sequence 大于 ref 中的最后 sequence 时追加。连接异常时清理旧 source，使用 250ms、500ms、1000ms、2000ms 上限的延迟重连，重连 URL 使用最后 sequence。组件卸载、任务切换和 `task_completed` 均清理 source 与 timeout。取消、恢复、审批成功后调用 `getTask` 刷新详情；失败以 `role="alert"` 显示。

用 CSS Grid 建立桌面三栏；`@media (max-width: 640px)` 切为单列，控件宽度为 `100%`，时间线允许纵向滚动但不横向溢出。色彩使用中性灰、白色面板与文本化状态徽标。

- [ ] **步骤 4：运行绿灯、全量 Web 单测与构建**

运行：

```powershell
cd web; npm test -- --run
cd web; npm run build
```

预期：Vitest 全部通过，构建无 TypeScript 错误。

- [ ] **步骤 5：提交**

```powershell
git add web/src/api.ts web/src/App.tsx web/src/styles.css web/src/App.test.tsx
git commit -m "feat: connect web console to task events"
```

### Task 4：加入 Playwright 验收并记录完整验证

**文件：**

- 修改：`web/package.json`
- 创建：`web/playwright.config.ts`
- 创建：`web/e2e/app.spec.ts`
- 修改：`SPEC_PROCESS.md`
- 修改：`AGENT_LOG.md`

**接口：**

- `npm run e2e`：启动 Vite preview 或 dev server 并运行 Chromium 的桌面/移动验收。
- Playwright 路由 mock 复现 `/api/tasks`、详情、取消、审批及 SSE 的可见 UI 状态。

- [ ] **步骤 1：编写失败的桌面和移动端 Playwright 测试**

创建 `web/e2e/app.spec.ts`：

```ts
import { expect, test } from "@playwright/test";

test("creates and approves a mock task on desktop", async ({ page }) => {
  await page.route("**/api/tasks", async (route) => route.fulfill({ status: 201, json: task("task-1", "waiting_approval") }));
  await page.route("**/api/tasks/task-1", async (route) => route.fulfill({ json: taskWithApproval() }));
  await page.goto("/");
  await page.getByLabel(/目标/i).fill("inspect");
  await page.getByRole("button", { name: /创建任务/i }).click();
  await expect(page.getByRole("button", { name: /允许一次/i })).toBeVisible();
});

test("keeps controls visible at 390 pixels", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /创建任务/i })).toBeVisible();
  await expect(page.locator("body")).not.toHaveJSProperty("scrollWidth", await page.locator("body").evaluate((body) => body.clientWidth + 1));
});
```

- [ ] **步骤 2：确认 Playwright 当前失败**

运行：

```powershell
cd web; npm run e2e
```

预期：失败原因是 `e2e` 脚本、Playwright 配置和浏览器依赖尚未配置。

- [ ] **步骤 3：添加最小 Playwright 配置与可重复 mock**

在 `package.json` 的 `devDependencies` 增加 `@playwright/test`，脚本增加：

```json
"e2e": "playwright test"
```

创建 `playwright.config.ts`，配置 `webServer.command` 为 `npm run dev -- --host 127.0.0.1`、baseURL 为 `http://127.0.0.1:5173`、Chromium 项目和 trace `on-first-retry`。在 e2e 文件中以明确的 route handler 返回 Task 19 字段；审批路由断言请求体含 `approved: true` 与 `scope: "once"`。移动端断言 `document.documentElement.scrollWidth <= window.innerWidth`，而非比较偶然的 body 属性。

- [ ] **步骤 4：执行验收与全量项目验证**

运行：

```powershell
cd web; npm install
cd web; npx playwright install chromium
cd web; npm test -- --run
cd web; npm run build
cd web; npm run e2e
cd ..; .\.venv\Scripts\python.exe -m pytest -q
cd ..; .\.venv\Scripts\python.exe -m ruff check .
cd ..; .\.venv\Scripts\python.exe -m mypy src
```

预期：Vitest、Vite build、Playwright、pytest、Ruff 和 Mypy 全部通过。

- [ ] **步骤 5：记录证据并提交**

在 `SPEC_PROCESS.md` 和 `AGENT_LOG.md` 用中文记录每个任务的红灯命令/摘要、绿灯命令/摘要、人工修正及提交哈希。

```powershell
git add web/package.json web/playwright.config.ts web/e2e/app.spec.ts SPEC_PROCESS.md AGENT_LOG.md
git commit -m "test: verify web task console workflow"
```

## 计划自检

- 规格覆盖：Task 1 实现创建和 API 契约；Task 2 实现状态、审批、取消/恢复呈现和有序时间线；Task 3 实现真实 REST 操作、SSE 游标重连、去重与响应式样式；Task 4 实现 Playwright 与完整验证记录。
- 占位检查：每个任务均列出确切文件、测试代码、红灯命令、最小实现要点、绿灯命令和提交命令。
- 类型一致性：`TaskDetail`、`Approval`、`TaskEvent`、`ConnectionState` 与 `TaskCreateInput` 在前端类型、组件 props 和 API 客户端中使用同一命名；Task 19 的 `scope` 固定为 `once` 或 `task`。
