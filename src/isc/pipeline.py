"""Run one FactSet through the full cascade: JEV stage 1 -> rule engine compare -> optional
JEV stage 2 (support check) -> optional generative arbiter -> :class:`isc.policy.Decision`.

Writes ``runs/<stamp>/{results.jsonl,run.json,report.md}``, the same artifact shape as
jev-email-cascade's ``pipeline.py``.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from isc import facts as facts_module
from isc import policy, questions, report, rules
from isc import state as state_module
from isc.backends import DecisionBackend
from isc.config import Settings
from isc.facts import FactSet
from isc.verify import GenerativeArbiter


def process_one(
    fs: FactSet,
    backend: DecisionBackend,
    arbiter: GenerativeArbiter | None,
    *,
    state_mode: str = "derived",
    verify: bool = True,
    escalate: bool = True,
    sec_data_dir: Path | None = None,
) -> dict:
    state = state_module.render(fs, state_mode)
    rules_labels = rules.label(fs)

    truth_fs = fs if fs.source == "xbrl" else facts_module.xbrl_twin(fs, sec_data_dir)
    truth = rules.label(truth_fs)
    extraction_changed_label = sorted(
        qid for qid in rules.RULE_KEYS if rules_labels[qid] != truth[qid]
    )

    stage1 = backend.decide(state, questions.QUESTIONS)
    outcomes, disputed = policy.decide_stage1(stage1.answers, rules_labels)

    stage2 = None
    if verify and disputed:
        claim_source = {qid: outcomes[qid].jev for qid in disputed}
        verify_qs = questions.verify_questions(claim_source, rules_labels)
        support_answers = {}
        if verify_qs:
            stage2 = backend.decide(state, verify_qs)
            support_answers = stage2.answers
        disputed = policy.decide_stage2(outcomes, disputed, support_answers)

    arbiter_result = None
    if disputed and escalate and arbiter is not None:
        jev_values = {qid: outcomes[qid].jev for qid in rules.RULE_KEYS}
        arbiter_result = arbiter.arbitrate(state, jev_values, rules_labels, disputed)

    gen_error = None
    if disputed and escalate and arbiter_result is None:
        gen_error = "no arbiter configured"
    elif arbiter_result is not None:
        gen_error = arbiter_result.error

    decision = policy.finalize(
        outcomes, disputed, arbiter_result.output if arbiter_result else None, gen_error
    )

    generative_dict = None
    if arbiter_result is not None:
        generative_dict = {
            "output": arbiter_result.output.model_dump() if arbiter_result.output else None,
            "error": arbiter_result.error,
            "schema_mode": arbiter_result.schema_mode,
            "latency_ms": arbiter_result.latency_ms,
            "prompt_tokens": arbiter_result.prompt_tokens,
            "completion_tokens": arbiter_result.completion_tokens,
            "cached_tokens": arbiter_result.cached_tokens,
            "reasoning_tokens": arbiter_result.reasoning_tokens,
        }

    return {
        "id": fs.id,
        "ticker": fs.ticker,
        "fiscal_year_end": fs.fiscal_year_end,
        "source": fs.source,
        "state_mode": state_mode,
        "state_hash": state_module.state_hash(state),
        "labels": {
            "rules": rules_labels,
            "truth": truth,
            "extraction_changed_label": extraction_changed_label,
        },
        "quality": fs.quality.model_dump(),
        "stage1": stage1.as_dict(),
        "stage2": stage2.as_dict() if stage2 else None,
        "generative": generative_dict,
        "decision": decision.model_dump(mode="json"),
    }


def run(
    settings: Settings,
    *,
    backend: DecisionBackend,
    arbiter: GenerativeArbiter | None,
    factsets: list[FactSet],
    state_mode: str = "derived",
    verify: bool = True,
    escalate: bool = True,
    limit: int | None = None,
) -> Path:
    if limit is not None:
        factsets = factsets[:limit]

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = settings.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    rows = [
        process_one(
            fs,
            backend,
            arbiter,
            state_mode=state_mode,
            verify=verify,
            escalate=escalate,
            sec_data_dir=settings.sec_data_dir,
        )
        for fs in factsets
    ]
    wall_s = time.perf_counter() - t0

    with (run_dir / "results.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row))
            f.write("\n")

    run_meta = {
        "backend": getattr(backend, "name", backend.__class__.__name__),
        "jev_model": settings.jev_model,
        "gen_model": settings.gen_model if arbiter is not None else None,
        "state_mode": state_mode,
        "verify": verify,
        "escalate": escalate,
        "n": len(rows),
        "questions_hash": questions.questions_hash(),
        "policy": policy.POLICY,
        "thresholds": rules.THRESHOLDS,
        "wall_s": wall_s,
        "routes": dict(Counter(row["decision"]["route"] for row in rows)),
    }
    (run_dir / "run.json").write_text(json.dumps(run_meta, indent=2, default=str))
    (run_dir / "report.md").write_text(report.render_markdown(run_meta, rows))
    return run_dir
