"""The shared answer schema and backend protocol.

``Answer``/``DecisionResult`` mirror jev-email-cascade's ``backends.py`` shapes, so the policy,
pipeline, and report never need to know which backend ran. ``JevBackend`` adapts anything that
speaks the raw Simple Jev envelope (``{model, answers, usage}``, e.g. ``isc.jev.llamacpp_backend``)
to this shape. ``MockBackend`` needs no server: it derives the rule-engine label straight from the
rendered ``state`` dict and answers with high confidence on it, with a configurable chance of a
low-confidence wrong answer -- enough to exercise every routing path in ``policy.py`` offline.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from isc import rules
from isc.questions import Choice, Question, Score, questions_json


@dataclass
class Answer:
    type: str
    noul: float | None = None
    choice: str | None = None
    score: float | None = None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    legend: dict[str, str] | None = None
    error: str | None = None

    @classmethod
    def from_json(cls, raw: dict) -> Answer:
        probs = raw.get("probabilities")
        if probs is not None:
            probs = {str(k): float(v) for k, v in probs.items()}
        return cls(
            type=raw.get("type", ""),
            noul=raw.get("noul"),
            choice=raw.get("choice"),
            score=raw.get("score"),
            probabilities=probs,
            confidence=raw.get("confidence"),
            legend=raw.get("legend"),
            error=raw.get("error"),
        )


@dataclass
class DecisionResult:
    answers: dict[str, Answer]
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0
    calls: int = 1
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None

    def as_dict(self) -> dict:
        return {
            "answers": {
                qid: {k: v for k, v in vars(a).items() if v is not None}
                for qid, a in self.answers.items()
            },
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "calls": self.calls,
            "error": self.error,
            "metrics": self.metrics,
        }


class DecisionBackend(Protocol):
    name: str

    def decide(self, state: dict, questions: dict[str, Question]) -> DecisionResult: ...


class RawJevClient(Protocol):
    """Something that speaks the raw Simple Jev envelope (see ``jev.llamacpp_backend``)."""

    def classify(self, request: dict, *, advanced: bool = False) -> dict: ...


class JevBackend:
    """Adapts a ``RawJevClient`` to :class:`DecisionBackend`."""

    def __init__(self, client: RawJevClient, model: str, *, name: str = "llamacpp") -> None:
        self.client = client
        self.model = model
        self.name = name

    def decide(self, state: dict, questions: dict[str, Question]) -> DecisionResult:
        request = {"model": self.model, "state": state, "questions": questions_json(questions)}
        t0 = time.perf_counter()
        try:
            envelope = self.client.classify(request, advanced=True)
        except Exception as exc:  # noqa: BLE001 - recorded, not raised, like the cascade backends
            return DecisionResult(
                answers={},
                model=self.model,
                error=str(exc),
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        latency_ms = (time.perf_counter() - t0) * 1000
        answers = {qid: Answer.from_json(raw) for qid, raw in envelope.get("answers", {}).items()}
        usage = envelope.get("usage", {})
        return DecisionResult(
            answers=answers,
            model=envelope.get("model", self.model),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            latency_ms=latency_ms,
            metrics=envelope.get("metrics", {}),
        )


def _state_values(state: dict, which: str) -> dict[str, float]:
    return dict(state.get(which, {}))


class MockBackend:
    """No server required: answers the rule-engine label with high confidence, and sometimes
    (probability ``noise``) a wrong, low-confidence answer, so offline tests can exercise every
    route (auto/verified/escalated/review) without a GPU.
    """

    name = "mock"

    def __init__(self, *, noise: float = 0.0, seed: int = 0, model: str = "mock-jev") -> None:
        self.noise = noise
        self.model = model
        self._rng = random.Random(seed)

    def decide(self, state: dict, questions: dict[str, Question]) -> DecisionResult:
        current, prior = _state_values(state, "current"), _state_values(state, "prior")
        truth = rules.label_from_values(current, prior)
        answers: dict[str, Answer] = {}
        for qid, q in questions.items():
            target = self._claim_target(qid, truth)
            flip = self._rng.random() < self.noise
            answers[qid] = self._answer_for(q, target, flip)
        return DecisionResult(answers=answers, model=self.model, input_tokens=0, output_tokens=0)

    def _claim_target(self, qid: str, truth: dict) -> object:
        if qid.startswith("supports_"):
            # Stage-2 claim Nouls are named after the stage-1 question; the "true" target here
            # is whatever the underlying rule-engine label is (a MockBackend stage-1 answer that
            # matches the rules never reaches this claim, since verify_questions only asks about
            # disputed questions -- so treat every claim under test as false against a noiseless
            # MockBackend to keep the calibration story honest: stage 1 was wrong, so is the claim).
            return False
        return truth.get(qid)

    def _answer_for(self, q: Question, target: object, flip: bool) -> Answer:
        if isinstance(q, Choice):
            options = list(q.criteria)
            choice = (
                target
                if (target in options and not flip)
                else self._rng.choice([o for o in options if o != target] or options)
            )
            conf = 0.9 if not flip else 0.45
            probs = self._spread(options, choice, conf)
            return Answer(type="choice", choice=choice, confidence=conf, probabilities=probs)
        if isinstance(q, Score):
            n = len(q.criteria)
            level = target if isinstance(target, int) and 0 <= target < n else 0
            if flip:
                level = (level + 1) % n
            conf = 0.9 if not flip else 0.45
            probs = self._spread([str(i) for i in range(n)], str(level), conf)
            score = sum(i * probs[str(i)] for i in range(n))
            return Answer(type="score", score=score, confidence=conf, probabilities=probs)
        # Noul
        is_true = bool(target) and not flip if target is not None else (self._rng.random() < 0.5)
        if target is None:
            is_true = self._rng.random() < 0.5 if not flip else self._rng.random() < 0.5
        p = 0.9 if is_true else 0.1
        if flip:
            p = 1.0 - p
        return Answer(type="noul", noul=p)

    def _spread(self, options: list[str], winner: str, conf: float) -> dict[str, float]:
        rest = [o for o in options if o != winner]
        remainder = (1.0 - conf) / len(rest) if rest else 0.0
        return {o: (conf if o == winner else remainder) for o in options}
