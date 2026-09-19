"""Stage-2 claim rendering (in ``questions.verify_questions``) plus the generative arbiter that
resolves whatever stage 1 and stage 2 could not: a JSON-schema-constrained call to a generative
model, validated with Pydantic before any of it is trusted.

Default target is a hosted frontier model (``provider="openai"``, e.g. gpt-5.6-terra) reached
over its real OpenAI-compatible API, not a second local llama-server -- the Spark keeps one large
model resident at a time, and the arbiter only fires on disputed questions, so paying for a
second resident model on the same box buys little. ``provider="local"`` is kept for a box with
spare capacity that wants to point this at a second llama-server instead; the two profiles differ
in exactly the fields llama-server accepts as extensions and the real API does not (see
jev-email-cascade's ``generative.py::_ChatClient``, which this class mirrors).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from isc.questions import QUESTIONS, Choice, Score


class EscalationOutput(BaseModel):
    """One answer per question ``isc.policy`` could not resolve. The arbiter must answer every
    field even if only some were disputed; ``policy.finalize`` only reads the disputed ones.
    """

    model_config = ConfigDict(extra="forbid")

    revenue_growth: Literal["growing", "flat", "declining", "other"]
    profitability_trend: Literal["loss_making", "improving", "stable", "deteriorating", "other"]
    ocf_covers_net_income: bool
    eps_increased: bool
    leverage: Literal[0, 1, 2]
    liquidity: Literal["strong", "adequate", "thin", "other"]
    share_count: Literal["buyback", "stable", "dilution", "other"]
    overall_signal: Literal["bullish", "neutral", "bearish", "other"]
    # No length constraint: OpenAI's Structured Outputs strict mode rejects maxLength/minLength/
    # pattern/numeric-bound keywords outright, so a schema carrying one would fail validation
    # before the model ever runs. Truncate defensively in the caller if a length cap is needed.
    rationale: str


RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "escalation",
        "strict": True,
        "schema": EscalationOutput.model_json_schema(),
    },
}


def _definitions_text() -> str:
    lines = []
    for qid, q in QUESTIONS.items():
        lines.append(f"- {qid}: {q.instructions}")
        if isinstance(q, Choice):
            for opt, desc in q.criteria.items():
                lines.append(f"    {opt}: {desc}")
        elif isinstance(q, Score):
            for i, desc in enumerate(q.criteria):
                lines.append(f"    {i}: {desc}")
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "You audit an automated financial-signal classifier. Decide each question strictly by these "
    "definitions, using only the numbers given in facts. Do not use outside knowledge about the "
    "company.\n\n" + _definitions_text()
)


@dataclass
class ArbiterResult:
    output: EscalationOutput | None = None
    error: str | None = None
    schema_mode: str = "json_schema"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_ms: float = 0.0
    raw: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.output is not None


class GenerativeArbiter:
    """A trimmed copy of jev-email-cascade's ``_ChatClient``, fixed to one schema.

    ``provider="openai"`` (default) talks to a real OpenAI-compatible frontier API:
    ``max_completion_tokens`` instead of ``max_tokens``, no fixed ``temperature`` (frontier
    reasoning models do not consistently support one -- see llama-cpp-spark's README), top-level
    ``reasoning_effort``, no ``cache_prompt`` (meaningless for a hosted API), and a Bearer token
    when ``api_key`` is set. ``provider="local"`` keeps today's llama-server request shape.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        provider: Literal["openai", "local"] = "openai",
        api_key: str | None = None,
        reasoning_effort: str = "low",
        max_tokens: int = 1500,
        timeout_s: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.api_key = api_key
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_s, connect=10.0), transport=transport, headers=headers
        )

    def _body(self, user_content: str, *, response_format: dict) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        if self.provider == "local":
            return {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": self.max_tokens,
                "chat_template_kwargs": {"reasoning_effort": self.reasoning_effort},
                "cache_prompt": True,
                "response_format": response_format,
            }
        return {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": self.max_tokens,
            "reasoning_effort": self.reasoning_effort,
            "response_format": response_format,
        }

    def arbitrate(
        self, state: dict, jev: dict[str, Any], rules: dict[str, Any], disputed: list[str]
    ) -> ArbiterResult:
        user_content = json.dumps(
            {
                "facts": state,
                "classifier_answers": jev,
                "rule_engine_answers": rules,
                "disputed": disputed,
            },
            sort_keys=True,
        )
        t0 = time.perf_counter()
        result = self._call(user_content, RESPONSE_FORMAT, schema_mode="json_schema")
        if result.output is None and result.error and "response_format" not in (result.error or ""):
            # First attempt failed to parse or validate; retry once with the looser json_object
            # mode in case this server build does not honour a strict json_schema constraint.
            fallback = self._call(user_content, {"type": "json_object"}, schema_mode="json_object")
            if fallback.output is not None:
                result = fallback
        result.latency_ms = (time.perf_counter() - t0) * 1000
        return result

    def _call(self, user_content: str, response_format: dict, *, schema_mode: str) -> ArbiterResult:
        body = self._body(user_content, response_format=response_format)
        try:
            r = self._client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            raw = r.json()
        except httpx.HTTPError as exc:
            return ArbiterResult(error=f"http: {exc}", schema_mode=schema_mode)

        try:
            content = raw["choices"][0]["message"]["content"]
            output = EscalationOutput.model_validate_json(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            return ArbiterResult(error=f"schema: {exc}", schema_mode=schema_mode, raw=raw)

        usage = raw.get("usage", {})
        return ArbiterResult(
            output=output,
            schema_mode=schema_mode,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
            reasoning_tokens=usage.get("reasoning_tokens"),
            raw=raw,
        )
