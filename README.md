# Code-Agent

Code-Agent 是 AI4SE 期末项目 A：Coding Agent Harness 的可运行实现。它提供一个受治理的任务循环：任务由 Provider 给出结构化决策，系统在 workspace 边界、权限策略和人工审批约束下执行工具调用，并将任务状态、审批记录和事件持久化到 SQLite。

项目包含 Python 后端、FastAPI REST/SSE API、CLI、Textual TUI、React WebUI、Docker Compose 与 GitLab CI。默认使用离线、可重复的 Mock Provider；不需要真实 API Key 即可演示任务生命周期与安全门控。

## 当前交付能力

- 任务状态机：创建、运行、等待审批、完成、待复核、取消与安全恢复。
- 受 workspace 边界保护的文件、搜索、目录、Git diff、Shell 与检查工具。
- 三种权限模式：`plan`、`supervised`、`auto`。
- 人工审批：允许一次、允许本任务同类风险、拒绝。
- 任务事件通过 SSE 推送到 WebUI Timeline，并持久化到 SQLite。
- Mock Provider 的确定性演示，以及 OpenAI-compatible Provider 的受控配置入口。
- Docker Compose 单容器部署；WebUI 通过主机 TCP 80 提供服务，SQLite 位于命名卷 `code-agent-state`。

## 快速启动

### 本地开发

前提：Python 3.12、Node.js 22、npm 和 Docker（Docker 部署时需要）。

```powershell
pip install -e ".[dev]"
cd web
npm ci
npm run build
cd ..
python scripts/prepare_web_package.py
code-agent web --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000/`。

