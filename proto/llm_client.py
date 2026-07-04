"""Pluggable LLM client interface -- lets `proto/pipeline.py` and
`proto/debate_local.py` run against a real Ollama instance or a scripted fake
for tests, without the orchestration logic knowing which."""
from __future__ import annotations

from typing import Callable, Protocol


class LLMClient(Protocol):
    def complete(self, prompt: str, *, model: str, system: str | None = None, temperature: float = 0.7) -> str:
        ...


class OllamaClient:
    """Real client -- talks to a local Ollama instance."""

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, prompt: str, *, model: str, system: str | None = None, temperature: float = 0.7) -> str:
        import requests  # lazy import: only needed for real execution, not tests

        payload = {
            "model": model,
            "prompt": prompt,
            "system": system or "",
            "options": {"temperature": temperature},
            "stream": False,
        }
        response = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()["response"]


class FakeLLMClient:
    """Scripted client for tests: returns responses from a queue (by call
    order) or from a custom responder callback for tests that need the
    response to depend on the prompt."""

    def __init__(
        self,
        responses: list[str] | None = None,
        responder: Callable[[str, str, str | None], str] | None = None,
    ) -> None:
        self._queue = list(responses) if responses else []
        self._responder = responder
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, model: str, system: str | None = None, temperature: float = 0.7) -> str:
        self.calls.append({"prompt": prompt, "model": model, "system": system, "temperature": temperature})
        if self._responder is not None:
            return self._responder(prompt, model, system)
        if self._queue:
            return self._queue.pop(0)
        return ""
