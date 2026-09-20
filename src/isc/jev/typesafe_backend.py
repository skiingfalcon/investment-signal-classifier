"""A ``RawJevClient`` against TypeSafe's hosted Jev, as the control for the local llama.cpp path.

The local backend (``llamacpp_backend.py``) reads label logits out of an open-weight qwen3.8-27b
through a prompt template this project renders itself -- a re-implementation of the Jev
*interface*, not the Jev *model*. This client talks to the real thing instead, so a disagreement
between the two backends on identical facts/questions/policy isolates the backend as the variable,
rather than leaving "was it qwen, the prompt rendering, or the questions" unanswered.

Mirrors jev-email-cascade's ``src/jev_email_cascade/jev_client.py`` byte-for-byte on the wire
contract: same ``{model, state, questions}`` -> ``{model, answers, usage}`` envelope, same
TypeSafe-direct-over-OpenRouter precedence, same retry/backoff, same published per-input-token
price used only when a response omits ``usage.cost``. Implements ``isc.backends.RawJevClient``
(``classify(request) -> envelope``), so it drops into the existing ``JevBackend`` adapter
unchanged -- everything from ``policy.py`` onward is identical for both backends.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from isc.config import Settings

RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}

# Published OpenRouter price for typesafe/jev-1.13; output is free. Used only as a fallback when
# a response's usage omits `cost` (observed: TypeSafe direct may not report it; OpenRouter did on
# every row of jev-email-cascade's live run).
JEV_PRICE_PER_INPUT_TOKEN = 0.042 / 1_000_000


class MissingKeyError(RuntimeError):
    """Neither TYPESAFE_API_KEY nor OPENROUTER_API_KEY is set."""


class TypesafeJevClient:
    """Implements ``isc.backends.RawJevClient`` against TypeSafe's hosted Jev."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        model: str,
        route: str,
        timeout_s: float = 60.0,
        retries: int = 5,
        retry_delay_s: float = 1.0,
        max_retry_delay_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if not api_key:
            raise MissingKeyError("empty API key")
        self.url = url
        self.model = model
        self.route = route
        self.retries = retries
        self.retry_delay_s = retry_delay_s
        self.max_retry_delay_s = max_retry_delay_s
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_s, connect=10.0), transport=transport, headers=headers
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.BaseTransport | None = None
    ) -> TypesafeJevClient:
        """TypeSafe direct takes precedence over OpenRouter when both keys are set, so a stray
        OPENROUTER_API_KEY left in the shell by another tool cannot silently reroute and re-bill.
        """
        if settings.typesafe_api_key:
            return cls(
                url=settings.typesafe_systemone_url,
                api_key=settings.typesafe_api_key,
                model=settings.typesafe_model,
                route="typesafe",
                timeout_s=settings.timeout_s,
                transport=transport,
            )
        if settings.openrouter_api_key:
            return cls(
                url=settings.jev_decisions_url,
                api_key=settings.openrouter_api_key,
                model=settings.openrouter_jev_model,
                route="openrouter",
                timeout_s=settings.timeout_s,
                transport=transport,
                # Attribution headers OpenRouter recognises; harmless if ignored.
                extra_headers={
                    "HTTP-Referer": "https://github.com/skiingfalcon/investment-signal-classifier",
                    "X-Title": "investment-signal-classifier",
                },
            )
        raise MissingKeyError(
            "set TYPESAFE_API_KEY (https://console.typesafe.ai/) or OPENROUTER_API_KEY "
            "(https://openrouter.ai/keys) in .env"
        )

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def classify(self, request: dict[str, Any], *, advanced: bool = False) -> dict[str, Any]:
        # The client owns the routing decision's model id, not whatever the caller's JevBackend
        # happened to pass in `request["model"]` (in practice the two already agree).
        body = {"model": self.model, "state": request["state"], "questions": request["questions"]}
        delay = self.retry_delay_s
        last_error = "no attempt made"
        attempts = 0
        for attempt in range(self.retries + 1):
            attempts += 1
            try:
                r = self._client.post(self.url, json=body)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                if attempt >= self.retries:
                    break
                time.sleep(delay)
                delay = min(delay * 2, self.max_retry_delay_s)
                continue
            if r.status_code == 200:
                return self._parse(r.json(), attempts)
            last_error = f"http {r.status_code}: {r.text[:300]}"
            if r.status_code not in RETRYABLE_STATUS or attempt >= self.retries:
                break
            wait = self._retry_after(r) or delay
            time.sleep(wait)
            delay = min(delay * 2, self.max_retry_delay_s)
        raise RuntimeError(last_error)

    def _parse(self, raw: dict[str, Any], attempts: int) -> dict[str, Any]:
        usage = raw.get("usage", {}) or {}
        input_tokens = usage.get("input_tokens")
        cost = usage.get("cost")
        cost_estimated = cost is None
        if cost is None and input_tokens is not None:
            cost = input_tokens * JEV_PRICE_PER_INPUT_TOKEN
        echoed_model = raw.get("model", self.model)
        return {
            "model": echoed_model,
            "answers": raw.get("answers", {}),
            "usage": {"input_tokens": input_tokens, "output_tokens": usage.get("output_tokens")},
            "metrics": {
                "route": self.route,
                "echoed_model": echoed_model,
                "cost_usd": cost,
                "cost_estimated": cost_estimated,
                "attempts": attempts,
            },
        }

    def close(self) -> None:
        self._client.close()
