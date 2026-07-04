"""Session logger -- one JSON per full pipeline run (v4, feature 10):
`results/sessions/{session_id}_full.json`, in addition to the per-debate log
(v3, 0.5)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SESSIONS_DIR = Path("results/sessions")


@dataclass
class SessionLogger:
    session_id: str
    sessions_dir: Path = DEFAULT_SESSIONS_DIR
    steps: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def log_step(self, step: str, **data: Any) -> None:
        self.steps.append({"step": step, "logged_at": datetime.now(timezone.utc).isoformat(), **data})

    def to_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "started_at": self.started_at, "steps": self.steps}

    def write(self) -> Path:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self.sessions_dir / f"{self.session_id}_full.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
