import json

import httpx
import pytest

from isc.jev.llama_server import LlamaServerClient, LlamaServerError


def _client(handler, **kwargs) -> LlamaServerClient:
    return LlamaServerClient("http://fake", transport=httpx.MockTransport(handler), **kwargs)


def test_healthy_true_and_false():
    ok = _client(lambda r: httpx.Response(200))
    assert ok.healthy() is True
    down = _client(lambda r: httpx.Response(500))
    assert down.healthy() is False


def test_apply_template_posts_messages_and_kwargs():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx.Response(200, json={"prompt": "RENDERED"})

    client = _client(handler)
    result = client.apply_template([{"role": "user", "content": "hi"}], {"enable_thinking": False})
    assert result == "RENDERED"
    assert seen["path"] == "/apply-template"
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_tokenize_defaults():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body == {"content": "abc", "add_special": False, "parse_special": True}
        return httpx.Response(200, json={"tokens": [1, 2, 3]})

    client = _client(handler)
    assert client.tokenize("abc") == [1, 2, 3]


def test_completion_posts_body_verbatim():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["n_predict"] == 1
        return httpx.Response(200, json={"content": "A"})

    client = _client(handler)
    assert client.completion({"prompt": [1, 2], "n_predict": 1}) == {"content": "A"}


def test_503_is_retried_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, retries=2, retry_delay_s=0.001)
    assert client.completion({}) == {"ok": True}
    assert calls["n"] == 2


def test_4xx_raises_llama_server_error():
    client = _client(lambda r: httpx.Response(400, text="bad request"))
    with pytest.raises(LlamaServerError):
        client.completion({})
