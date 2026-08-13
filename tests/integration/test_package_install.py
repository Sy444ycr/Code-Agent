from __future__ import annotations

import socket
import subprocess
import sys
import tarfile
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


def build_project_artifacts(repo_root: Path, artifact_output: Path) -> tuple[Path, Path]:
    frontend = repo_root / "web"
    install = run(npm_executable(), "ci", cwd=frontend)
    assert install.returncode == 0, install.stderr
    build = run(npm_executable(), "run", "build", cwd=frontend)
    assert build.returncode == 0, build.stderr
    prepare_web_package(repo_root)
    result = run(sys.executable, "-m", "build", "--outdir", str(artifact_output))
    assert result.returncode == 0, result.stderr
    wheels = list(artifact_output.glob("code_agent-*.whl"))
    assert len(wheels) == 1, "wheel build did not create exactly one wheel"
    sdists = list(artifact_output.glob("code_agent-*.tar.gz"))
    assert len(sdists) == 1, "sdist build did not create exactly one source archive"
    return wheels[0], sdists[0]


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


def make_recipe(makefile: str, target: str) -> list[str]:
    target_marker = f"{target}:"
    lines = makefile.splitlines()
    start = lines.index(target_marker) + 1
    recipe: list[str] = []
    for line in lines[start:]:
        if line.startswith("\t"):
            recipe.append(line.removeprefix("\t"))
        elif line:
            break
    return recipe


PACKAGE_COMMANDS = [
    "cd web && npm ci && npm test -- --run && npm run build",
    "python scripts/prepare_web_package.py",
    "python -m build",
    "python -m pytest tests/integration/test_package_install.py -q",
]

CI_PACKAGE_COMMANDS = [
    "python scripts/prepare_web_package.py",
    "make verify",
    "python -m build",
    "python -m pytest tests/integration/test_package_install.py -q",
]


def normalized_commands(commands: list[str]) -> list[str]:
    return [" ".join(command.split()) for command in commands]


def test_prepare_web_package_rejects_missing_frontend_dist(tmp_path: Path) -> None:
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    with pytest.raises(WebPackagePreparationError) as error:
        prepare_web_package(tmp_path)

    assert str(error.value) == "WebUI 构建产物缺失，请先运行 npm run build。"


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


def test_prepare_web_package_rejects_missing_referenced_asset(tmp_path: Path) -> None:
    source = tmp_path / "web" / "dist"
    source.mkdir(parents=True)
    (source / "index.html").write_text(
        '<script src="/assets/missing.js"></script>', encoding="utf-8"
    )
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    with pytest.raises(WebPackagePreparationError) as error:
        prepare_web_package(tmp_path)

    assert str(error.value) == "WebUI 构建产物缺失，请先运行 npm run build。"


def test_prepare_web_package_rejects_missing_nested_asset_reference(tmp_path: Path) -> None:
    source = tmp_path / "web" / "dist" / "assets"
    source.mkdir(parents=True)
    (source.parent / "index.html").write_text(
        '<script src="/assets/app.js"></script>', encoding="utf-8"
    )
    (source / "app.js").write_text('import "./missing-chunk.js"', encoding="utf-8")
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    with pytest.raises(WebPackagePreparationError) as error:
        prepare_web_package(tmp_path)

    assert str(error.value) == "WebUI 构建产物缺失，请先运行 npm run build。"


def test_prepare_web_package_script_stages_assets(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "prepare_web_package.py"
    script.parent.mkdir()
    script.write_text(
        REPO_ROOT.joinpath("scripts", "prepare_web_package.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    source = tmp_path / "web" / "dist" / "assets"
    source.mkdir(parents=True)
    (source.parent / "index.html").write_text(
        '<script src="/assets/app.js"></script>', encoding="utf-8"
    )
    (source / "app.js").write_text("console.log('WebUI')", encoding="utf-8")
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    result = run(sys.executable, str(script), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "src" / "code_agent" / "web_dist" / "assets" / "app.js").is_file()


def test_prepare_web_package_script_reports_missing_assets_exactly(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "prepare_web_package.py"
    script.parent.mkdir()
    script.write_text(
        REPO_ROOT.joinpath("scripts", "prepare_web_package.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    result = run(sys.executable, str(script), cwd=tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "WebUI 构建产物缺失，请先运行 npm run build。\n"


def test_ci_and_makefile_run_web_build_before_python_package() -> None:
    makefile = REPO_ROOT.joinpath("Makefile").read_text(encoding="utf-8")
    github = yaml.safe_load(
        REPO_ROOT.joinpath(".github", "workflows", "ci.yml").read_text(encoding="utf-8")
    )
    gitlab = yaml.safe_load(REPO_ROOT.joinpath(".gitlab-ci.yml").read_text(encoding="utf-8"))

    assert normalized_commands(make_recipe(makefile, "package")) == PACKAGE_COMMANDS

    github_steps = github["jobs"]["test"]["steps"]
    github_commands = [step["run"] for step in github_steps if "run" in step]
    assert normalized_commands(github_commands) == [
        'pip install -e ".[dev]"',
        PACKAGE_COMMANDS[0],
        *CI_PACKAGE_COMMANDS,
    ]

    web_build = gitlab["web-build"]
    package = gitlab["package"]
    assert package["needs"] == [{"job": "web-build", "artifacts": True}]
    assert web_build["artifacts"]["paths"] == ["web/dist/"]
    assert package["image"] == "python:3.12-bookworm"
    assert "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -" in package["before_script"]
    assert "apt-get install -y nodejs make" in package["before_script"]
    assert normalized_commands(web_build["script"]) == [
        "cd web && npm ci && npm test -- --run && npm run build"
    ]
    assert normalized_commands(package["script"]) == [
        'pip install -e ".[dev]"',
        *CI_PACKAGE_COMMANDS,
    ]


def test_built_wheel_installs_with_web_assets_in_clean_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel, sdist = build_project_artifacts(REPO_ROOT, tmp_path / "package-output")
    with tarfile.open(sdist) as archive:
        archive_names = archive.getnames()
    assert any(name.endswith("src/code_agent/cli.py") for name in archive_names)
    assert any(name.endswith("src/code_agent/web_dist/index.html") for name in archive_names)
    with zipfile.ZipFile(wheel) as archive:
        assert "code_agent/web_dist/index.html" in archive.namelist()
        assert "code_agent/cli.py" in archive.namelist()

    sdist_source = tmp_path / "sdist-source"
    with tarfile.open(sdist) as archive:
        archive.extractall(sdist_source, filter="data")
    extracted_project = next(sdist_source.iterdir())
    rebuilt_output = tmp_path / "rebuilt-output"
    rebuilt = run(
        sys.executable, "-m", "build", "--outdir", str(rebuilt_output), cwd=extracted_project
    )
    assert rebuilt.returncode == 0, rebuilt.stderr
    rebuilt_wheel = next(rebuilt_output.glob("code_agent-*.whl"))
    with zipfile.ZipFile(rebuilt_wheel) as archive:
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
