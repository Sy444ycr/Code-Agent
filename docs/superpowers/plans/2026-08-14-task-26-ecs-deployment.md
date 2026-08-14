# Task 26：ECS 容器化部署与课程交付闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供可复现的 Ubuntu ECS Docker Compose 部署路径，持久化任务 SQLite 数据，并补齐课程要求的 GitLab `unit-test` 与交付文档。

**Architecture:** Dockerfile 在构建阶段生成并暂存 WebUI，在运行阶段安装 Python 包并以 `code-agent web --host 0.0.0.0` 提供服务。Compose 只暴露 TCP 80，并把 `.code-agent` 挂到命名卷；离线配置测试始终运行，Docker 运行时验收仅在本机 Docker 可用时运行。

**Tech Stack:** Python 3.12、FastAPI/Uvicorn、React/Vite、Docker BuildKit、Docker Compose、pytest、GitLab CI。

## Global Constraints

- 文档、界面和诊断默认使用中文；代码标识符、命令和第三方产品名可保留英文。
- 默认部署仅运行 Mock Provider；不得读取 keyring、访问真实 Provider 或写入 API Key、账号、私钥和服务器公网地址。
- 目标系统为 Ubuntu 22.04 LTS；首轮只通过公网 IP 的 HTTP 访问，不实现域名、备案、HTTPS 或自动部署。
- Compose 仅发布主机 TCP 80；SSH 与阿里云安全组由用户手动管理，不由代码或脚本自动变更。
- SQLite 数据必须挂载在 Compose 命名卷中，容器重启后仍可读取任务记录。
- 每个任务严格遵循 RED → GREEN → REFACTOR，并完成规格合规与代码质量两阶段评审。

---

## 文件结构

- `Dockerfile`：构建 Vite 资源、暂存包内资源、安装发行包、运行 Web 服务。
- `docker-compose.yml`：唯一 `code-agent` 服务、80 端口、健康检查和 `code-agent-state` 命名卷。
- `.dockerignore`：排除本地虚拟环境、git 元数据、测试产物、密钥与数据库，避免泄漏和无效构建上下文。
- `tests/integration/test_docker_deployment.py`：静态 Docker/Compose 契约；可选真实 Docker 启动、HTTP 和重启持久化验收。
- `.gitlab-ci.yml`：保留 `web-build`、新增课程规定的 `unit-test`、最后运行 `package`。
- `deploy/ecs-ubuntu.md`：人工重装 Ubuntu 后的前置检查、部署、更新、回滚与排错命令。
- `README.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`：实际状态、部署限制、验证结果和提交证据。

### Task 1：Docker 构建与 Compose 配置契约

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `tests/integration/test_docker_deployment.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `web/package.json` 的 `build` 脚本、`scripts/prepare_web_package.py`、`code-agent web --host --port`。
- Produces: `docker compose -f docker-compose.yml up -d --build`；服务名 `code-agent`；命名卷 `code-agent-state`；容器内状态路径 `/var/lib/code-agent/state.db`。

- [ ] **Step 1: Write the failing test**

在 `tests/integration/test_docker_deployment.py` 写入 YAML/文本契约测试：断言 `Dockerfile` 尚不存在；最终契约要求 Node 22 构建阶段执行 `npm ci`、`npm run build` 和 `python scripts/prepare_web_package.py`，运行阶段使用 Python 3.12、非 root 用户、`EXPOSE 8000`、`CMD ["code-agent", "web", "--host", "0.0.0.0", "--port", "8000"]`。断言 Compose 的 `code-agent` 服务仅发布 `80:8000`，以 `CODE_AGENT_STATE_PATH=/var/lib/code-agent/state.db` 配置状态路径，挂载 `code-agent-state:/var/lib/code-agent`，并定义 HTTP 健康检查。

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_docker_deployment.py::test_deployment_configuration_contract -q`

Expected: FAIL，原因是 `Dockerfile` 或 `docker-compose.yml` 尚不存在。

- [ ] **Step 3: Write minimal implementation**

