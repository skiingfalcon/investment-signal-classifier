import json

import httpx

from isc.verify import RESPONSE_FORMAT, EscalationOutput, GenerativeArbiter


def test_escalation_schema_has_no_extra_fields_and_covers_every_question():
    schema = EscalationOutput.model_json_schema()
    assert schema.get("additionalProperties") is False
    for qid in (
        "revenue_growth",
        "profitability_trend",
        "ocf_covers_net_income",
        "eps_increased",
        "leverage",
        "liquidity",
        "share_count",
        "overall_signal",
        "rationale",
    ):
        assert qid in schema["properties"]


def test_response_format_embeds_the_schema():
    assert RESPONSE_FORMAT["type"] == "json_schema"
    assert RESPONSE_FORMAT["json_schema"]["strict"] is True


def test_schema_has_no_openai_strict_mode_unsupported_keywords():
    # OpenAI's Structured Outputs strict mode rejects maxLength/minLength/pattern/numeric bounds
    # outright; a schema carrying one would be rejected before the model ever runs.
    schema = json.dumps(RESPONSE_FORMAT["json_schema"]["schema"])
    for keyword in ("maxLength", "minLength", "pattern", "minimum", "maximum"):
        assert keyword not in schema


VALID_OUTPUT = {
    "revenue_growth": "growing",
    "profitability_trend": "improving",
    "ocf_covers_net_income": True,
    "eps_increased": True,
    "leverage": 1,
    "liquidity": "strong",
    "share_count": "stable",
    "overall_signal": "bullish",
    "rationale": "Revenue and net income both grew.",
}


def _server(content: str, *, status: int = 200, on_request=None):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"]["type"] in ("json_schema", "json_object")
        if on_request:
            on_request(request, body)
        return httpx.Response(
            status,
            json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 100}},
        )

    return httpx.MockTransport(handler)


def test_arbiter_parses_a_valid_response():
    arbiter = GenerativeArbiter(
        "http://x/v1", "gpt-5.6-terra", transport=_server(json.dumps(VALID_OUTPUT))
    )
    result = arbiter.arbitrate({"current": {}}, {}, {}, ["overall_signal"])
    assert result.ok
    assert result.output.overall_signal == "bullish"
    assert result.schema_mode == "json_schema"
    assert result.prompt_tokens == 100


def test_arbiter_records_a_schema_error_without_raising():
    arbiter = GenerativeArbiter("http://x/v1", "gpt-5.6-terra", transport=_server("not json"))
    result = arbiter.arbitrate({"current": {}}, {}, {}, ["overall_signal"])
    assert not result.ok
    assert "schema" in result.error


def test_arbiter_records_an_invalid_enum_value():
    bad = dict(VALID_OUTPUT, overall_signal="super_bullish")
    arbiter = GenerativeArbiter("http://x/v1", "gpt-5.6-terra", transport=_server(json.dumps(bad)))
    result = arbiter.arbitrate({"current": {}}, {}, {}, ["overall_signal"])
    assert not result.ok


def test_openai_profile_is_the_default_and_uses_the_real_api_request_shape():
    seen = {}

    def on_request(request, body):
        seen["body"] = body
        seen["headers"] = request.headers

    arbiter = GenerativeArbiter(
        "http://x/v1",
        "gpt-5.6-terra",
        transport=_server(json.dumps(VALID_OUTPUT), on_request=on_request),
    )
    assert arbiter.provider == "openai"
    arbiter.arbitrate({"current": {}}, {}, {}, ["overall_signal"])
    body = seen["body"]
    assert "max_completion_tokens" in body
    assert "max_tokens" not in body
    assert body["reasoning_effort"] == "low"
    assert "chat_template_kwargs" not in body
    assert "cache_prompt" not in body
    assert "temperature" not in body
    assert "authorization" not in seen["headers"]  # no api_key configured


def test_openai_profile_sends_bearer_token_when_api_key_configured():
    seen = {}

    def on_request(request, body):
        seen["headers"] = request.headers

    arbiter = GenerativeArbiter(
        "http://x/v1",
        "gpt-5.6-terra",
        api_key="sk-test-123",
        transport=_server(json.dumps(VALID_OUTPUT), on_request=on_request),
    )
    arbiter.arbitrate({"current": {}}, {}, {}, ["overall_signal"])
    assert seen["headers"]["authorization"] == "Bearer sk-test-123"


def test_local_profile_keeps_the_llama_server_request_shape():
    seen = {}

    def on_request(request, body):
        seen["body"] = body

    arbiter = GenerativeArbiter(
        "http://x/v1",
        "gpt-oss-120b",
        provider="local",
        transport=_server(json.dumps(VALID_OUTPUT), on_request=on_request),
    )
    assert arbiter.provider == "local"
    arbiter.arbitrate({"current": {}}, {}, {}, ["overall_signal"])
    body = seen["body"]
    assert body["max_tokens"] == 1500
    assert "max_completion_tokens" not in body
    assert body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"reasoning_effort": "low"}
    assert body["cache_prompt"] is True
