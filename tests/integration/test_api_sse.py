from fastapi.testclient import TestClient

from code_agent.api.app import create_app


def test_create_task_returns_task_id(tmp_path) -> None:
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    response = client.post(
        "/api/tasks",
        json={"workspace": str(tmp_path), "goal": "inspect", "mode": "plan", "provider": "mock"},
    )
    assert response.status_code == 201
    assert response.json()["id"]
    assert response.json()["status"] in {"pending", "running", "needs_review"}


def test_events_endpoint_replays_ordered_events(tmp_path) -> None:
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    task_id = client.post(
        "/api/tasks", json={"workspace": str(tmp_path), "goal": "inspect"}
    ).json()["id"]
    response = client.get(f"/api/tasks/{task_id}/events?after=0")
    assert response.status_code == 200
    assert isinstance(response.json()["events"], list)
