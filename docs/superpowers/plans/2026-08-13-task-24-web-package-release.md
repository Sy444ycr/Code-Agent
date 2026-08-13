# Task 24：WebUI 打包与干净安装验收实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施。步骤使用 checkbox（`- [ ]`）跟踪。

**目标：** 让 `code-agent web` 在干净环境从 wheel 安装后提供 WebUI、静态资源和既有 API，并使发布流程在 Python 打包前明确完成前端构建与资源暂存。

**架构：** 新增发布资源脚本，将已验证的 `web/dist` 复制到 `src/code_agent/web_dist`；Hatchling 将该包内目录包含在 sdist 和 wheel。`web_assets.py` 优先定位安装包资源，其次定位源码 `web/dist`；FastAPI 在所有 API 路由之后挂载 SPA 回退路由。干净安装验收在临时虚拟环境安装刚构建的 wheel，并以子进程验证 CLI 与 HTTP 路由契约。

**技术栈：** Python 3.12、Hatchling、FastAPI、Typer、pytest、httpx、Vite、Vitest、GitHub Actions、GitLab CI。

## 全局约束

- `python -m build` 不得调用 Node、npm 或 Vite；前端构建和资源暂存必须在打包之前由明确的发布命令执行。
- 默认测试、构建和安装验收不得读取 Provider 凭据或访问真实 Provider 网络。
- 已安装包资源目录固定为 `code_agent/web_dist`，开发回退目录固定为仓库 `web/dist`。
- `/api/...` 必须优先于 SPA 静态资源回退路由；路径穿越不能读取资源根目录外的文件。
- 缺少前端资源时发布预检必须以固定中文错误失败，不得生成不含 WebUI 的发布包。
- 不修改既有 SQLite schema、Task API/SSE 事件格式、Provider、Policy Engine 或审批状态机。
- 文档与过程记录使用中文；保留既有 FastAPI/Starlette 和 Vite 警告的真实状态。

---

## 文件结构

- 新建 `scripts/prepare_web_package.py`：验证 `web/dist`，清理并复制资源到 `src/code_agent/web_dist`。
- 修改 `pyproject.toml`：将包内 `web_dist` 明确纳入 Hatchling sdist/wheel。
- 修改 `.gitignore`：忽略生成的 `src/code_agent/web_dist/`，保留源码和构建产物分离。
- 修改 `src/code_agent/web_assets.py`：按包内优先、源码回退顺序解析资源，安全挂载 SPA 路由。
- 修改 `tests/integration/test_web_runtime.py`：覆盖资源优先级、SPA 回退、API 优先和路径边界。
- 新建 `tests/integration/test_package_install.py`：构建 wheel 并在临时 venv 中安装、验证包内资源和 CLI/HTTP 行为。
- 修改 `Makefile`、`.github/workflows/ci.yml`、`.gitlab-ci.yml`：声明统一发布顺序。
- 修改 `README.md`、`AGENT_LOG.md`、`SPEC_PROCESS.md`：记录发布入口、TDD 和验收结果。

### Task 1：发布资源暂存与包数据

**文件：**

- 新建：`scripts/prepare_web_package.py`
- 修改：`pyproject.toml`、`.gitignore`
- 测试：`tests/integration/test_package_install.py`

**接口：**

- 产生：`prepare_web_package(repo_root: Path) -> Path`
- 产生：`src/code_agent/web_dist/index.html` 及 Vite 生成的 assets 文件。
- 失败：前端入口缺失时抛出 `WebPackagePreparationError("WebUI 构建产物缺失，请先运行 npm run build。")`。

- [ ] **步骤 1：写失败测试。**

```python
from pathlib import Path
import pytest

from scripts.prepare_web_package import WebPackagePreparationError, prepare_web_package


def test_prepare_web_package_rejects_missing_frontend_dist(tmp_path: Path) -> None:
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    with pytest.raises(WebPackagePreparationError, match="WebUI 构建产物缺失"):
        prepare_web_package(tmp_path)
```

- [ ] **步骤 2：运行红灯。**

运行：`$env:PYTHONPATH="src;."; .\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q`

预期：因 `scripts.prepare_web_package` 不存在而收集失败。

- [ ] **步骤 3：实现最小资源暂存与包数据配置。**

```python
class WebPackagePreparationError(RuntimeError):
    pass


def prepare_web_package(repo_root: Path) -> Path:
    source = repo_root / "web" / "dist"
    if not (source / "index.html").is_file():
        raise WebPackagePreparationError("WebUI 构建产物缺失，请先运行 npm run build。")
    target = repo_root / "src" / "code_agent" / "web_dist"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target
```

