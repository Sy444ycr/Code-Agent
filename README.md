# Code Agent

AI4SE 期末项目 A：Coding Agent Harness。

本仓库将实现一个小型、由项目代码自行编写的 coding agent harness。当前计划方向是优先做 CLI 版本，重点覆盖可确定性测试的 mock LLM、代码级治理护栏、工具分发、反馈闭环、记忆、配置与分发支持。

## 项目状态

当前阶段：仓库初始化与规格设计。

在 Superpowers 的 brainstorming 与 planning 流程产出并确认 `SPEC.md` 和 `PLAN.md` 之前，不编写实现代码。

## 必需工作流

1. 通过 brainstorming 讨论并确认设计。
2. 编写 `SPEC.md`。
3. 编写 `PLAN.md`。
4. 使用全新 agent 仅根据 `SPEC.md` 与 `PLAN.md` 进行冷启动验证。
5. 按 TDD 流程实现各项任务。
6. 完成评审、文档、打包与分发。

## 安全边界

不要提交真实 API key、凭据、token 或本地密钥。

`.env.example` 只用于说明配置项。真实 `.env` 文件已被 Git 忽略。

## 仓库结构

```text
.
|-- README.md
|-- SPEC.md
|-- PLAN.md
|-- SPEC_PROCESS.md
|-- AGENT_LOG.md
|-- REFLECTION.md
|-- docs/
|   `-- superpowers/
|       `-- specs/
|-- .env.example
|-- .gitignore
|-- AI4SE_Final_Project_A_Coding_Agent_Harness.md
`-- AI4SE_通用要求.md
```

## 开发说明

具体开发命令将在 `SPEC.md` 中确定技术栈后补充。
