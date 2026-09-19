import pytest

from isc.jev.llama_server import LlamaServerClient
from isc.jev.llamacpp_backend import LlamaCppBackend, LlamaCppCompiler
from isc.jev.model_profiles import PROFILES

QWEN = PROFILES["qwen3.8-27b"]

REQUEST = {
    "model": "qwen3.8-27b",
    "state": {"company": "ACME", "current": {"revenue": 1250.0}},
    "questions": {
        "color": {
            "type": "choice",
            "instructions": "Color?",
            "criteria": {"red": None, "blue": None},
        },
        "is_red": {"type": "noul", "instructions": "Is it red?"},
    },
}


def _client(fake_llama_server, **kwargs):
    fake = fake_llama_server(**kwargs)
    return LlamaServerClient("http://fake", transport=fake.transport()), fake


def test_compile_closes_the_think_block_and_derives_single_token_labels(fake_llama_server):
    client, fake = _client(fake_llama_server)
    compiled = LlamaCppCompiler(client, QWEN).compile(REQUEST)
    assert compiled.thinking_block == "asis"
    assert len(compiled.branches) == 2
    color = next(b for b in compiled.branches if b.question_id == "color")
    assert color.label_ids == {"A": ord("A"), "B": ord("B")}
    is_red = next(b for b in compiled.branches if b.question_id == "is_red")
    assert is_red.label_ids == {str(i): ord(str(i)) for i in range(1, 10)}
    assert color.prompt_text.endswith('<think>\n\n</think>\n\n{"answer": "')


def test_compile_patches_an_open_think_block_when_server_ignores_the_kwarg(fake_llama_server):
    client, fake = _client(fake_llama_server, ignore_enable_thinking=True)
    compiled = LlamaCppCompiler(client, QWEN).compile(REQUEST)
    assert compiled.thinking_block == "patched"
    color = next(b for b in compiled.branches if b.question_id == "color")
    assert "<think>\n\n</think>\n\n" in color.prompt_text


def test_score_reads_label_logprobs_and_scores_via_common(fake_llama_server):
    script = [
        {"label_logprobs": {ord("A"): -0.1, ord("B"): -3.0}},
        {"label_logprobs": {ord(str(i)): (-0.1 if i == 9 else -5.0) for i in range(1, 10)}},
    ]
    client, fake = _client(fake_llama_server, completion_script=script)
    backend = LlamaCppBackend(client, QWEN)
    response = backend.classify(REQUEST)
    assert response["answers"]["color"]["choice"] == "red"
    assert response["answers"]["is_red"]["noul"] > 0.9
    assert response["usage"]["input_tokens"] > 0
    assert "metrics" in response


def test_metrics_report_cache_and_prefix_stats(fake_llama_server):
    script = [
        {"label_logprobs": {ord("A"): -0.1, ord("B"): -3.0}, "tokens_cached": 10, "prompt_n": 5},
        {
            "label_logprobs": {ord(str(i)): -1.0 for i in range(1, 10)},
            "tokens_cached": 400,
            "prompt_n": 20,
        },
    ]
    client, fake = _client(fake_llama_server, completion_script=script)
    backend = LlamaCppBackend(client, QWEN)
    response = backend.classify(REQUEST)
    metrics = response["metrics"]
    assert metrics["engine_calls"] == 2
    assert metrics["cached_tokens_total"] == 410
    assert metrics["prompt_n_total"] == 25
    assert metrics["prefix_tokens"] >= 0


def _missing_label_script():
    return [
        {"label_logprobs": {ord("A"): -0.1}, "omit_ids": [ord("B")]},  # B absent from top-k
        {"label_logprobs": {ord(str(i)): -1.0 for i in range(1, 10)}},
    ]


def test_missing_label_is_recorded_in_metrics(fake_llama_server):
    client, fake = _client(fake_llama_server, completion_script=_missing_label_script())
    backend = LlamaCppBackend(client, QWEN)
    compiled = LlamaCppCompiler(client, QWEN).compile(REQUEST)
    logits, metrics = backend.score(compiled)
    assert metrics["missing_labels"]["0"] == ["B"]


def test_missing_label_does_not_block_the_correct_answer(fake_llama_server):
    client, fake = _client(fake_llama_server, completion_script=_missing_label_script())
    backend = LlamaCppBackend(client, QWEN)
    response = backend.classify(REQUEST, advanced=False)
    assert response["answers"]["color"]["choice"] == "red"


def test_missing_label_raises_when_every_label_falls_outside_top_k(fake_llama_server):
    # The floor value is always strictly below every observed logprob, so a single missing
    # label among present ones can never "win" -- only a branch with *no* labels in the
    # top-k (server returned unrelated tokens entirely) hits the unresolvable case.
    script = [
        {"label_logprobs": {}, "omit_ids": [ord("A"), ord("B")]},
        {"label_logprobs": {ord(str(i)): -1.0 for i in range(1, 10)}},
    ]
    client, fake = _client(fake_llama_server, completion_script=script)
    backend = LlamaCppBackend(client, QWEN)
    with pytest.raises(ValueError, match="fell outside"):
        backend.classify(REQUEST)
