"""Turn a run's rows into accuracy, agreement, and cost/latency metrics, and render Markdown.

Reads straight from each row's ``decision.outcomes`` (already carries ``jev``/``rules``/``final``/
``resolved_by`` per question -- see ``isc.policy``), so this module does no re-parsing of raw
backend answers.
"""

from __future__ import annotations

from isc import rules
from isc.stats import bootstrap_ci, percentile


def _flags(rows: list[dict], qid: str, key: str, *, skip_missing: bool = True) -> list[bool]:
    out = []
    for row in rows:
        outcome = row["decision"]["outcomes"].get(qid)
        if outcome is None:
            continue
        if key == "stage1_vs_rules":
            if outcome["agree_jev_rules"] is None:
                continue
            out.append(bool(outcome["agree_jev_rules"]))
        elif key == "final_vs_truth":
            truth = row["labels"]["truth"].get(qid)
            if skip_missing and truth in (None, "other"):
                continue
            out.append(outcome["final"] == truth)
    return out


def per_question_metrics(rows: list[dict]) -> dict:
    out = {}
    for qid in rules.RULE_KEYS:
        stage1_flags = _flags(rows, qid, "stage1_vs_rules")
        final_flags = _flags(rows, qid, "final_vs_truth")
        out[qid] = {
            "n_stage1_comparable": len(stage1_flags),
            "stage1_accuracy_vs_rules": (sum(stage1_flags) / len(stage1_flags))
            if stage1_flags
            else None,
            "stage1_ci": bootstrap_ci(stage1_flags),
            "n_final_comparable": len(final_flags),
            "final_accuracy_vs_truth": (sum(final_flags) / len(final_flags))
            if final_flags
            else None,
            "final_ci": bootstrap_ci(final_flags),
            "resolved_by": _resolved_by_counts(rows, qid),
        }
    return out


