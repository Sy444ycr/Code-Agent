import time

from fastapi.testclient import TestClient

from code_agent.api.app import create_app


def test_task_artifacts_return_report_verification_and_diff(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "complete",
                "mock_decisions": [{"action": "complete", "completion_message": "done"}],
            },
        )
        task_id = response.json()["id"]
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if client.get(f"/api/tasks/{task_id}").json()["status"] == "succeeded":
                break
            time.sleep(0.01)
        report = client.get(f"/api/tasks/{task_id}/report")
        diff = client.get(f"/api/tasks/{task_id}/diff")

    assert report.status_code == 200
    assert report.json()["status"] == "succeeded"
    assert report.json()["report"] == "done"
    assert isinstance(report.json()["verification"], list)
    assert diff.status_code == 200
    assert "diff" in diff.json()
