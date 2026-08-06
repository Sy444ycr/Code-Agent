from __future__ import annotations

from pydantic import BaseModel


class AppConfig(BaseModel):
    api_base_url: str = "http://127.0.0.1:8000"
    state_path: str = ".code-agent/state.db"
