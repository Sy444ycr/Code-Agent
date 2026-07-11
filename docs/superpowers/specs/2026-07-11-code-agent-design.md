# Code-Agent brainstorming 设计记录

## 状态

- 日期：2026-07-11
- 结果：整体设计已由用户逐段确认
- 正式规格：[SPEC.md](../../../SPEC.md)

本文件记录 `superpowers:brainstorming` 阶段形成的关键设计决策。完整、可执行的产品与系统规格以仓库根目录 `SPEC.md` 为准。

## 关键决策

1. 采用 Web-first 完整控制台方案，同时提供 Textual TUI 和非交互 CLI。
2. 产品定位为面向任意文本代码仓库的通用编码助手，覆盖需求实现、Bug 修复、测试补充、小型重构、配置和文档修改。
3. 后端使用 Python、FastAPI、Pydantic、SQLAlchemy 与 SQLite；前端使用 React、Vite 与 TypeScript。
4. 自行实现 Agent 主循环，不使用高层 Agent Runner；同时提供 Mock LLM 和 OpenAI-compatible Provider。
5. 以受治理的反馈循环和轻量结构化项目记忆作为双核心贡献。
6. 在主循环外增加 LoopSpec 与 Loop Controller，显式管理目标、验收、预算、恢复和终止状态。
7. 所有动作经过 Policy Engine；提供 Plan、Supervised、Auto 三种模式，硬性安全边界不可关闭。
8. 提供内置 Hook 与项目 Hook；Hook 能增加限制和反馈，但不能绕过核心护栏。
9. 记忆采用 SQLite 与规则检索，不使用重型向量 RAG；只有确定性或已验证信息可以晋升为长期记忆。
10. Coordinator 可派发 Explorer、Implementer、Verifier、Reviewer 四类 SubAgent；只读任务可有限并行，同一 workspace 仅一个写入者。
11. SubAgent 使用隔离的最小上下文，只向父 Agent 返回结构化总结与运行时证据引用。
12. Git 管理通过 Shell Tool 完成，不建立独立 GitService；Policy Engine 按 Git 子命令风险分类。
13. 模型 API 是受控 Provider 通道；Agent 的任意联网在 Supervised 模式审批、Auto 模式放行，硬性风险仍禁止。
14. 凭据首选系统钥匙串，环境变量和 `.env` 仅作开发回退；密钥不得进入子进程、Prompt、日志和数据库。
15. WebUI 使用 Open Design 工作流和仓库级 `DESIGN.md`，以 Linear 风格设计系统为起点。
16. 项目以 Python 包分发，通过 `pipx` 安装；WebUI 静态资源随包提供。

## 方案取舍

最终选择“模块化单体 + 共享任务服务”。相比 CLI-first 报告工具，它能更自然地展示审批、反馈、记忆和 SubAgent；相比后端平台化方案，它保持了课程所需 Harness 机制的清晰边界。首版主动排除多用户、分布式队列、多写 Agent 合并、重型 RAG 和在线 IDE，以控制实现与验证范围。

## 设计确认说明

设计按产品定位、架构、治理、Hook、反馈、记忆、界面、异常处理、技术栈、安全、权限模式、SubAgent、上下文管理和 Git 能力逐段讨论。用户对各部分确认后，批准将整体设计暂定为首版实现依据。
