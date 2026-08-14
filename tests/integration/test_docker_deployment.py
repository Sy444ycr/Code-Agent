from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]


def test_deployment_configuration_contract() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert "FROM node:22-bookworm AS web-build" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "FROM python:3.12-bookworm" in dockerfile
    assert "python scripts/prepare_web_package.py" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert 'CMD ["code-agent", "web", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile
    assert "USER code-agent" in dockerfile

    service = compose["services"]["code-agent"]
    assert service["ports"] == ["80:8000"]
    assert service["restart"] == "unless-stopped"
    assert service["environment"]["CODE_AGENT_STATE_PATH"] == "/var/lib/code-agent/state.db"
    assert "code-agent-state:/var/lib/code-agent" in service["volumes"]
    assert service["healthcheck"]["test"] == ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/')"]
    assert compose["volumes"] == {"code-agent-state": {}}


def test_app_uses_state_path_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "state.db"
    monkeypatch.setenv("CODE_AGENT_STATE_PATH", str(state_path))

    from code_agent.api.app import create_app

    app = create_app()
    try:
        assert app.state.store.path == state_path
    finally:
        app.state.manager.shutdown()


def test_compose_serves_webui_and_preserves_state(tmp_path: Path) -> None:
    if not os.environ.get("CODE_AGENT_RUN_DOCKER_E2E"):
        pytest.skip("Docker E2E 未显式启用。")
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI 不可用，跳过容器运行验收。")

    project = f"task26-{os.getpid()}"
    host_port = 18000 + (os.getpid() % 1000)
    override = tmp_path / "docker-compose.override.yml"
    override.write_text(
        "services:\n  code-agent:\n    ports:\n      - "
        f'"{host_port}:8000"\n',
        encoding="utf-8",
    )
    base = [
        docker,
        "compose",
        "-p",
        project,
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(override),
    ]

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*base, *args], cwd=ROOT, text=True, capture_output=True, check=False
        )

    def request(
        path: str, method: str = "GET", payload: dict[str, object] | None = None
    ) -> dict[str, object]:
        data = json.dumps(payload).encode() if payload is not None else None
        request_object = urllib.request.Request(
            f"http://127.0.0.1:{host_port}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request_object, timeout=5) as response:
            return json.loads(response.read())

    try:
        started = run("up", "-d", "--build")
        if started.returncode != 0:
            pytest.fail(f"Docker Compose 启动失败：\n{started.stdout}\n{started.stderr}")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                request("/")
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2)
        else:
            logs = run("logs", "--no-color")
            pytest.fail(f"服务未就绪：\n{logs.stdout}\n{logs.stderr}")

        created = request(
            "/api/tasks",
            "POST",
            {
                "workspace": "/app",
                "goal": "Docker 持久化验收",
                "provider": "mock",
                "mock_decisions": [{"action": "complete", "completion_message": "done"}],
            },
        )
        task_id = str(created["id"])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            detail = request(f"/api/tasks/{task_id}")
            if detail["status"] == "succeeded":
                break
            time.sleep(1)
        else:
            pytest.fail(f"任务未完成：{detail}")

        restarted = run("restart", "code-agent")
        assert restarted.returncode == 0, restarted.stderr
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                persisted = request(f"/api/tasks/{task_id}")
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(1)
        else:
            pytest.fail("容器重启后服务未恢复。")
        assert persisted["id"] == task_id
        assert persisted["status"] == "succeeded"
        assert persisted["goal"] == "Docker 持久化验收"
    finally:
        run("down", "-v")
