# Task 26：ECS 容器化部署与课程交付闭环设计

## 1. 目标

Task 26 为本地 Code-Agent 增加可复现的阿里云 ECS 部署路径，并补齐课程交付所需的 CI 与文档状态。部署默认只运行 Mock Provider，不读取 keyring、不访问真实 Provider，也不将任何凭据写入仓库、镜像、CI 或服务器配置。

本任务的完成标志是：仓库能构建 Linux 容器镜像；Ubuntu 22.04 ECS 能通过 Docker Compose 启动公开 WebUI；SQLite 数据可跨容器重启保留；GitLab CI 中存在 `unit-test` job；README 与计划文档反映实际实现状态。

## 2. 已确认的部署边界

目标服务器将由用户将现有阿里云 ECS 重装为 Ubuntu 22.04 LTS。首轮通过公网 IP 的 HTTP 访问服务，不购买域名、不申请备案、不配置 HTTPS。域名、备案和 HTTPS 是后续上线增强，不能将本任务的 IP/HTTP 演示描述为正式生产部署。

服务器由用户手动管理。本任务不自动登录 ECS、不重装系统、不变更安全组、不购买域名，也不接触任何账号密码、私钥或 API Key。

安全组的目标状态为：公网仅开放 TCP 80；SSH 22 仅允许用户可信公网 IP。原有 Windows RDP 规则不属于仓库变更范围，但重装后不应继续对公网开放。

## 3. 架构

```text
Internet
  -> ECS public IP:80
  -> Docker Compose
  -> code-agent web container
       -> packaged WebUI + FastAPI API
       -> named SQLite volume (tasks, approvals, events)
```

容器入口运行既有 `code-agent web`，监听容器内固定端口，由 Compose 将主机 TCP 80 映射到该端口。任务工作区、SQLite 数据库和日志使用受 Compose 管理的持久化卷或明确宿主机挂载路径；首轮部署只提交 Mock Provider 场景，真实 Provider 需要人工在本地显式启用，不进入云端默认运行路径。

## 4. 仓库交付物

- `Dockerfile`：基于 Python 3.12 Linux 镜像，安装已声明的运行依赖和项目包，包含已构建的 WebUI 资源。
- `docker-compose.yml`：单服务编排、端口映射、健康检查、SQLite 持久化卷、无凭据的默认环境变量。
- `.dockerignore` 与 `deploy/`：最小化构建上下文；提供 Ubuntu 前置检查、部署、更新、回滚和健康检查命令，但不记录真实服务器地址或凭据。
- `.gitlab-ci.yml`：补充课程要求的 `unit-test` job，保持离线验证，不启用真实 Provider E2E。
- 测试：先固定 Dockerfile/Compose 的静态契约红灯；在本地具备 Docker 时才执行容器启动、HTTP 和重启持久化验收。无 Docker 的默认 Python CI 不因环境能力缺失而伪造容器通过。
- `README.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`：纠正“尚未实现”等过期描述，给出 IP/HTTP 演示的限制和可复现的验证证据。

## 5. 失败处理

- 构建前端资源缺失、镜像构建失败或容器健康检查失败时，部署命令必须非零退出，不能声明上线成功。
- SQLite 卷未正确挂载时，重启验收必须失败；不得以临时容器内数据库代替持久化。
- 默认配置尝试使用非 Mock Provider、读取 keyring 或缺少显式 Mock 场景时，必须安全拒绝或保持离线，不得回退到隐式凭据来源。
- 部署文档将端口冲突、Docker 未安装、服务未就绪和安全组未放行列为可诊断的前置失败，而不是自动修改服务器。

## 6. 验收策略

1. 离线仓库验证：Python pytest、Ruff、Mypy、Vitest、Vite build、wheel 干净安装验收以及 GitLab `unit-test` job 配置测试。
2. 本地容器验证：镜像构建、Compose 启动、健康检查、Mock 任务创建与审批、容器重启后的 SQLite 数据保留。
3. ECS 人工验收：用户在 Ubuntu 服务器按部署清单执行，访问 `http://<公网IP>/`，完成 Mock 任务并记录容器状态与公开 URL。

## 7. 非目标

- 自动部署、自动 SSH、自动配置阿里云安全组、域名注册、ICP备案、TLS 证书与 HTTPS。
- 多用户云服务、远程任务队列、Docker 级工具执行隔离、真实 Provider 云端调用。
- 代写 `REFLECTION.md`；该报告必须由学生本人完成，AI 仅可在后续按用户要求提供提纲或润色。