在 `pyproject.toml` 的 Hatchling 配置中明确包含 `src/code_agent/web_dist/**`；在 `.gitignore` 中新增 `src/code_agent/web_dist/`，避免生成资源被提交。

- [ ] **步骤 4：运行绿灯与静态检查。**

运行：`$env:PYTHONPATH="src;."; .\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q; .\.venv\Scripts\ruff.exe check scripts tests/integration/test_package_install.py; .\.venv\Scripts\mypy.exe src`

预期：缺失资源返回固定错误；存在最小 `web/dist/index.html` 时资源被复制；Ruff 与 Mypy 通过。

- [ ] **步骤 5：提交。**

```powershell
git add scripts/prepare_web_package.py pyproject.toml .gitignore tests/integration/test_package_install.py
git commit -m "build: stage web assets for python packages"
```

### Task 2：包内资源解析与 SPA/API 路由契约

**文件：**

- 修改：`src/code_agent/web_assets.py`、`src/code_agent/api/app.py`
- 修改：`tests/integration/test_web_runtime.py`

**接口：**

- 消费：`static_dist_path() -> Path | None`
- 产生：`mount_web_assets(app: FastAPI) -> None`
- 产生：包内资源优先、源码资源回退、无资源时仅 API 的确定性行为。

- [ ] **步骤 1：写失败测试。**

```python
def test_package_assets_take_precedence_and_api_routes_are_not_spa_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dist = tmp_path / "package" / "web_dist"
    source_dist = tmp_path / "source" / "web" / "dist"
    package_dist.mkdir(parents=True)
    source_dist.mkdir(parents=True)
    (package_dist / "index.html").write_text("package", encoding="utf-8")
    (source_dist / "index.html").write_text("source", encoding="utf-8")
    monkeypatch.setattr("code_agent.web_assets._asset_candidates", lambda: [package_dist, source_dist])

    assert static_dist_path() == package_dist
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    assert client.get("/").text == "package"
    assert client.get("/client/route").text == "package"
    assert client.get("/api/tasks/not-found").status_code == 404
```

- [ ] **步骤 2：运行红灯。**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_web_runtime.py -q`

预期：当前实现没有 `_asset_candidates`，且不覆盖包内优先、SPA 回退和 API 优先级。

- [ ] **步骤 3：实现最小资源解析和安全挂载。**

```python
def _asset_candidates() -> list[Path]:
    return [
        Path(__file__).resolve().parent / "web_dist",
        Path(__file__).resolve().parents[2] / "web" / "dist",
    ]


def static_dist_path() -> Path | None:
    return next((path for path in _asset_candidates() if (path / "index.html").is_file()), None)
```

保留 `mount_web_assets` 的 catch-all 路由，但在返回文件前使用 `requested.is_relative_to(dist.resolve())` 判断路径边界；不存在的非 API 文件统一回退 `index.html`。在 `create_app` 所有 `/api` 路由定义完成后调用 `mount_web_assets(app)`。

- [ ] **步骤 4：运行绿灯与静态检查。**

运行：`$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/integration/test_web_runtime.py tests/integration/test_api_sse.py -q; .\.venv\Scripts\ruff.exe check src tests/integration/test_web_runtime.py; .\.venv\Scripts\mypy.exe src`

预期：包内优先、源码回退、SPA 回退、API `404` 优先和路径边界测试通过。

- [ ] **步骤 5：提交。**

```powershell
git add src/code_agent/web_assets.py src/code_agent/api/app.py tests/integration/test_web_runtime.py
git commit -m "feat: serve packaged web assets safely"
```

### Task 3：wheel 干净安装与 HTTP 验收

**文件：**

- 修改：`tests/integration/test_package_install.py`

**接口：**

- 消费：`scripts.prepare_web_package.prepare_web_package(repo_root)`、`dist/code_agent-*.whl`
- 产生：临时 venv 中 wheel 安装、CLI 帮助、包内资源、HTTP 根路径和 API 404 的验收。

- [ ] **步骤 1：写失败测试。**

```python
def test_built_wheel_installs_with_web_assets_in_clean_venv(tmp_path: Path) -> None:
    wheel = build_project_wheel(REPO_ROOT)
    venv_python = create_venv(tmp_path / "venv")
    install_wheel(venv_python, wheel)

    assert run(venv_python, "-m", "code_agent.web_assets", "--check").returncode == 0
    assert run_code_agent(venv_python, "--help").returncode == 0
    assert run_code_agent(venv_python, "web", "--help").returncode == 0
