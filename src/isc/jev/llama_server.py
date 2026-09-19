"""Thin httpx client over the llama-server endpoints the JEV backend needs.

Only /health, /props, /apply-template, /tokenize, /completion. No sampling, no chat
completions: Simple Jev never generates an answer, it reads the next-token distribution at a
forced boundary (see ``llamacpp_backend.py``).
"""

from __future__ import annotations

import time
from typing import Any

import httpx


class LlamaServerError(RuntimeError):
    pass


class LlamaServerClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 600.0,
        retries: int = 5,
        retry_delay_s: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.retry_delay_s = retry_delay_s
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            transport=transport,
        )

    def healthy(self) -> bool:
        try:
            return self._client.get("/health", timeout=5.0).status_code == 200
        except httpx.HTTPError:
            return False

    def props(self) -> dict[str, Any]:
        r = self._client.get("/props")
        r.raise_for_status()
        return r.json()

    def apply_template(self, messages: list[dict], chat_template_kwargs: dict | None = None) -> str:
        body: dict[str, Any] = {"messages": messages}
        if chat_template_kwargs:
            body["chat_template_kwargs"] = chat_template_kwargs
        r = self._post("/apply-template", body)
        return r["prompt"]

    def tokenize(
        self, text: str, *, add_special: bool = False, parse_special: bool = True
    ) -> list[int]:
        r = self._post(
            "/tokenize",
            {"content": text, "add_special": add_special, "parse_special": parse_special},
        )
        return list(r.get("tokens", []))

    def completion(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/completion", body)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        delay = self.retry_delay_s
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self._client.post(path, json=body)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                raise LlamaServerError(f"{path}: {exc}") from exc
            if r.status_code == 503 and attempt < self.retries:
                retry_after = r.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else delay)
                delay = min(delay * 2, 30.0)
                continue
            if r.status_code >= 400:
                raise LlamaServerError(f"{path} -> HTTP {r.status_code}: {r.text[:500]}")
            return r.json()
        raise LlamaServerError(f"{path}: exhausted retries") from last_exc
