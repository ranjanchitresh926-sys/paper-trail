from __future__ import annotations

from typing import Callable, Optional

import requests


class OllamaLLM:
    """Local model through Ollama. Check the exact tag with `ollama list`."""

    def __init__(self, model: str = "gemma4:e4b", host: str = "http://localhost:11434",
                 temperature: float = 0.7, think: bool = False, keep_alive: str = "30m"):
        # think=False: measured 2-3 s per reply instead of 30-120 s with thinking left on.
        # keep_alive keeps the model in GPU memory so later calls skip the 30-45 s load.
        self.model, self.host, self.temperature = model, host, temperature
        self.think, self.keep_alive = think, keep_alive

    def chat(self, system: str, user: str, temperature: Optional[float] = None, format=None) -> str:
        """`format` may be "json" or a JSON schema dict (Ollama structured outputs)."""
        body = {
            "model": self.model,
            "stream": False,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": self.temperature if temperature is None else temperature},
        }
        if format is not None:
            body["format"] = format
        r = requests.post(f"{self.host}/api/chat", json=body, timeout=300)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


class FakeLLM:
    """Scripted stand-in for tests."""

    def __init__(self, fn: Callable[[str, str], str]):
        self.fn = fn

    def chat(self, system: str, user: str, temperature: Optional[float] = None, format=None) -> str:
        return self.fn(system, user)