```

- [ ] **步骤 2：运行红灯。**

运行：`$env:PYTHONPATH="src;."; .\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q`

预期：wheel 中尚未包含 `code_agent/web_dist/index.html`，或尚无干净安装 HTTP 验收辅助函数。

- [ ] **步骤 3：实现最小验收辅助与 wheel 检查。**

测试中使用 `subprocess.run` 创建 `venv`、安装刚生成的 wheel；通过 `zipfile.ZipFile` 断言 wheel 包含 `code_agent/web_dist/index.html`。使用 `subprocess.Popen` 启动安装环境的 `code-agent web --port <临时端口>`，以轮询 `httpx.get` 等待服务；断言：

```python
assert root.status_code == 200
assert "<div id=\"root\">" in root.text
assert api.status_code == 404
```

在 `finally` 中 `terminate()`，超时后 `kill()`，并读取进程输出；任何失败信息不得包含 Provider 凭据。

- [ ] **步骤 4：运行绿灯与完整发布链。**

运行：`cd web; npm.cmd ci; npm.cmd test -- --run; npm.cmd run build; cd ..; $env:PYTHONPATH="src;."; .\.venv\Scripts\python.exe scripts/prepare_web_package.py; .\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q; .\.venv\Scripts\python.exe -m build`

预期：前端测试/build、资源暂存、wheel 内容断言、干净 venv 安装、CLI help、HTTP `/` 与 `/api` 验收全部通过。

- [ ] **步骤 5：提交。**

```powershell
git add tests/integration/test_package_install.py
git commit -m "test: verify clean wheel installation serves web ui"
```

### Task 4：发布入口、CI 与中文交付文档

**文件：**

- 修改：`Makefile`、`.github/workflows/ci.yml`、`.gitlab-ci.yml`
- 修改：`README.md`、`AGENT_LOG.md`、`SPEC_PROCESS.md`

**接口：**

- 产生：`make package`，顺序为 `web` 测试/build、资源暂存、`python -m build`、wheel 安装验收。
- 产生：GitHub/GitLab 同等发布链，默认不运行真实 Provider E2E。

- [ ] **步骤 1：写失败测试。**

```python
def test_ci_and_makefile_run_web_build_before_python_package() -> None:
    makefile = REPO_ROOT.joinpath("Makefile").read_text(encoding="utf-8")
    github = REPO_ROOT.joinpath(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "package:" in makefile
    assert "prepare_web_package.py" in makefile
    assert github.index("npm run build") < github.index("python -m build")
```

- [ ] **步骤 2：运行红灯。**

运行：`$env:PYTHONPATH="src;."; .\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q`

预期：`make package` 不存在，且 CI 当前在 Python 打包之后才运行前端 build。

- [ ] **步骤 3：实现统一发布入口和文档。**

```make
package:
	cd web && npm ci && npm test -- --run && npm run build
	python scripts/prepare_web_package.py
	python -m build
	python -m pytest tests/integration/test_package_install.py -q
```

调整 GitHub Actions 和 GitLab CI 以先安装 Node 依赖、运行 Vitest/Vite build、执行资源暂存，再执行 Python verify、build 和 wheel 验收。README 说明 `make package` 为发布入口及其 Node 前置条件；过程文档记录实际红绿命令、警告和干净安装结果。

- [ ] **步骤 4：运行最终验证。**

运行：`make package; $env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest -q; .\.venv\Scripts\ruff.exe check .; .\.venv\Scripts\mypy.exe src`

预期：发布链、全量 Python 测试、Ruff 和 Mypy 通过；真实 Provider E2E 仍保持默认跳过。

- [ ] **步骤 5：提交。**

```powershell
git add Makefile .github/workflows/ci.yml .gitlab-ci.yml README.md AGENT_LOG.md SPEC_PROCESS.md tests/integration/test_package_install.py
git commit -m "ci: verify packaged web ui release workflow"
```

## 计划自检

- 规格覆盖：Task 1 实现显式前端资源暂存与包数据；Task 2 实现包内优先资源解析、SPA/API 路由与路径边界；Task 3 覆盖 wheel 的干净 venv 安装和 HTTP 运行时；Task 4 固化 Makefile、两套 CI 和中文交付记录。
- 接口一致性：所有任务使用相同的 `prepare_web_package(repo_root)`、`static_dist_path()`、`mount_web_assets(app)`、`code_agent/web_dist` 和 `make package` 名称。
- 占位检查：计划不包含禁止的占位语、模糊实现步骤或未定义接口。
