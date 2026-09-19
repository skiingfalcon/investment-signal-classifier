# investment-signal-classifier

A numbers-driven investment-signal classifier built on three sibling projects:

- **[simple-jev](../)** — the "Simple Jev" logit classifier: one shared context plus N typed
  questions (`choice` / `score` / `noul`); the model is pushed to the exact position where its
  answer would start, and the classifier reads the probability it assigns to each allowed answer
  token there. No text is ever generated. This project adds a **llama.cpp backend** for it
  (`src/isc/jev/`) alongside the existing `hf-server` (torch/transformers) reference backend.
- **[llama-cpp-spark](../../llama-cpp-spark)** — has already extracted 11 XBRL financial facts
  from the latest 10-K of 12 companies with 14 model runs on a DGX Spark. This project reads that
  corpus and those extraction results directly; it does not re-extract anything.
- **[jev-email-cascade](../../jev-email-cascade)** — the pattern this project's cascade and
  evaluation harness follow: a typed decision model decides, plain code routes, a generative model
  handles what the decision model and a rule check could not resolve, and every run is scored
  against ground truth with bootstrapped confidence intervals.

## The idea

State = the extracted financial facts for one company-fiscal-year (current + prior). Instead of
asking Jev to read prose, it answers direction/health judgments — *is revenue growing, is the
company more or less leveraged, is the overall signal bullish or bearish* — straight from the
numbers. Because the state is numeric, a **deterministic rule engine** (`isc/rules.py`) computes
the same eight labels from arithmetic. That gives free, exact ground truth, which is what makes a
real "double check" possible:

1. **Stage 1** — Jev answers all eight questions in one shared-prefix call. An answer is accepted
   if it clears its confidence threshold and either agrees with the rule engine or the rule engine
   has no opinion (missing data).
2. **Stage 2** (optional) — for every disputed question, one more Jev call asks a `noul`: *do the
   facts support Jev's stage-1 claim?* High support accepts Jev's answer; low support falls back
   to the rule engine's answer when it has one.
3. **Escalation** (optional) — whatever is still unresolved goes to a generative arbiter with the
   full picture — state, Jev's answers, the rule engine's answers — and a `strict` JSON-schema
   `response_format`, validated with Pydantic before anything is trusted. By default the arbiter
   is a **hosted frontier model** (gpt-5.6-terra over the real OpenAI API), not a second local
   model: the Spark keeps one large model resident at a time, and the arbiter only fires on
   disputed questions, so it isn't worth reserving Spark memory for it. `GenerativeArbiter` can
   still be pointed at a second local llama-server (`provider="local"`) on a box with capacity
   to spare.

Every row ends up routed `auto` / `verified` / `escalated` / `review`, and the report
(`isc/report.py`) breaks accuracy, agreement, and cost down by question, plus an
**extraction-impact** table: how often an upstream 10-K extraction error actually changed a label,
and whether the cascade caught it.

## Layout

```
src/isc/
  xbrl.py, facts.py         load EDGAR XBRL + extraction runs into FactSet, derive ratios
  rules.py                  THRESHOLDS + the deterministic label(fs) ground truth
  questions.py              the 8 Jev questions, worded from THRESHOLDS; stage-2 claims
  state.py                  FactSet -> the `state` object sent to Jev
  backends.py               Answer/DecisionResult/DecisionBackend, JevBackend, MockBackend
  jev/                      llama.cpp Simple Jev backend (llama_server.py, model_profiles.py,
                             llamacpp_backend.py) -- see its module docstrings for the mechanics
  policy.py, verify.py      the 3-stage resolution + the generative arbiter
  pipeline.py, report.py    run orchestration, run-dir artifacts, metrics + Markdown report
  cli.py                    `isc facts|show|questions|run|report|compare|jev classify`
```

## Running it

Everything below runs **on the machine that also runs llama-cpp-spark** (the DGX Spark in the
reference setup); this repo has no GPU dependency of its own and never needs the corpus copied
elsewhere.

```bash
uv sync
cp env.example .env   # set OPENAI_API_KEY; adjust ISC_SPARK_REPO if not a sibling checkout

# 1. Build the eval set: ~60 XBRL company-years (exact labels) plus every committed extraction run.
uv run isc facts --source xbrl --years 5 --source model:all --out data/facts.jsonl

# 2. Serve the Jev backend (from the llama-cpp-spark checkout). Only one local model is needed --
#    the escalation arbiter is a hosted frontier model, not a second resident server.
uv run local-llm serve qwen3.8-27b   # :8084

# 3. Run the cascade.
uv run isc run --backend llamacpp --verify --escalate

# 4. Report / compare runs.
uv run isc report runs/<stamp> --markdown
uv run isc compare runs/<stamp-a> runs/<stamp-b> --markdown
```

Escalated rows call a real hosted API and cost real money, but only fire on disputed questions
that stage 1 and stage 2 couldn't resolve — most rows never reach it. To use a second local
llama-server instead (on a box with memory to spare), set `ISC_GEN_PROVIDER=local` and
`ISC_GEN_BASE_URL` in `.env`.

Without a GPU, `--backend mock` runs the exact same pipeline and policy against a backend that
answers the rule-engine label with a configurable chance of a low-confidence wrong answer — enough
to exercise every route offline (see `tests/test_pipeline_mock.py`).

`uv run isc jev classify examples/bicycle.json --model qwen3.8-27b` sends a raw request straight
to the llama.cpp backend, bypassing the financial-facts pipeline entirely — useful for checking the
backend against the classic Simple Jev "bicycle" example from `common/PROMPT_STRUCTURE_V1.md`.

## Testing

```bash
uv run pytest -q       # 73 tests, no network, no GPU
uv run ruff check src tests
uv run ruff format --check src tests
```

`tests/fixtures/sec_data/{ACME,BETA}/companyfacts.json` is a small hand-built synthetic EDGAR
corpus (restated facts, an alias-only revenue concept, negative equity, zero long-term debt,
missing-tag coverage gaps) at realistic whole-dollar 10-K magnitudes, plus
`tests/fixtures/results_mini.jsonl`, a miniature extraction run with a wrong, an off-by-scale, and
a missing (`parsed: null`) value — enough to exercise every branch of `facts.py`, `rules.py`, and
the extraction-impact report without touching the real corpus.

## Known limitations

- The eval set is small (~60 XBRL company-years across 12 tickers), and large-cap growth years
  dominate it; treat the bootstrap confidence intervals in the report as the real result, not the
  point estimates.
- `gpt-oss-120b` is marked experimental as a *Jev* backend (`isc/jev/model_profiles.py`): its
  harmony chat template wants to emit an analysis channel before any answer, which fights the
  forced-answer-prefix trick Simple Jev depends on. It remains a valid choice for the generative
  arbiter's `provider="local"` fallback, where it decodes normally.
- The hosted-frontier arbiter is not bit-reproducible run to run: frontier reasoning models do
  not consistently support a fixed `temperature`/`seed` (the same finding llama-cpp-spark
  documents for its own SEC eval harness), unlike local JEV/mock rows.
- A label missing from a branch's top-`k` logprobs is scored on a floor value and reported in
  `metrics.missing_labels`, not silently ignored; see `jev/llamacpp_backend.py` for exactly when
  that can and cannot change an answer.
