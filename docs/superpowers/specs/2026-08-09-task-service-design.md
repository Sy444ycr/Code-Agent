# Task 18：本地 Mock Agent 端到端任务闭环设计

## 1. 目标与范围

本阶段将现有的核心循环、策略、工具、反馈与 SQLite 模块接入 CLI，形成可重复演示的单机任务闭环。

用户通过以下形式运行任务：

```powershell
code-agent run <workspace> "<goal>" --provider mock --mock-decisions decisions.json --mode supervised --check "python -m pytest -q" --json
```

本阶段只支持单机、单任务和 Mock Provider。Mock 决策来自用户指定的 JSON 场景文件，以保证测试与演示可重复。真实 OpenAI-compatible Provider、WebUI 联动、API 后台任务、多任务并发、取消/恢复和真实 SubAgent 派发不属于本阶段范围。

## 2. 架构

新增应用层 `TaskService`，统一编排任务的创建、运行与持久化：

```text
CLI
  -> TaskService.run
  -> SQLiteStore.create_task
  -> MockScenarioLoader
  -> LoopController.run
  -> PolicyEngine / CLI 审批回调 / ToolExecutor
  -> SQLiteStore 保存任务、事件、审批和最终结果
  -> CLI 输出结果
```

CLI 只负责解析参数、读取 Mock 场景、向用户展示事件和收集即时审批输入。`TaskService` 是任务生命周期的唯一入口，以便后续 API、TUI 与 WebUI 复用同一套运行语义。

## 3. CLI 与 Mock 场景

`code-agent run` 增加以下参数：

- `--provider`：本阶段仅允许 `mock`，默认值为 `mock`。
- `--mock-decisions PATH`：Mock 场景文件，使用 Pydantic 校验为有序的 `AgentDecision` 列表；Mock Provider 时必填。
- `--mode`：`plan`、`supervised` 或 `auto`，默认 `supervised`。
- `--check COMMAND`：可重复指定，构成 `LoopSpec.acceptance_checks`。
- `--json`：输出结构化最终结果；未指定时输出可读摘要。

场景文件使用如下稳定格式：

```json
{
  "decisions": [
    {
      "action": "tool_call",
      "rationale": "读取目标文件",
      "tool_action": {"tool": "read_file", "arguments": {"path": "target.txt"}}
    },
    {
      "action": "complete",
      "completion_message": "验收通过"
    }
  ]
}
```

非法 JSON、未知字段或不满足 `AgentDecision` 约束的场景文件必须在执行工具前失败，并向用户输出明确原因。

## 4. 即时审批

当 `PolicyEngine` 返回 `ask` 时，CLI 显示工具名称、风险等级、命令或路径以及策略原因，并循环提示：

```text
[y] 仅允许这一次
[a] 本任务内允许同类动作
[n] 拒绝
```

- `y`：创建 `approved/once` 审批记录，仅执行当前动作。
- `a`：创建 `approved/task` 审批记录，执行当前动作，并把相应 `RiskLevel` 写入当前任务的临时授权集合。
- `n`：创建 `rejected` 审批记录，任务以 `needs_review` 结束。
- 无效输入重复询问；EOF 与中断输入均视为拒绝。
- `forbidden` 动作永不询问，直接拒绝。

现有 `LoopController` 必须通过注入的审批回调处理 `ask`，而不是立即返回。没有审批回调的调用方保持安全默认值：返回 `needs_review`。

## 5. 持久化、状态与输出

`SQLiteStore` 扩展为支持：

- 读取与更新任务，记录运行中和最终状态。
- 保存与读取审批记录。
- 追加 `task_started`、`decision_made`、`approval_requested`、`approval_decided`、`feedback` 与 `task_completed` 事件。

`task_completed` 事件保存最终状态、报告、验证摘要与修改文件；任务记录保存最终状态。CLI 的 JSON 输出至少包含任务 ID、状态、报告、事件数、修改文件、反馈摘要与验证结果。

成功的退出码为 `0`；`needs_review`、`blocked`、`failed`、`budget_exhausted` 和无效场景输入使用非零退出码。

## 6. 测试与验收

实施严格遵循 TDD：先写失败测试、确认红灯、完成最小实现、确认绿灯，再运行完整回归检查。

最少新增以下测试：

1. Mock 场景解析成功、格式非法和决策非法的测试。
2. CLI 对临时 Git 仓库的端到端测试：Mock 决策读文件、写文件、运行验收命令并最终成功。
3. Supervised 模式下 Shell 动作的 `y`、`a`、`n` 审批测试。
4. 硬性禁止命令不进入审批提示的测试。
5. SQLite 可读取任务最终状态、事件顺序和审批记录的测试。

完成条件：以上测试通过，既有 Python 全量测试、Ruff 与 Mypy 通过；`code-agent run` 能在临时仓库中用 Mock 场景完成一次可验证任务，并保留可查询的执行证据。

## 7. 后续阶段

Task 18 完成后，再按独立规格推进以下工作：

1. API 后台运行、任务查询、取消、恢复和实时 SSE。
2. TUI 与 WebUI 对任务 API、事件和审批的连接。
3. OpenAI-compatible Provider 的安全配置与端到端验证。
4. 多任务控制、SubAgent 实际派发与更强的部署安全措施。
