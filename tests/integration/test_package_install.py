from __future__ import annotations

import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import httpx
import pytest

from scripts.prepare_web_package import WebPackagePreparationError, prepare_web_package

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST_TIMEOUT_SECONDS = 10


def run(python: Path | str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(python), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def run_code_agent(venv_python: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(venv_python.parent / "code-agent.exe"), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def build_project_wheel(repo_root: Path) -> Path:
    prepare_web_package(repo_root)
    result = run(sys.executable, "-m", "build", "--wheel")
    assert result.returncode == 0, result.stderr
    wheels = sorted((repo_root / "dist").glob("code_agent-*.whl"), key=Path.stat)
    assert wheels, "wheel build did not create dist/code_agent-*.whl"
    return wheels[-1]


def create_venv(path: Path) -> Path:
    result = run(sys.executable, "-m", "venv", str(path))
    assert result.returncode == 0, result.stderr
    return path / "Scripts" / "python.exe"


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


def test_built_wheel_installs_with_web_assets_in_clean_venv(tmp_path: Path) -> None:
    wheel = build_project_wheel(REPO_ROOT)
    with zipfile.ZipFile(wheel) as archive:
        assert "code_agent/web_dist/index.html" in archive.namelist()

    venv_python = create_venv(tmp_path / "venv")
    install_wheel(venv_python, wheel)

    assert run(venv_python, "-m", "code_agent.web_assets", "--check").returncode == 0
    assert run_code_agent(venv_python, "--help").returncode == 0
    assert run_code_agent(venv_python, "web", "--help").returncode == 0

    port = available_port()
    process = subprocess.Popen(
        [str(venv_python.parent / "code-agent.exe"), "web", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        root = wait_for_web_server(process, f"http://127.0.0.1:{port}/")
        api = httpx.get(f"http://127.0.0.1:{port}/api", timeout=REQUEST_TIMEOUT_SECONDS)
        assert root.status_code == 200
        assert '<div id="root">' in root.text
        assert api.status_code == 404
    finally:
        stop_process(process)