### Docker Compose

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 code-agent
```

服务监听主机的 TCP 80；课程演示 WebUI 已部署在 <http://121.40.241.117/>。停止服务但保留任务数据：

```bash
docker compose down
```

`docker compose down -v` 会删除 `code-agent-state` 卷及其中的 SQLite 任务记录，执行前应先决定是否需要保留数据。

Ubuntu 22.04 ECS 的完整前置检查、更新、回滚和清理步骤见 [deploy/ecs-ubuntu.md](deploy/ecs-ubuntu.md)。首次演示只需开放 TCP 80；SSH TCP 22 应仅允许可信公网 IP，Ubuntu 实例不应保留公网 RDP 3389 规则。

## WebUI 使用与答辩演示

WebUI 是“任务控制台 + 观察台”，不是浏览器内的代码编辑器。默认部署的 Provider 为 `mock`：它不会调用真实大模型，而是按 **Mock decisions** 中的 JSON 决策逐步执行。这种方式适合稳定演示任务、策略、审批和 Timeline。

### 表单字段

| 字段 | 用途 |
|---|---|
| Workspace | Agent 可操作的工作目录。容器演示中填 `.`，它对应容器内 `/app`，不会访问访问者电脑中的文件。 |
| Goal | 任务目标与演示说明，不能为空。 |
| Mode | 权限模式：`plan`、`supervised` 或 `auto`。 |
| Provider | 课程演示请选择 `mock`。`openai` 需要服务器中已有 Provider 档案和系统 keyring 凭据，默认部署未配置。 |
| Mock decisions | JSON 数组，按顺序指定 Mock Agent 的每一步决策。填 `[]` 没有任何决策，任务会失败。 |

### 推荐演示脚本

每次填写清晰的 Goal，例如“演示监督模式的人工审批”，然后将以下任一 JSON 粘贴到 **Mock decisions** 并点击 **Start Task**。

#### 1. 最小成功任务

Mode 选择 `supervised`：

```json
[
  {
    "action": "complete",
    "completion_message": "任务已完成：Agent 生命周期正常结束。"
  }
]
```

预期：右侧任务状态为 `succeeded`，Timeline 出现任务开始与完成事件。

#### 2. Plan 模式的只读操作

Mode 选择 `plan`：

```json
[
  {
    "action": "tool_call",
    "tool_action": {
      "tool": "list_dir",
      "arguments": {"path": "."}
    }
  },
  {
    "action": "complete",
    "completion_message": "只读检查完成。"
  }
]
```

预期：只读目录操作自动执行并反馈，随后任务完成。

#### 3. Supervised 模式的人工审批

Mode 选择 `supervised`：

```json
[
  {
    "action": "tool_call",
    "rationale": "执行无害状态检查",
    "tool_action": {
      "tool": "shell",
      "arguments": {"command": "echo supervised-demo"}
    }
  },
  {
    "action": "complete",
    "completion_message": "审批后的命令执行完成。"
  }
]
```

预期：任务进入 `waiting_approval`，页面下方出现 **Allow once**、**Allow for task**、**Reject**。点击 **Allow once** 后，Shell 命令执行，Timeline 显示审批决定和完成事件；点击 **Reject** 则任务进入 `needs_review`，展示人工否决。

#### 4. Auto 模式的自动执行

Mode 选择 `auto`：

```json
[
  {
    "action": "tool_call",
    "tool_action": {
      "tool": "shell",
      "arguments": {"command": "echo auto-demo"}
    }
  },
  {
    "action": "complete",
    "completion_message": "自动模式执行完成。"
  }
]
```

预期：普通 Shell 操作无需人工审批即可执行。删除文件和 Git 写入仍属于高风险操作，即使在 `auto` 模式也会请求审批。

#### 5. Plan 模式拒绝执行

Mode 选择 `plan`：

```json
[
  {
    "action": "tool_call",
    "tool_action": {
      "tool": "shell",
      "arguments": {"command": "echo should-not-run"}
    }
  }
]
```

预期：策略阻止 Shell，任务进入 `needs_review`。这可用于说明“计划模式只允许读取，不允许执行或修改”。

### 权限策略摘要

| 动作类别 | Plan | Supervised | Auto |
|---|---|---|---|
| 读取、搜索、Git diff | 自动允许 | 自动允许 | 自动允许 |
| 写入 workspace 文件、运行检查 | 拒绝 | 自动允许 | 自动允许 |
| 普通 Shell | 拒绝 | 请求审批 | 自动允许 |
| 删除文件、Git 写入 | 拒绝 | 请求审批 | 请求审批 |
| `git reset --hard`、强制推送、越界路径等硬性禁止项 | 拒绝 | 拒绝 | 拒绝 |

审批仅对当前任务生效；“Allow once”只允许一次，“Allow for task”允许该任务中同类风险，且授权不会继承到其他任务。

当前 Tool Executor 已实现文件、目录、搜索、Git diff、Shell 和检查工具。联网与安装依赖保留了策略风险分类，但尚未提供通用执行器，因此不应作为已可运行的 WebUI 演示能力。

## ECS 演示部署说明

课程演示推荐 Ubuntu 22.04、Docker Engine、Docker Compose 和 Mock Provider。服务默认不保存真实 API Key、私钥或账号凭据；请勿将密钥写入仓库、命令历史、容器环境变量或页面表单。

部分网络环境下，Docker Hub 或镜像加速器可能无法获取 `node:22-bookworm`、`python:3.12-bookworm` 等基础镜像。若 ECS 上 `docker compose up -d --build` 因基础镜像元数据失败，可在一台能正常构建的本机执行：

```powershell
docker compose build
docker tag <本机Compose镜像名>:latest code-agent-code-agent:latest
docker save code-agent-code-agent:latest | ssh -i "<私钥路径>" ecs-user@<ECS地址> docker load
```

然后在 ECS 的项目目录启动已导入镜像：

```bash
docker compose up -d --no-build
docker compose ps
docker compose logs --tail=100 code-agent
```

确认 `docker compose ps` 显示 `healthy` 后，从浏览器访问 <http://121.40.241.117/>。这是一条用于课程演示的 IP/HTTP 路径；本项目未将域名、HTTPS、多用户访问控制、备份或长期公网运营作为本次交付范围。

## Provider 与安全边界

Mock Provider 是默认且推荐的演示 Provider。若要使用 OpenAI-compatible Provider，需在实际 workspace 的 `.code-agent/config.toml` 中保存非敏感地址与模型，并用 `code-agent auth set <provider>` 将密钥写入系统 keyring；不要把密钥放入配置文件、Git 或 WebUI。

工具执行时会解析真实路径并检查 workspace 边界；Shell 环境会移除 Provider 密钥变量，并受超时和输出上限约束。需要注意：当前 Docker 演示容器没有挂载开发者的真实代码仓库，因此它展示的是受控任务流程，不应被视为可直接修改宿主机项目的生产级远程编码服务。

## 验证命令

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/unit -q
cd web
npm test -- --run
npm run build
```

启用真实 Provider 或 Docker 端到端测试需要显式设置相应环境变量；默认测试和 CI 使用离线 Mock Provider，不会读取真实凭据或访问真实模型服务。

## 目录结构

```text
src/code_agent/       Harness 内核、Provider、API、CLI 与 TUI
web/                  React WebUI 源码、测试与构建配置
tests/                单元测试与集成测试
demos/                Mock LLM 机制演示脚本
deploy/               Ubuntu ECS 部署清单
docs/superpowers/     规格、实施计划与过程设计记录
```

## 仓库文档

- [SPEC.md](SPEC.md)：产品、架构、安全与验收规格。
- [PLAN.md](PLAN.md)：任务拆分与当前执行状态。
- [deploy/ecs-ubuntu.md](deploy/ecs-ubuntu.md)：Ubuntu ECS Docker Compose 部署清单。
- [AGENT_LOG.md](AGENT_LOG.md)：实现过程与人工干预记录。
- [REFLECTION.md](REFLECTION.md)：项目反思。
