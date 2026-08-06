# SPEC_PROCESS

本文档记录 `SPEC.md` 与 `PLAN.md` 的生成、评审和验证过程。

## Brainstorming 记录

在 brainstorming 阶段填写。

## Writing-plans 记录

2026-07-11 使用 `superpowers:writing-plans` 将已确认的 `SPEC.md` 拆分为 17 个可执行任务，正式计划保存到 `PLAN.md` 与 `docs/superpowers/plans/2026-07-11-code-agent.md`。计划按 TDD 顺序组织：项目骨架、核心模型、治理策略、workspace 工具、Shell 与语言适配、反馈、LLM Provider、记忆与上下文、Hook、主循环、SubAgent、SQLite、API、CLI/TUI/WebUI、CI 与机制演示。

本轮计划自查覆盖三项：规格覆盖、占位词扫描和接口命名一致性。占位词扫描命令为：

```powershell
rg -n "TBD|TODO|implement later|fill in details|Similar to|类似|适当|后续补" PLAN.md docs/superpowers/plans/2026-07-11-code-agent.md
```

检查结果为空；`PLAN.md` 与默认计划文件的 SHA256 哈希一致。

2026-07-13 根据用户要求，将 `PLAN.md` 调整为明确的 TDD 执行版：新增 `TDD Execution Contract`，要求每个行为变更必须先写失败测试、确认红灯、再写最小实现、确认绿灯、绿灯后重构，并在 `AGENT_LOG.md` 记录红绿证据。此次调整只修改计划与过程文档，不编写实现代码。

## 关键对话节选

记录至少三轮关键交互，以及这些交互如何影响项目决策。

## 采纳与拒绝的建议

在规格和计划评审过程中填写。

## 冷启动验证

在全新 agent 仅使用 `SPEC.md` 与 `PLAN.md` 尝试实现一到两个任务后填写。

## 实现阶段记录

冷启动验证完成后，在隔离 worktree 中按 Task 1–17 执行严格 TDD。每个任务均记录红灯、绿灯、静态检查和提交；Windows 环境缺少 `make` 时，使用等价的 pytest、Ruff 和 Mypy 命令验证底层行为。
