"""Run one FactSet through the full cascade: JEV stage 1 -> rule engine compare -> optional
JEV stage 2 (support check) -> optional generative arbiter -> :class:`isc.policy.Decision`.

Writes ``runs/<stamp>/{results.jsonl,run.json,report.md}``, the same artifact shape as
jev-email-cascade's ``pipeline.py``.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from isc import facts as facts_module
from isc import policy, questions, report, rules
from isc import state as state_module
from isc.backends import DecisionBackend
from isc.config import Settings
from isc.facts import FactSet
from isc.verify import GenerativeArbiter

log = logging.getLogger("isc")


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


def _fmt_duration(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:  # NaN
        return "?"
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def _short_source(source: str, width: int = 24) -> str:
    name = source.removeprefix("model:")
    if "/" in name:
        name = name.split("/", 1)[0]
    if len(name) <= width:
        return name
    return name[: width - 1] + "…"


def _stage_cost_usd(stage: Mapping | None) -> float | None:
    if not stage:
        return None
    metrics = stage.get("metrics") or {}
    if "cost_usd" not in metrics:
        return None
    return float(metrics["cost_usd"] or 0.0)


def _row_cost_usd(row: Mapping) -> float | None:
    costs = [_stage_cost_usd(row.get("stage1")), _stage_cost_usd(row.get("stage2"))]
    present = [c for c in costs if c is not None]
    return sum(present) if present else None


def _progress_line(
    i: int,
    n: int,
    row: Mapping,
    *,
    elapsed_s: float,
    routes: Counter,
    cost_usd: float,
) -> str:
    """One stderr line of live telemetry; same shape for llamacpp, typesafe, and mock."""
    route = (row.get("decision") or {}).get("route", "?")
    signal = (row.get("decision") or {}).get("final_signal", "?")
    stage1 = row.get("stage1") or {}
    stage2 = row.get("stage2")
    gen = row.get("generative")
    metrics = stage1.get("metrics") or {}
    bits = [
        f"[{i:>{len(str(n))}}/{n}]",
        f"{row.get('ticker', '?'):<5}",
        str(row.get("fiscal_year_end", "?")),
        f"{_short_source(str(row.get('source', '?'))):<24}",
        f"{route}/{signal}",
        f"s1={_fmt_ms(stage1.get('latency_ms'))}",
    ]
    if stage2:
        bits.append(f"s2={_fmt_ms(stage2.get('latency_ms'))}")
    if gen:
        bits.append(f"gen={_fmt_ms(gen.get('latency_ms'))}")
        if gen.get("error"):
            bits.append(f"gen_error={gen['error'][:80]}")
    tok = stage1.get("input_tokens") or metrics.get("prompt_n_total")
    if tok:
        bits.append(f"tok={tok}")
    cached = metrics.get("cached_tokens_total")
    if cached:
        bits.append(f"cache={cached}")
    row_cost = _row_cost_usd(row)
    if row_cost is not None:
        bits.append(f"cost=${row_cost:.5f}")
        bits.append(f"sum=${cost_usd:.5f}")
    attempts = metrics.get("attempts")
    if attempts and attempts > 1:
        bits.append(f"attempts={attempts}")
    echoed = metrics.get("echoed_model")
    if echoed:
        bits.append(f"model={echoed}")
    missing = metrics.get("missing_labels") or {}
    if missing:
        bits.append(f"missing_labels={sum(len(v) for v in missing.values())}")
    if stage1.get("error"):
        bits.append(f"error={str(stage1['error'])[:120]}")
    outcomes = (row.get("decision") or {}).get("outcomes") or {}
    disputed = [qid for qid, o in outcomes.items() if o.get("resolved_by") != "stage1"]
    if disputed:
        shown = ",".join(disputed[:3])
        extra = "" if len(disputed) <= 3 else f"+{len(disputed) - 3}"
        bits.append(f"disputed={shown}{extra}")
    rate = i / elapsed_s if elapsed_s > 0 else 0.0
    remaining = (n - i) / rate if rate > 0 else None
    eta = _fmt_duration(remaining) if remaining is not None else "?"
    route_bits = " ".join(f"{k}={v}" for k, v in sorted(routes.items()))
    bits.append(f"{rate:.2f}/s")
    bits.append(f"eta={eta}")
    bits.append(f"elapsed={_fmt_duration(elapsed_s)}")
    if route_bits:
        bits.append(route_bits)
    return " ".join(bits)


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
    n = len(factsets)
    backend_name = getattr(backend, "name", backend.__class__.__name__)
    jev_model = getattr(backend, "model", settings.jev_model)
    log.info(
        "starting run=%s backend=%s model=%s n=%s verify=%s escalate=%s -> %s",
        run_id,
        backend_name,
        jev_model,
        n,
        verify,
        escalate,
        run_dir,
    )

    t0 = time.perf_counter()
    rows: list[dict] = []
    routes: Counter[str] = Counter()
    cost_usd = 0.0
    results_path = run_dir / "results.jsonl"
    with results_path.open("w") as f:
        for i, fs in enumerate(factsets, 1):
            row = process_one(
                fs,
                backend,
                arbiter,
                state_mode=state_mode,
                verify=verify,
                escalate=escalate,
                sec_data_dir=settings.sec_data_dir,
            )
            rows.append(row)
            f.write(json.dumps(row))
            f.write("\n")
            f.flush()
            routes[row["decision"]["route"]] += 1
            row_cost = _row_cost_usd(row)
            if row_cost is not None:
                cost_usd += row_cost
            log.info(
                "%s",
                _progress_line(
                    i, n, row, elapsed_s=time.perf_counter() - t0, routes=routes, cost_usd=cost_usd
                ),
            )
    wall_s = time.perf_counter() - t0
    log.info(
        "finished run=%s n=%s wall=%s routes=%s jev_cost=$%.5f",
        run_id,
        len(rows),
        _fmt_duration(wall_s),
        dict(routes),
        cost_usd,
    )

    stage1_cost = sum(r["stage1"].get("metrics", {}).get("cost_usd") or 0.0 for r in rows)
    stage2_cost = sum((r["stage2"] or {}).get("metrics", {}).get("cost_usd") or 0.0 for r in rows)
    cost_estimated_any = any(
        r["stage1"].get("metrics", {}).get("cost_estimated")
        or (r["stage2"] or {}).get("metrics", {}).get("cost_estimated")
        for r in rows
    )
    echoed_models = sorted(
        {
            m
            for r in rows
            for m in (
                r["stage1"].get("metrics", {}).get("echoed_model"),
                (r["stage2"] or {}).get("metrics", {}).get("echoed_model"),
            )
            if m
        }
    )

    run_meta = {
        # The effective model actually used: settings.jev_model for the local backend, or the
        # hosted route's model id (possibly overridden by --model) for the typesafe backend.
        "backend": getattr(backend, "name", backend.__class__.__name__),
        "jev_model": getattr(backend, "model", settings.jev_model),
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
        # 0.0 / False / [] for the local backend, which has no per-call billing; non-zero for a
        # hosted Jev backend. That asymmetry is itself the cost row of a backend comparison.
        "jev_backend_metrics": {
            "stage1_cost_usd": stage1_cost,
            "stage2_cost_usd": stage2_cost,
            "cost_estimated_any": cost_estimated_any,
            "echoed_models": echoed_models,
        },
    }
    (run_dir / "run.json").write_text(json.dumps(run_meta, indent=2, default=str))
    (run_dir / "report.md").write_text(report.render_markdown(run_meta, rows))
    return run_dir
