from __future__ import annotations

from pathlib import Path

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
