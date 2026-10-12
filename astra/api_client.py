"""Client for OpenAI-compatible chat APIs (DeepSeek by default) with a hard spending cap.

API calls cost real money. Every call is priced from the token usage the API
reports, added to a running total, and refused in advance if its worst case
could push the total past ``sandbox.max_api_spend_usd``. The key is read from
an environment variable and never written anywhere.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .config import APIConfig, APIModelSpec
from .ollama_client import GenerateResult
from .sandbox import Sandbox, SandboxViolation


class APIError(RuntimeError):
    """The API is unreachable, rejected the key or returned an error."""


class APIClient:
    RETRIES = 3

    def __init__(self, cfg: APIConfig, sandbox: Sandbox, api_key: str | None = None):
        sandbox.check_url(cfg.base_url)
        key = api_key or os.environ.get(cfg.api_key_env, "")
        if not key:
            raise APIError(f"set the {cfg.api_key_env} environment variable to your API key")
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")
        self.timeout = sandbox.cfg.request_timeout
        self.limit_usd = sandbox.cfg.max_api_spend_usd
        self.prices: dict[str, APIModelSpec] = {m.name: m for m in cfg.models}
        self.spent_usd = 0.0
        self.calls = 0
        self._key = key

    def serves(self, model: str) -> bool:
        return model in self.prices

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"},
            method="POST",
        )
        for attempt in range(self.RETRIES):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:300]
                if exc.code in (429, 500, 502, 503) and attempt + 1 < self.RETRIES:
                    time.sleep(2 ** attempt)
                    continue
                raise APIError(f"{self.base_url}{path}: HTTP {exc.code}: {detail}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if attempt + 1 < self.RETRIES:
                    time.sleep(2 ** attempt)
                    continue
                raise APIError(f"cannot reach {self.base_url} ({exc})") from None
        raise APIError("unreachable")  # pragma: no cover

    def generate(
        self,
        model: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 256,
        think: bool | None = False,
        effort: float = 1.0,
    ) -> GenerateResult:
        """One chat completion. ``effort`` >= 1 turns on the model's thinking mode."""
        price = self.prices[model]
        thinking = effort >= 1.0
        max_tokens = num_predict + (self.cfg.thinking_tokens if thinking else 0)
        worst_case = (len(prompt) * price.input_usd_per_mtok + max_tokens * price.output_usd_per_mtok) / 1e6
        if self.spent_usd + worst_case > self.limit_usd:
            raise SandboxViolation(
                f"API spending cap reached: spent ${self.spent_usd:.4f} of "
                f"sandbox.max_api_spend_usd=${self.limit_usd:g}"
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "thinking": {"type": "enabled" if thinking else "disabled"},
        }
        if thinking:
            payload["reasoning_effort"] = "high" if effort >= 1.6 else "low"
        started = time.monotonic()
        data = self._post("/chat/completions", payload)
        seconds = time.monotonic() - started

        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        cached = usage.get("prompt_cache_hit_tokens", 0)
        uncached = usage.get("prompt_cache_miss_tokens", prompt_tokens - cached)
        completion = usage.get("completion_tokens", 0)
        cost = (
            cached * price.cached_input_usd_per_mtok
            + uncached * price.input_usd_per_mtok
            + completion * price.output_usd_per_mtok
        ) / 1e6
        self.spent_usd += cost
        self.calls += 1
        message = (data.get("choices") or [{}])[0].get("message") or {}
        return GenerateResult(
            text=(message.get("content") or "").strip(),
            seconds=seconds,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion,
            model=model,
            cost_usd=cost,
        )


class ModelRouter:
    """Sends each model name to whichever backend serves it: the API or local Ollama."""

    def __init__(self, local: Any | None = None, api: APIClient | None = None):
        self.local = local
        self.api = api

    def generate(self, model: str, prompt: str, **options: Any) -> GenerateResult:
        if self.api is not None and self.api.serves(model):
            return self.api.generate(model, prompt, **options)
        if self.local is None:
            raise APIError(f"no backend serves model {model!r}")
        return self.local.generate(model, prompt, **options)

    def list_models(self) -> list:
        return self.local.list_models() if self.local is not None else []
