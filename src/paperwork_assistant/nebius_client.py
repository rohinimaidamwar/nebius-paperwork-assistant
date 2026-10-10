"""Minimal client for Nebius Token Factory's OpenAI-compatible API.

Design notes
- Endpoint: {base_url}/chat/completions with `Authorization: Bearer <key>`.
- NVIDIA Nemotron models on Token Factory may be reasoning models. A public issue
  (nebius/api #211, May 2026) reports they can return the answer in
  `reasoning_content` with empty `content`, and that native tool calls can fail.
  So this client (1) gives a generous token budget, (2) strips <think> blocks,
  (3) falls back to `reasoning_content` when `content` is empty, (4) raises a clear
  error when the reply was cut off, and (5) the app never relies on native function
  calling. It asks for JSON in plain text instead.
  Re-check this against the current docs; the behaviour may have changed.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .jsonutil import strip_reasoning

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
# Public listings show the Token Factory id as "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B".
# Run `paperwork models` with your key to confirm the exact id before relying on it.
DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
DEFAULT_MAX_TOKENS = 4000

class NebiusError(RuntimeError):
    pass

@dataclass
class Reply:
    text: str
    model: str
    used_reasoning_fallback: bool = False
    finish_reason: str | None = None

class NebiusClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None,
                 timeout: float = 120.0, max_retries: int = 3, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        self.api_key = api_key or os.getenv("NEBIUS_API_KEY", "")
        if not self.api_key:
            raise NebiusError("NEBIUS_API_KEY is not set. Create a key in the Nebius Token Factory console.")
        self.base_url = (base_url or os.getenv("NEBIUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/") + "/"
        self.model = model or os.getenv("NEBIUS_MODEL") or DEFAULT_MODEL
        self.max_retries = max_retries
        self.sleep = sleep
        self.http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport,
                                 headers={"Authorization": f"Bearer {self.api_key}"})

    def _request(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                r = self.http.request(method, path, **kw)
            except httpx.TransportError as e:
                last = e
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    last = NebiusError(f"HTTP {r.status_code}: {r.text[:200]}")
                elif r.status_code >= 400:
                    raise NebiusError(f"HTTP {r.status_code}: {r.text[:300]}")
                else:
                    try:
                        return r.json()
                    except ValueError as e:
                        raise NebiusError(f"Response was not valid JSON: {r.text[:200]}") from e
            if attempt < self.max_retries - 1:
                self.sleep(min(2 ** attempt, 8))
        raise NebiusError(f"Request failed after {self.max_retries} attempts: {last}")

    def list_models(self) -> list[str]:
        data = self._request("GET", "models")
        return sorted(m["id"] for m in data.get("data", []))

    def chat(self, messages: list[dict[str, str]], max_tokens: int = DEFAULT_MAX_TOKENS,
             temperature: float = 0.2) -> Reply:
        data = self._request("POST", "chat/completions", json={
            "model": self.model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
        })
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise NebiusError(f"Unexpected response shape: {str(data)[:300]}") from e

        finish = choice.get("finish_reason")
        content = strip_reasoning(message.get("content") or "")
        fallback = False
        if not content:
            reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
            if finish == "length" and not reasoning.strip().endswith("}"):
                raise NebiusError("The model ran out of tokens while reasoning. Increase max_tokens.")
            content, fallback = strip_reasoning(reasoning), True
        if not content:
            raise NebiusError("The model returned an empty reply.")
        if finish == "length" and not content.rstrip().endswith("}"):
            raise NebiusError("The reply was cut off because the token limit was reached. Increase max_tokens.")
        return Reply(text=content, model=data.get("model", self.model),
                     used_reasoning_fallback=fallback, finish_reason=finish)