创建多阶段 `Dockerfile`：Node 阶段复制 `web/package*.json` 后运行 `npm ci`，复制 Web 源码并运行 `npm run build`；Python 构建阶段复制 Python 源码、构建产物和 `scripts/prepare_web_package.py`，运行资源暂存与 `python -m build`；运行阶段仅安装刚构建 wheel，创建归属非 root 用户的 `/var/lib/code-agent`，以固定命令启动服务。创建 Compose 命名卷、80:8000 映射、`restart: unless-stopped`、`wget` 或 Python 标准库 HTTP 健康检查；不写任何密钥、IP 或 Provider 档案。`.dockerignore` 排除 `.env*`（保留 `.env.example`）、`.git`、`.venv`、`node_modules`、构建产物、数据库和测试输出。`.gitignore` 增加本地 Compose 覆盖文件和本地部署状态路径。

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_docker_deployment.py::test_deployment_configuration_contract -q`

Expected: PASS；再运行 `docker compose -f docker-compose.yml config`。若 Docker CLI 不可用，记录该命令因环境缺失无法执行，但不得替换为通过结果。

- [ ] **Step 5: Commit**

```powershell
git add Dockerfile docker-compose.yml .dockerignore .gitignore tests/integration/test_docker_deployment.py
git commit -m "feat: add container deployment configuration"
```

### Task 2：容器运行、HTTP 与 SQLite 持久化验收

**Files:**
- Modify: `tests/integration/test_docker_deployment.py`

**Interfaces:**
- Consumes: Task 1 的 Compose 服务、`code-agent-state` 卷、`/api/tasks` API。
- Produces: 标记为 Docker 可选的 `test_compose_serves_webui_and_preserves_state`，验证服务可用并跨容器重启保留数据库。

- [ ] **Step 1: Write the failing test**

在同一测试文件新增测试：用 `shutil.which("docker")` 检测 Docker，不可用时 `pytest.skip("Docker CLI 不可用，跳过容器运行时验收")`；可用时使用临时 Compose project 名和空闲本机端口执行 `docker compose up -d --build`，轮询根路径；POST `/api/tasks` 创建含 `provider: "mock"` 与最小 `mock_decisions` 的完成任务；查询任务详情；执行 `docker compose restart code-agent` 后再次查询相同任务 ID，断言状态、goal 和 task ID 保留；finally 中 `docker compose down -v` 清理临时 project。

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_docker_deployment.py::test_compose_serves_webui_and_preserves_state -q`

Expected: Docker 可用时 FAIL，原因是运行时验收尚未实现；Docker 不可用时 SKIPPED，并在日志说明非通过。

- [ ] **Step 3: Write minimal implementation**

只在测试中补齐受 `CODE_AGENT_RUN_DOCKER_E2E=1` 显式开关保护的启动、轮询和清理辅助函数；不修改生产服务行为。开关未启用时跳过，确保默认 CI 不需要 Docker daemon；开关启用时所有子进程使用临时 project 名和随机主机端口，失败时输出 `docker compose logs` 的截断诊断但不输出环境变量。

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:CODE_AGENT_RUN_DOCKER_E2E='1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_docker_deployment.py -q`

Expected: Docker 可用时 PASS，证明 WebUI、Mock API 和重启后 SQLite 数据均可用；Docker 不可用时记录 SKIPPED。随后清除 `CODE_AGENT_RUN_DOCKER_E2E` 并运行同一命令，预期仅静态契约 PASS、运行时测试 SKIPPED。

- [ ] **Step 5: Commit**

```powershell
git add tests/integration/test_docker_deployment.py
git commit -m "test: verify container deployment persistence"
```

### Task 3：补齐 GitLab `unit-test` 与离线发布链

**Files:**
- Modify: `.gitlab-ci.yml`
- Modify: `tests/integration/test_package_install.py`

**Interfaces:**
- Consumes: `make verify`、前端 `npm ci && npm test -- --run && npm run build`、Task 1 的静态部署测试。
- Produces: GitLab job `unit-test`，在 `package` 之前执行 Python 测试、Ruff 与 Mypy；真实 Provider/Docker E2E 均未启用。

- [ ] **Step 1: Write the failing test**

在 `test_ci_and_makefile_run_web_build_before_python_package` 中增加断言：GitLab `stages` 含 `unit-test`；`gitlab["unit-test"]` 存在、使用 `python:3.12-bookworm`、运行 `pip install -e ".[dev]"` 和 `make verify`；`package["needs"]` 同时依赖 `web-build` 与 `unit-test`，且 `unit-test` 的脚本不包含 `CODE_AGENT_RUN_PROVIDER_E2E` 或 Docker E2E 开关。

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH='src;.'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_package_install.py::test_ci_and_makefile_run_web_build_before_python_package -q`

Expected: FAIL，原因是 `.gitlab-ci.yml` 尚无 `unit-test` job。

- [ ] **Step 3: Write minimal implementation**

将 GitLab stages 调整为 `[web, unit-test, package]`；新增 `unit-test` job，使用 Python 3.12 镜像安装开发依赖并运行 `make verify`；`package` 保持现有前端工件依赖，额外通过 `needs` 依赖 `unit-test`，再进行资源暂存、打包与 wheel 安装验收。不要在 CI 中设置任何真实 Provider 或 Docker E2E 环境变量。

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONPATH='src;.'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_package_install.py -q`

