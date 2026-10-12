"""Minimal client for a local Ollama server (standard library only).

Every URL is checked against the sandbox before a request is made, so by
default only the local machine can be contacted.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .sandbox import Sandbox

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaError(RuntimeError):
    """The Ollama server is unreachable or returned an error."""


@dataclass
class GenerateResult:
    text: str
    seconds: float  # compute time, excluding model loading
    prompt_tokens: int
    completion_tokens: int
    model: str


@dataclass
class ModelInfo:
    name: str
    size_gb: float
    parameter_size: str
    capabilities: list[str]


class OllamaClient:
    def __init__(self, host: str, sandbox: Sandbox, timeout: float = 300.0):
        sandbox.check_url(host)
        self.host = host.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.host}{path}"
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise OllamaError(f"{url}: HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise OllamaError(
                f"cannot reach Ollama at {self.host} ({exc}). Is it running? Try: ollama serve"
            ) from None

    def version(self) -> str:
        return self._request("/api/version").get("version", "unknown")

    def list_models(self) -> list[ModelInfo]:
        models = []
        for item in self._request("/api/tags").get("models", []):
            details = item.get("details") or {}
            models.append(
                ModelInfo(
                    name=item["name"],
                    size_gb=item.get("size", 0) / 1e9,
                    parameter_size=details.get("parameter_size", "?"),
                    capabilities=item.get("capabilities") or ["completion"],
                )
            )
        return models

    def generate(
        self,
        model: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 256,
        think: bool | None = False,
    ) -> GenerateResult:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if think is not None:
            payload["think"] = think
        started = time.monotonic()
        data = self._request("/api/generate", payload)
        wall = time.monotonic() - started
        total = data.get("total_duration")
        seconds = (total - data.get("load_duration", 0)) / 1e9 if total else wall
        return GenerateResult(
            text=strip_thinking(data.get("response", "")),
            seconds=max(seconds, 0.0),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            model=model,
        )


def strip_thinking(text: str) -> str:
    """Drop ``<think>...</think>`` blocks that some reasoning models emit."""
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text:  # opening tag was cut off by the template
        text = text.split("</think>", 1)[1]
    return text.strip()


def discover_models(client: OllamaClient, wanted: list[str], max_size_gb: float) -> list[ModelInfo]:
    """Resolve the models to use, smallest first.

    ``wanted`` lists model names explicitly; when empty, every installed model
    that can generate text and fits within ``max_size_gb`` is used.
    """
    installed = {m.name: m for m in client.list_models()}
    if wanted:
        missing = [name for name in wanted if name not in installed]
        if missing:
            raise OllamaError(f"model(s) not installed: {missing}. Install with: ollama pull <name>")
        chosen = [installed[name] for name in wanted]
    else:
        chosen = [
            m for m in installed.values() if "completion" in m.capabilities and m.size_gb <= max_size_gb
        ]
    if not chosen:
        raise OllamaError(
            f"no usable models (installed: {sorted(installed)}, size limit {max_size_gb} GB). "
            "Install one, e.g.: ollama pull qwen2.5:3b"
        )
    return sorted(chosen, key=lambda m: m.size_gb)
