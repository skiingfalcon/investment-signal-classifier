"""Shared test fixtures: fixture paths and a minimal llama-server double.

FakeLlamaServer tokenizes with UTF-8 byte IDs (the same trick simple-jev's own hf-server test
conftest uses for a fake tokenizer), so single-character Simple Jev labels (A, B, C, ... or
0-9, or 1-9) are trivially single-token and distinct: the byte value of the label character is
its "token id" everywhere in these tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sec_data_dir() -> Path:
    return FIXTURES / "sec_data"


@pytest.fixture
def results_mini_path() -> Path:
    return FIXTURES / "results_mini.jsonl"


class FakeLlamaServer:
    def __init__(self, *, ignore_enable_thinking: bool = False, completion_script=None):
        self.ignore_enable_thinking = ignore_enable_thinking
        self.completion_script = completion_script if completion_script is not None else {}
        self.requests: list[tuple[str, dict]] = []
        self._completion_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content or b"{}")
        self.requests.append((path, body))
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/props":
            return httpx.Response(
                200, json={"total_slots": 4, "default_generation_settings": {"n_ctx": 131072}}
            )
        if path == "/apply-template":
            return httpx.Response(200, json={"prompt": self._render(body)})
        if path == "/tokenize":
            return httpx.Response(200, json={"tokens": self._tokenize(body["content"])})
        if path == "/completion":
            return self._completion(body)
        return httpx.Response(404)

    def _render(self, body: dict) -> str:
        parts = [f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in body["messages"]]
        kwargs = body.get("chat_template_kwargs") or {}
        thinking_off = kwargs.get("enable_thinking") is False
        tail = (
            "<think>\n\n</think>\n\n"
            if (thinking_off and not self.ignore_enable_thinking)
            else "<think>\n"
        )
        parts.append(f"<|im_start|>assistant\n{tail}")
        return "".join(parts)

    def _tokenize(self, text: str) -> list[int]:
        return list(text.encode("utf-8"))

    def _completion(self, body: dict) -> httpx.Response:
        self._completion_calls += 1
        prompt = body["prompt"]
        assert isinstance(prompt, list) and all(isinstance(t, int) for t in prompt)
        script = self.completion_script
        entry = (
            script[min(self._completion_calls - 1, len(script) - 1)]
            if isinstance(script, list)
            else script
        )
        if entry.get("status") == 503 and not entry.get("_served"):
            entry["_served"] = True
            return httpx.Response(503, headers={"Retry-After": "0"})
        label_logprobs: dict[int, float] = entry.get("label_logprobs", {})
        omit = set(entry.get("omit_ids", ()))
        ordered = sorted(label_logprobs.items(), key=lambda kv: -kv[1])
        top = [
            {"id": tid, "token": chr(tid), "logprob": lp, "bytes": [tid]}
            for tid, lp in ordered
            if tid not in omit
        ]
        return httpx.Response(
            200,
            json={
                "content": "",
                "completion_probabilities": [
                    {"id": top[0]["id"] if top else 0, "top_logprobs": top}
                ],
                "tokens_cached": entry.get("tokens_cached", max(len(prompt) - 5, 0)),
                "tokens_evaluated": len(prompt),
                "id_slot": entry.get("id_slot", 0),
                "timings": {"prompt_n": entry.get("prompt_n", len(prompt))},
            },
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def fake_llama_server():
    return FakeLlamaServer
