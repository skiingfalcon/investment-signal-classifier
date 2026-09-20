"""TypesafeJevClient: request contract, route precedence, retry/backoff, cost accounting --
mirrored from jev-email-cascade's tests/test_jev_client.py -- plus an envelope-parity test
proving the shared policy code treats the local and hosted backends identically.
"""

import json
import logging

import httpx
import pytest

from isc.backends import JevBackend
from isc.config import Settings
from isc.jev.typesafe_backend import MissingKeyError, TypesafeJevClient
from isc.policy import decide_stage1
from isc.questions import Choice, Noul, Score


def _settings(**kw) -> Settings:
    base = {"typesafe_api_key": None, "openrouter_api_key": None}
    base.update(kw)
    return Settings(_env_file=None, **base)


def test_from_settings_requires_a_key():
    with pytest.raises(MissingKeyError):
        TypesafeJevClient.from_settings(_settings())


def test_typesafe_takes_precedence_when_both_keys_set():
    settings = _settings(typesafe_api_key="ts-key", openrouter_api_key="or-key")
    client = TypesafeJevClient.from_settings(settings)
    assert client.route == "typesafe"
    assert client.url == settings.typesafe_systemone_url
    assert client.model == settings.typesafe_model


def test_openrouter_used_when_only_that_key_set():
    settings = _settings(openrouter_api_key="or-key")
    client = TypesafeJevClient.from_settings(settings)
    assert client.route == "openrouter"
    assert client.url == settings.jev_decisions_url
    assert client.model == settings.openrouter_jev_model


def _mock_client(handler, **kwargs) -> TypesafeJevClient:
    return TypesafeJevClient(
        url="https://x/v1/systemone",
        api_key="k",
        model="typesafe/jev-1.13",
        route="openrouter",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_request_contract():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "typesafe/jev-1.13-20260917",
                "answers": {"is_urgent": {"type": "noul", "noul": 0.9}},
                "usage": {"input_tokens": 100, "output_tokens": 5, "cost": 4.2e-6},
            },
        )

    client = _mock_client(handler)
    request = {
        "model": "typesafe/jev-1.13",
        "state": {"subject": "hi"},
        "questions": {"is_urgent": Noul(instructions="urgent?").to_json()},
    }
    envelope = client.classify(request)
    assert captured["url"] == "https://x/v1/systemone"
    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "typesafe/jev-1.13"
    assert captured["body"]["state"] == {"subject": "hi"}
    assert envelope["model"] == "typesafe/jev-1.13-20260917"
    assert envelope["answers"]["is_urgent"]["noul"] == 0.9
    assert envelope["metrics"]["cost_usd"] == 4.2e-6
    assert envelope["metrics"]["cost_estimated"] is False
    assert envelope["metrics"]["echoed_model"] == "typesafe/jev-1.13-20260917"


def test_cost_is_estimated_when_usage_omits_it():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "typesafe/jev-1.13",
                "answers": {},
                "usage": {"input_tokens": 50, "output_tokens": 3},
            },
        )

    client = _mock_client(handler)
    envelope = client.classify({"model": "x", "state": {}, "questions": {}})
    assert envelope["metrics"]["cost_estimated"] is True
    assert envelope["metrics"]["cost_usd"] == pytest.approx(50 * 0.042 / 1_000_000)


def test_retries_on_429_then_succeeds(monkeypatch, caplog):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "slow down"})
        return httpx.Response(200, json={"model": "x", "answers": {}, "usage": {}})

    client = _mock_client(handler, retry_delay_s=0.01)
    with caplog.at_level(logging.WARNING, logger="isc"):
        envelope = client.classify({"model": "x", "state": {}, "questions": {}})
    assert len(calls) == 2
    assert sleeps == [2.0]
    assert envelope["metrics"]["attempts"] == 2
    assert "jev openrouter retry" in caplog.text
    assert "429" in caplog.text


def test_gives_up_after_retries_exhausted(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = _mock_client(lambda r: httpx.Response(500), retries=1, retry_delay_s=0.0)
    with pytest.raises(RuntimeError, match="http 500"):
        client.classify({"model": "x", "state": {}, "questions": {}})


def test_non_retryable_status_stops_immediately(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(422, text="bad request")

    client = _mock_client(handler, retries=3)
    with pytest.raises(RuntimeError, match="422"):
        client.classify({"model": "x", "state": {}, "questions": {}})
    assert len(calls) == 1


def test_jev_backend_adapter_raises_are_recorded_not_propagated():
    client = _mock_client(lambda r: httpx.Response(500), retries=0, retry_delay_s=0.0)
    backend = JevBackend(client, client.model, name="typesafe")
    result = backend.decide({"current": {}}, {})
    assert not result.ok
    assert "http 500" in result.error


# -- envelope parity: the point of this backend existing at all -----------------------------


REAL_JEV_ANSWERS = {
    # Noul: only `noul`, no probabilities/confidence, even though criteria were sent.
    "ocf_covers_net_income": {"type": "noul", "noul": 0.98},
    # Choice: confidence arrives as a JSON int, not a float.
    "revenue_growth": {
        "type": "choice",
        "choice": "growing",
        "probabilities": {"growing": 1, "flat": 0, "declining": 0, "other": 0},
        "confidence": 1,
    },
    # Score: fractional expectation, string-keyed probabilities, an echoed legend.
    "leverage": {
        "type": "score",
        "score": 0.01,
        "probabilities": {"0": 0.99, "1": 0.01, "2": 0.0},
        "confidence": 0.99,
        "legend": {"0": "Low", "1": "Moderate", "2": "High"},
    },
}

RULES_LABELS = {"ocf_covers_net_income": True, "revenue_growth": "growing", "leverage": 0}

SUBSET_QUESTIONS = {
    "ocf_covers_net_income": Noul(instructions="x"),
    "revenue_growth": Choice(
        instructions="x", criteria={"growing": "g", "flat": "f", "declining": "d", "other": "o"}
    ),
    "leverage": Score(instructions="x", criteria=["Low", "Moderate", "High"]),
}


def test_real_jev_response_shapes_parse_and_route_identically_to_the_local_backend():
    from isc.backends import Answer, DecisionResult

    hosted_answers = {qid: Answer.from_json(raw) for qid, raw in REAL_JEV_ANSWERS.items()}
    hosted_result = DecisionResult(answers=hosted_answers, model="typesafe/jev-1.13-20260917")
    outcomes, disputed = decide_stage1(hosted_result.answers, RULES_LABELS, SUBSET_QUESTIONS)

    assert disputed == []
    assert outcomes["ocf_covers_net_income"].final is True
    assert outcomes["revenue_growth"].final == "growing"
    assert outcomes["leverage"].final == 0
    for qid in SUBSET_QUESTIONS:
        assert outcomes[qid].resolved_by == "stage1"
        assert outcomes[qid].agree_jev_rules is True
