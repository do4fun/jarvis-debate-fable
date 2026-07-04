"""Checkpoint/resume for the debate pipeline (v4, feature 9).

A checkpoint captures enough state to resume a pipeline run at the exact
step it was interrupted on, instead of restarting from step [1]. One file
per session, overwritten atomically after every LLM call -- critical given
the corpus-scale runs run on CPU (v4 0.7 / v3 correction F4).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_SESSIONS_DIR = Path("results/sessions")


@dataclass
class Checkpoint:
    session_id: str
    step: str
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "step": self.step, "state": self.state}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        return cls(session_id=data["session_id"], step=data["step"], state=data.get("state", {}))


class CheckpointStore:
    """File-based checkpoint persistence, one JSON file per session."""

    def __init__(self, sessions_dir: Path | str = DEFAULT_SESSIONS_DIR) -> None:
        self.sessions_dir = Path(sessions_dir)

    def _path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.checkpoint.json"

    def save(self, session_id: str, step: str, state: dict[str, Any]) -> Checkpoint:
        checkpoint = Checkpoint(session_id=session_id, step=step, state=state)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(session_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)  # atomic on POSIX and Windows: never leaves a half-written checkpoint
        return checkpoint

    def load(self, session_id: str) -> Checkpoint | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint.from_dict(data)

    def exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()

    def clear(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
