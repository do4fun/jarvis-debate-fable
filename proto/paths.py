"""Guard for turning caller-supplied IDs (session_id, chunk_id, ...) into
filesystem path components safely.

These IDs are currently developer-controlled prototype strings or
`uuid.uuid4()` defaults, so there is no live attacker-controlled input today.
But once real corpus content is wired in (`datasets/facts/`, `corpus/raw/`
at the ~300+ resource scale the plan targets), an ID ever derived from
crawled data (a URL slug, a filename) could contain a path separator -- and
`Path(dir) / f"{id}..."` would happily write outside `dir`. Validate once,
here, rather than trusting every call site that builds a path from an ID.
"""
from __future__ import annotations

import re

_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class UnsafeIdentifierError(ValueError):
    """Raised when a caller-supplied ID isn't safe to use as a path component."""


def safe_id(value: str) -> str:
    if not value or value in (".", "..") or not _SAFE_ID_PATTERN.match(value):
        raise UnsafeIdentifierError(f"unsafe identifier for use as a filename component: {value!r}")
    return value
