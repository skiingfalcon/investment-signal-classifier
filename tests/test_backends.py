from isc.backends import JevBackend, MockBackend
from isc.questions import QUESTIONS


def _state():
    return {
        "current": {
            "revenue": 1250.0,
            "net_income": 150.0,
            "eps_diluted": 1.55,
            "equity": 1200.0,
            "long_term_debt": 350.0,
            "cash": 500.0,
        },
        "prior": {"revenue": 1100.0, "net_income": 120.0, "eps_diluted": 1.20},
    }


def test_mock_backend_noiseless_recovers_rule_engine_labels():
    from isc.rules import label_from_values

    state = _state()
    truth = label_from_values(state["current"], state["prior"])
    backend = MockBackend(noise=0.0)
    result = backend.decide(state, QUESTIONS)
    assert result.ok
    for qid, answer in result.answers.items():
        target = truth[qid]
        if answer.type == "choice":
            assert answer.choice == target
            assert answer.confidence == 0.9
        elif answer.type == "score":
            assert round(answer.score) == target
        elif answer.type == "noul":
            if target is True:
                assert answer.noul == 0.9
            elif target is False:
                assert answer.noul == 0.1


def test_mock_backend_full_noise_always_disagrees_on_choices():
    from isc.rules import label_from_values

    state = _state()
    truth = label_from_values(state["current"], state["prior"])
    backend = MockBackend(noise=1.0, seed=1)
    result = backend.decide(state, QUESTIONS)
    for qid, answer in result.answers.items():
        if answer.type == "choice" and truth[qid] is not None:
            assert answer.choice != truth[qid]
            assert answer.confidence < 0.6


class _FakeRawClient:
    def __init__(self, envelope=None, error=None):
        self.envelope = envelope
        self.error = error
        self.calls = []

    def classify(self, request, *, advanced=False):
        self.calls.append((request, advanced))
        if self.error:
            raise RuntimeError(self.error)
        return self.envelope


def test_jev_backend_adapts_envelope_to_decision_result():
    envelope = {
        "model": "qwen3.8-27b",
        "answers": {
            "revenue_growth": {
                "type": "choice",
                "choice": "growing",
                "confidence": 0.9,
                "probabilities": {"growing": 0.9},
            }
        },
        "usage": {"input_tokens": 500, "output_tokens": 0},
        "metrics": {"prompt_n_total": 500},
    }
    client = _FakeRawClient(envelope=envelope)
    backend = JevBackend(client, "qwen3.8-27b")
    result = backend.decide({"current": {}}, {"revenue_growth": QUESTIONS["revenue_growth"]})
    assert result.ok
    assert result.answers["revenue_growth"].choice == "growing"
    assert result.input_tokens == 500
    assert result.metrics["prompt_n_total"] == 500
    assert client.calls[0][1] is True  # advanced=True was requested


def test_jev_backend_records_backend_errors_without_raising():
    client = _FakeRawClient(error="connection refused")
    backend = JevBackend(client, "qwen3.8-27b")
    result = backend.decide({"current": {}}, {"revenue_growth": QUESTIONS["revenue_growth"]})
    assert not result.ok
    assert "connection refused" in result.error
    assert result.answers == {}