Expected: PASS；再执行 `.\.venv\Scripts\ruff.exe check .` 和 `.\.venv\Scripts\mypy.exe src`，预期均成功。

- [ ] **Step 5: Commit**

```powershell
git add .gitlab-ci.yml tests/integration/test_package_install.py
git commit -m "ci: add required GitLab unit-test job"
```

### Task 4：Ubuntu ECS 部署清单与课程文档收尾

**Files:**
- Create: `deploy/ecs-ubuntu.md`
- Modify: `README.md`
- Modify: `PLAN.md`
- Modify: `SPEC_PROCESS.md`
- Modify: `AGENT_LOG.md`

**Interfaces:**
- Consumes: `docker compose -f docker-compose.yml up -d --build`、Task 1/2 的端口、卷和环境边界、Task 3 的 CI job。
- Produces: 用户可在重装后的 Ubuntu 22.04 ECS 上按文档部署并以公网 IP/HTTP 验收；项目文档不再声明尚未实现。

- [ ] **Step 1: Write the failing documentation checks**

在 `tests/integration/test_docker_deployment.py` 新增文档契约测试：`deploy/ecs-ubuntu.md` 必须包含 Ubuntu 22.04、Docker Engine、Docker Compose、`git clone`、`docker compose up -d --build`、`docker compose ps`、`docker compose logs`、`docker compose pull`/`down` 回滚说明、TCP 80 与 SSH 来源限制；README 必须包含 Docker Compose 部署章节、IP/HTTP 仅为临时演示、默认 Mock Provider、不得在服务器写入真实 API Key。断言 README 不含“实现尚未开始”“尚未进入实现阶段”及“待生成的细粒度实施计划”。

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_docker_deployment.py::test_ecs_deployment_docs_are_complete -q`

Expected: FAIL，原因是部署清单不存在，且 README 仍含过期状态。

- [ ] **Step 3: Write minimal implementation**

编写中文部署清单：用户重装 Ubuntu 后，先收紧安全组，再安装 Docker Engine 与 Compose 插件；克隆公开仓库、构建启动、查看状态和日志、通过 `http://<公网IP>/` 访问；写明 `code-agent-state` 卷、升级和失败回滚步骤。README 用实际运行/打包/CI 状态替换旧设计期措辞，链接部署清单，明确域名、备案、HTTPS 尚未完成。将 `PLAN.md` 的 Task 17/Task26 状态与 commit hash 更新为实际记录；在过程文档与日志中记录 RED/GREEN、Docker 可用性和用户完成的 ECS 人工验收结果。不得代写 `REFLECTION.md`。

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_docker_deployment.py -q`

Expected: 静态契约与文档测试 PASS；Docker 运行时测试仅在显式开关和 Docker 可用时 PASS。最后运行完整离线验证：`.\.venv\Scripts\python.exe -m pytest -q`、`.\.venv\Scripts\ruff.exe check .`、`.\.venv\Scripts\mypy.exe src`、`web\npm.cmd test -- --run`、`web\npm.cmd run build`。

- [ ] **Step 5: Commit**

```powershell
git add deploy/ecs-ubuntu.md README.md PLAN.md SPEC_PROCESS.md AGENT_LOG.md tests/integration/test_docker_deployment.py
git commit -m "docs: complete ECS deployment handoff"
```

## 规格覆盖自查

- Linux Docker 镜像、Compose、80 端口、命名卷与健康检查：Task 1。
- WebUI/API 可用与跨容器 SQLite 持久化：Task 2。
- GitLab `unit-test`、默认离线 CI 与发布链：Task 3。
- Ubuntu 部署、IP/HTTP 限制、安全组手工边界、README/PLAN/过程记录：Task 4。
- 自动 SSH、自动部署、域名、备案、HTTPS、真实云端 Provider 和反思报告均明确不在范围内。

## 计划自查

- 占位词扫描不含 `TBD`、`TODO`、`implement later`、`fill in details`、`Similar to`。
- `code-agent-state`、`/var/lib/code-agent/state.db`、`CODE_AGENT_RUN_DOCKER_E2E`、GitLab `unit-test` 在所有任务中命名一致。
- 每项生产或配置行为均有先行失败测试；文档更新由文档契约测试保护。
