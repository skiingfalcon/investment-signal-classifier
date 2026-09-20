import pytest

from isc.report import compute_metrics, cost_latency_metrics, render_compare, render_markdown

RUN_META = {
    "backend": "mock",
    "jev_model": "mock-jev",
    "gen_model": None,
    "n": 2,
    "state_mode": "derived",
    "verify": True,
    "escalate": False,
    "wall_s": 0.1,
}


def _outcome(jev, rules, final, resolved_by, agree=None):
    return {
        "jev": jev,
        "jev_conf": 0.9,
        "rules": rules,
        "agree_jev_rules": agree if agree is not None else jev == rules,
        "support_jev": None,
        "generative": None,
        "final": final,
        "resolved_by": resolved_by,
        "reasons": [],
    }


ROWS = [
    {
        "id": "A",
        "ticker": "ACME",
        "source": "xbrl",
        "stage1": {
            "latency_ms": 10.0,
            "metrics": {"prompt_n_total": 100, "cached_tokens_total": 80},
        },
        "stage2": None,
        "generative": None,
        "labels": {"truth": {"overall_signal": "bullish"}, "extraction_changed_label": []},
        "decision": {
            "route": "auto",
            "outcomes": {"overall_signal": _outcome("bullish", "bullish", "bullish", "stage1")},
        },
    },
    {
        "id": "B",
        "ticker": "BETA",
        "source": "model:run1",
        "stage1": {
            "latency_ms": 12.0,
            "metrics": {"prompt_n_total": 100, "cached_tokens_total": 90},
        },
        "stage2": {"latency_ms": 5.0},
        "generative": None,
        "labels": {
            "truth": {"overall_signal": "bearish"},
            "extraction_changed_label": ["overall_signal"],
        },
        "decision": {
            "route": "verified",
            "outcomes": {"overall_signal": _outcome("bearish", "neutral", "bearish", "stage2")},
        },
    },
]


def test_compute_metrics_accuracy_and_routes():
    m = compute_metrics(RUN_META, ROWS)
    assert m["routes"] == {"auto": 1, "verified": 1}
    oq = m["per_question"]["overall_signal"]
    assert oq["n_final_comparable"] == 2
    assert oq["final_accuracy_vs_truth"] == 1.0
    assert m["cost_latency"]["stage1_cache_hit_ratio"] == (80 + 90) / (100 + 100)


def test_extraction_impact_lists_changed_rows_and_whether_caught():
    m = compute_metrics(RUN_META, ROWS)
    assert len(m["extraction_impact"]) == 1
    item = m["extraction_impact"][0]
    assert item["id"] == "B"
    assert item["caught"] is True  # final "bearish" matches truth despite rules saying "neutral"


def test_render_markdown_produces_headings():
    text = render_markdown(RUN_META, ROWS)
    assert "# Run:" in text
    assert "## Per-question accuracy" in text
    assert "## Extraction impact" in text


def test_render_compare_produces_a_table_row_per_run():
    text = render_compare(
        [(dict(RUN_META, run_id="r1"), ROWS), (dict(RUN_META, run_id="r2"), ROWS)]
    )
    assert text.count("| r1 ") == 1
    assert text.count("| r2 ") == 1


def test_render_compare_shows_cost_and_no_warning_when_runs_match():
    local_meta = dict(RUN_META, run_id="local", backend="llamacpp")
    text = render_compare([(local_meta, ROWS), (dict(RUN_META, run_id="local2"), ROWS)])
    assert "cost usd" in text
    assert "| 0.000000 |" in text  # no jev_backend_metrics on these fixtures -> zero cost
    assert "warning" not in text


def test_render_compare_warns_on_mismatched_questions_hash():
    hosted_rows = [dict(r) for r in ROWS]
    local_meta = dict(RUN_META, run_id="local", questions_hash="abc123")
    hosted_meta = dict(RUN_META, run_id="hosted", questions_hash="def456")
    text = render_compare([(local_meta, ROWS), (hosted_meta, hosted_rows)])
    assert "warning: questions_hash differs" in text


def test_cost_latency_metrics_sums_jev_cost_and_flags_estimation():
    rows = [
        {
            "stage1": {"latency_ms": 1.0, "metrics": {"cost_usd": 0.01, "cost_estimated": False}},
            "stage2": {"latency_ms": 1.0, "metrics": {"cost_usd": 0.002, "cost_estimated": True}},
            "generative": None,
        }
    ]
    cl = cost_latency_metrics(rows)
    assert cl["jev_cost_usd"] == pytest.approx(0.012)
    assert cl["jev_cost_estimated"] is True