def _resolved_by_counts(rows: list[dict], qid: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        outcome = row["decision"]["outcomes"].get(qid)
        if outcome is None:
            continue
        key = outcome["resolved_by"]
        counts[key] = counts.get(key, 0) + 1
    return counts


def agreement_metrics(rows: list[dict]) -> dict:
    out = {}
    for qid in rules.RULE_KEYS:
        gen_total = gen_agree_jev = gen_agree_rules = gen_neither = 0
        stage2_total = stage2_kept_jev = stage2_used_rules = 0
        for row in rows:
            outcome = row["decision"]["outcomes"].get(qid)
            if outcome is None:
                continue
            if outcome["resolved_by"] == "generative":
                gen_total += 1
                if outcome["final"] == outcome["jev"]:
                    gen_agree_jev += 1
                if outcome["final"] == outcome["rules"]:
                    gen_agree_rules += 1
                if outcome["final"] != outcome["jev"] and outcome["final"] != outcome["rules"]:
                    gen_neither += 1
            if outcome["resolved_by"] == "stage2":
                stage2_total += 1
                if outcome["final"] == outcome["jev"]:
                    stage2_kept_jev += 1
                else:
                    stage2_used_rules += 1
        out[qid] = {
            "generative_n": gen_total,
            "generative_agrees_jev": gen_agree_jev,
            "generative_agrees_rules": gen_agree_rules,
            "generative_agrees_neither": gen_neither,
            "stage2_n": stage2_total,
            "stage2_kept_jev": stage2_kept_jev,
            "stage2_used_rules": stage2_used_rules,
        }
    return out


def route_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        route = row["decision"]["route"]
        counts[route] = counts.get(route, 0) + 1
    return counts


def extraction_impact(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        if not row["source"].startswith("model:"):
            continue
        changed = row["labels"]["extraction_changed_label"]
        if not changed:
            continue
        out.append(
            {
                "id": row["id"],
                "ticker": row["ticker"],
                "changed": changed,
                "route": row["decision"]["route"],
                "caught": all(
                    row["decision"]["outcomes"].get(qid, {}).get("final")
                    == row["labels"]["truth"].get(qid)
                    for qid in changed
                ),
            }
        )
    return out


def cost_latency_metrics(rows: list[dict]) -> dict:
    stage1_latency = [r["stage1"]["latency_ms"] for r in rows if r.get("stage1")]
    stage2_latency = [r["stage2"]["latency_ms"] for r in rows if r.get("stage2")]
    gen_latency = [r["generative"]["latency_ms"] for r in rows if r.get("generative")]
    prompt_total = sum(r["stage1"].get("metrics", {}).get("prompt_n_total", 0) or 0 for r in rows)
    cached_total = sum(
        r["stage1"].get("metrics", {}).get("cached_tokens_total", 0) or 0 for r in rows
    )
    return {
        "stage1_latency_p50_ms": percentile(stage1_latency, 0.5),
        "stage1_latency_p95_ms": percentile(stage1_latency, 0.95),
        "stage2_latency_p50_ms": percentile(stage2_latency, 0.5),
        "stage2_latency_p95_ms": percentile(stage2_latency, 0.95),
        "generative_latency_p50_ms": percentile(gen_latency, 0.5),
        "generative_latency_p95_ms": percentile(gen_latency, 0.95),
        "stage1_prompt_tokens_total": prompt_total,
        "stage1_cached_tokens_total": cached_total,
        "stage1_cache_hit_ratio": (cached_total / prompt_total) if prompt_total else None,
    }


def compute_metrics(run_meta: dict, rows: list[dict]) -> dict:
    return {
        "per_question": per_question_metrics(rows),
        "agreement": agreement_metrics(rows),
        "routes": route_counts(rows),
        "extraction_impact": extraction_impact(rows),
        "cost_latency": cost_latency_metrics(rows),
    }


def _fmt(x, digits=3) -> str:
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def render_markdown(run_meta: dict, rows: list[dict]) -> str:
    m = compute_metrics(run_meta, rows)
    lines = [
        f"# Run: backend={run_meta.get('backend')} jev_model={run_meta.get('jev_model')} "
        f"gen_model={run_meta.get('gen_model')}",
        "",
        f"n={run_meta.get('n')} state_mode={run_meta.get('state_mode')} verify={run_meta.get('verify')} "
        f"escalate={run_meta.get('escalate')} wall_s={_fmt(run_meta.get('wall_s'), 1)}",
        "",
        "## Routes",
        "",
        "| route | n |",
        "|---|---|",
    ]
    for route, n in sorted(m["routes"].items()):
        lines.append(f"| {route} | {n} |")

    lines += [
        "",
        "## Per-question accuracy",
        "",
        "| question | n(stage1) | stage1 vs rules | CI | n(final) | final vs truth | CI |",
        "|---|---|---|---|---|---|---|",
    ]
    for qid, q in m["per_question"].items():
        ci1 = "-" if not q["stage1_ci"] else f"{q['stage1_ci'][0]:.2f}-{q['stage1_ci'][1]:.2f}"
        ci2 = "-" if not q["final_ci"] else f"{q['final_ci'][0]:.2f}-{q['final_ci'][1]:.2f}"
        lines.append(
            f"| {qid} | {q['n_stage1_comparable']} | {_fmt(q['stage1_accuracy_vs_rules'])} | {ci1} | "
            f"{q['n_final_comparable']} | {_fmt(q['final_accuracy_vs_truth'])} | {ci2} |"
        )

    lines += [
        "",
        "## Agreement (stage2 / generative)",
        "",
        "| question | stage2 n | stage2 kept jev | stage2 used rules | gen n | gen~jev | gen~rules | gen~neither |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for qid, a in m["agreement"].items():
        lines.append(
            f"| {qid} | {a['stage2_n']} | {a['stage2_kept_jev']} | {a['stage2_used_rules']} | "
            f"{a['generative_n']} | {a['generative_agrees_jev']} | {a['generative_agrees_rules']} | "
            f"{a['generative_agrees_neither']} |"
        )

    if m["extraction_impact"]:
        lines += [
            "",
            "## Extraction impact (model-sourced rows where extraction changed a label)",
            "",
            "| id | changed | route | caught |",
            "|---|---|---|---|",
        ]
        for item in m["extraction_impact"]:
            lines.append(
                f"| {item['id']} | {', '.join(item['changed'])} | {item['route']} | {item['caught']} |"
            )

    cl = m["cost_latency"]
    stage1_lat = f"{_fmt(cl['stage1_latency_p50_ms'], 1)}/{_fmt(cl['stage1_latency_p95_ms'], 1)}"
    stage2_lat = f"{_fmt(cl['stage2_latency_p50_ms'], 1)}/{_fmt(cl['stage2_latency_p95_ms'], 1)}"
    gen_lat = (
        f"{_fmt(cl['generative_latency_p50_ms'], 1)}/{_fmt(cl['generative_latency_p95_ms'], 1)}"
    )
    lines += [
        "",
        "## Cost / latency",
        "",
        f"stage1 p50/p95 ms: {stage1_lat}  \n"
        f"stage2 p50/p95 ms: {stage2_lat}  \n"
        f"generative p50/p95 ms: {gen_lat}  \n"
        f"stage1 prompt tokens total: {cl['stage1_prompt_tokens_total']} "
        f"(cached: {cl['stage1_cached_tokens_total']}, hit ratio: {_fmt(cl['stage1_cache_hit_ratio'])})",
    ]
    return "\n".join(lines) + "\n"


def render_compare(runs: list[tuple[dict, list[dict]]]) -> str:
    lines = [
        "| run | backend | jev_model | state_mode | n | overall_signal final acc "
        "| auto | verified | escalated | review |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for run_meta, rows in runs:
        m = compute_metrics(run_meta, rows)
        overall = m["per_question"].get("overall_signal", {})
        routes = m["routes"]
        acc = _fmt(overall.get("final_accuracy_vs_truth"))
        lines.append(
            f"| {run_meta.get('run_id', '-')} | {run_meta.get('backend')} | "
            f"{run_meta.get('jev_model')} | {run_meta.get('state_mode')} | {run_meta.get('n')} | "
            f"{acc} | {routes.get('auto', 0)} | {routes.get('verified', 0)} | "
            f"{routes.get('escalated', 0)} | {routes.get('review', 0)} |"
        )
    return "\n".join(lines) + "\n"
