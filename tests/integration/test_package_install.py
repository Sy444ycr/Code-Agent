from __future__ import annotations

import socket
import subprocess
import sys
import time
import zipfile
from os import environ
from os import name as os_name
from pathlib import Path
from re import findall

import httpx
import pytest
import yaml

from scripts.prepare_web_package import WebPackagePreparationError, prepare_web_package

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST_TIMEOUT_SECONDS = 10


def run(
    executable: Path | str,
    *arguments: str,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def npm_executable() -> str:
    return "npm.cmd" if os_name == "nt" else "npm"


def venv_executable(venv_path: Path, name: str) -> Path:
    scripts = "Scripts" if os_name == "nt" else "bin"
    suffix = ".exe" if os_name == "nt" else ""
    return venv_path / scripts / f"{name}{suffix}"


def installed_environment() -> dict[str, str]:
    environment = dict(environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    return environment


def run_code_agent(
    venv_python: Path, *arguments: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(venv_executable(venv_python.parent.parent, "code-agent")), *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def build_project_wheel(repo_root: Path, wheel_output: Path) -> Path:
    frontend = repo_root / "web"
    install = run(npm_executable(), "ci", cwd=frontend)
    assert install.returncode == 0, install.stderr
    build = run(npm_executable(), "run", "build", cwd=frontend)
    assert build.returncode == 0, build.stderr
    prepare_web_package(repo_root)
    result = run(sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_output))
    assert result.returncode == 0, result.stderr
    wheels = list(wheel_output.glob("code_agent-*.whl"))
    assert len(wheels) == 1, "wheel build did not create exactly one wheel"
    return wheels[0]


def create_venv(path: Path) -> Path:
    result = run(sys.executable, "-m", "venv", str(path))
    assert result.returncode == 0, result.stderr
    return venv_executable(path, "python")


def install_wheel(venv_python: Path, wheel: Path) -> None:
    result = run(venv_python, "-m", "pip", "install", str(wheel))
    assert result.returncode == 0, result.stderr


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_web_server(process: subprocess.Popen[str], url: str) -> httpx.Response:
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    last_error: httpx.HTTPError | None = None
    while time.monotonic() < deadline:
        if process_exited(process):
            pytest.fail("web server exited before responding")
        try:
            return httpx.get(url, timeout=0.5)
        except httpx.HTTPError as error:
            last_error = error
            time.sleep(0.1)
    pytest.fail(f"web server did not start within {REQUEST_TIMEOUT_SECONDS} seconds: {last_error}")


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    process.communicate(timeout=5)


def process_exited(process: subprocess.Popen[str]) -> bool:
    return process.poll() is not None


def static_asset_path(index_html: str) -> str:
    assets = findall(r'(?:src|href)="(/assets/[^"]+)"', index_html)
    assert assets, "built index.html does not reference a static asset"
    return assets[0]


def make_recipe(makefile: str, target: str) -> str:
    target_marker = f"{target}:"
    lines = makefile.splitlines()
    start = lines.index(target_marker) + 1
    recipe: list[str] = []
    for line in lines[start:]:
        if line.startswith("\t"):
            recipe.append(line.removeprefix("\t"))
        elif line:
            break
    return "\n".join(recipe)


def command_sequence(commands: list[str]) -> list[str]:
    return [
        "npm ci",
        "npm test -- --run",
        "npm run build",
        "python scripts/prepare_web_package.py",
        "python -m build",
        "python -m pytest tests/integration/test_package_install.py -q",
    ]


def assert_command_sequence(commands: list[str]) -> None:
    joined = "\n".join(commands)
    indexes = [joined.index(command) for command in command_sequence(commands)]
    assert indexes == sorted(indexes)


def test_prepare_web_package_rejects_missing_frontend_dist(tmp_path: Path) -> None:
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    with pytest.raises(WebPackagePreparationError, match="WebUI 构建产物缺失"):
        prepare_web_package(tmp_path)


def test_prepare_web_package_copies_frontend_dist(tmp_path: Path) -> None:
    source = tmp_path / "web" / "dist"
    source.mkdir(parents=True)
    (source / "index.html").write_text("<main>WebUI</main>", encoding="utf-8")
    (source / "assets").mkdir()
    (source / "assets" / "app.js").write_text("console.log('WebUI')", encoding="utf-8")
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    target = prepare_web_package(tmp_path)

    assert target == tmp_path / "src" / "code_agent" / "web_dist"
    assert (target / "index.html").read_text(encoding="utf-8") == "<main>WebUI</main>"
    assert (target / "assets" / "app.js").read_text(encoding="utf-8") == "console.log('WebUI')"


def test_ci_and_makefile_run_web_build_before_python_package() -> None:
    makefile = REPO_ROOT.joinpath("Makefile").read_text(encoding="utf-8")
    github = yaml.safe_load(
        REPO_ROOT.joinpath(".github", "workflows", "ci.yml").read_text(encoding="utf-8")
    )
    gitlab = yaml.safe_load(REPO_ROOT.joinpath(".gitlab-ci.yml").read_text(encoding="utf-8"))

    assert_command_sequence([make_recipe(makefile, "package")])

    github_steps = github["jobs"]["test"]["steps"]
    github_commands = [step["run"] for step in github_steps if "run" in step]
    assert_command_sequence(github_commands)

    web_build = gitlab["web-build"]
    package = gitlab["package"]
    assert package["needs"] == [{"job": "web-build", "artifacts": True}]
    assert web_build["artifacts"]["paths"] == ["web/dist/"]
    assert package["image"] == "python:3.12-bookworm"
    assert "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -" in package["before_script"]
    assert "apt-get install -y nodejs make" in package["before_script"]
    assert_command_sequence(web_build["script"] + package["script"])


def test_built_wheel_installs_with_web_assets_in_clean_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = build_project_wheel(REPO_ROOT, tmp_path / "wheel-output")
    with zipfile.ZipFile(wheel) as archive:
        assert "code_agent/web_dist/index.html" in archive.namelist()

    venv_python = create_venv(tmp_path / "venv")
    install_wheel(venv_python, wheel)
    shadow = tmp_path / "shadow" / "code_agent"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text("", encoding="utf-8")
    (shadow / "web_assets.py").write_text("print('shadowed')", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(shadow.parent))
    environment = installed_environment()

    assets_check = run(
        venv_python, "-m", "code_agent.web_assets", "--check", cwd=tmp_path, env=environment
    )
    assert assets_check.returncode == 0
    assert assets_check.stdout == "Web assets available\n"
    assert run_code_agent(venv_python, "--help", cwd=tmp_path, env=environment).returncode == 0
    web_help = run_code_agent(venv_python, "web", "--help", cwd=tmp_path, env=environment)
    assert web_help.returncode == 0

    port = available_port()
    process = subprocess.Popen(
        [str(venv_executable(venv_python.parent.parent, "code-agent")), "web", "--port", str(port)],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        root = wait_for_web_server(process, f"http://127.0.0.1:{port}/")
        static_asset = httpx.get(
            f"http://127.0.0.1:{port}{static_asset_path(root.text)}",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        spa_fallback = httpx.get(
            f"http://127.0.0.1:{port}/client/route", timeout=REQUEST_TIMEOUT_SECONDS
        )
        api = httpx.get(
            f"http://127.0.0.1:{port}/api/tasks/not-found", timeout=REQUEST_TIMEOUT_SECONDS
        )
        assert root.status_code == 200
        assert '<div id="root">' in root.text
        assert static_asset.status_code == 200
        assert spa_fallback.status_code == 200
        assert spa_fallback.text == root.text
        assert api.status_code == 404
    finally:
        stop_process(process)
