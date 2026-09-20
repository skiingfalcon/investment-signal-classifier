# Investment signals: local qwen3.8-27b vs TypeSafe's hosted Jev — CTO brief

*Measured 2026-09-20 on the same 336 company-years (60 clean XBRL rows across 12 tickers, plus
276 rows replaying those same 12 companies through 23 different 10-K extraction runs to measure
extraction damage), the same 8 typed questions, the same rule engine, the same policy, the same
scoring code. Runs: [`runs/20260920T015410Z`](../runs/20260920T015410Z/report.md) (local
llama.cpp, qwen3.8-27b) and [`runs/20260920T161159Z`](../runs/20260920T161159Z/report.md)
(TypeSafe's hosted Jev, via OpenRouter). Reproduce with `uv run isc compare
runs/20260920T015410Z runs/20260920T161159Z --markdown`.*

## The elevator pitch

**On the final investment signal, the two backends are statistically indistinguishable — 98.4%
vs 97.7% — and on the 60 rows with clean numbers, the free local model made zero mistakes while
the paid hosted one made one.** They get there by different routes: qwen's raw judgment on two
specific yes/no questions is close to a coin flip, fully absorbed by the rule-engine fallback the
cascade already has for that case; the hosted Jev's raw judgment is excellent on those same two
questions but stumbles on the one ordered-scale question, which is what drives most of its paid
escalations. The one number that isn't close is **latency: the hosted call for all 8 questions
takes ~250ms; the local path takes ~15 seconds for the same 8 questions on the same hardware that
serves qwen fast for everything else.** The leading suspect is this project's own per-question
HTTP overhead, not the model, but that overhead hasn't been directly instrumented yet — it's
called out below as the thing to check, not as an already-confirmed diagnosis.

## The three question types, and how each backend did

Every row answers the same 8 questions, each one of three types (see
[`questions.py`](../src/isc/questions.py)):

- **Choice** — pick one option from a fixed list (`revenue_growth`, `profitability_trend`,
  `liquidity`, `share_count`, `overall_signal`), returned with a confidence.
- **Score** — a position on an ordered scale, 3 levels (`leverage`: 0 = low debt/equity, 2 =
  high or negative equity), returned as a probability-weighted expectation across the levels.
- **Noul** — a yes/no question answered as a *probability* (`ocf_covers_net_income`,
  `eps_increased`). 0.5 means "cannot tell," not "somewhat."

| question type | raw stage-1 agreement w/ rules: qwen | typesafe Jev | **final accuracy vs truth: qwen** | **typesafe Jev** |
| --- | ---: | ---: | ---: | ---: |
| **Choice** (5 questions, mean) | 96.4% | 99.3% | 94.5% | 94.1% |
| **Score** — `leverage` | 99.6% | 99.6% | 94.9% | 98.8% |
| **Noul** (2 questions, mean) | **23.4%** | **100.0%** | 97.6% | 97.8% |

The Noul row is the whole story in one line: qwen's raw stage-1 answer on "does operating cash
flow cover net income" and "did diluted EPS increase" agrees with plain arithmetic barely more
often than chance, while TypeSafe's real Jev gets it right essentially every time. Yet the
**final** accuracy on those two questions ends up nearly identical (97.6% vs 97.8%), because a
disputed Noul has nowhere to hide in this cascade: it skips the Stage 2 re-ask (a Noul answer is
already a probability, with no separate claim to test support for) and falls straight through to
the rule engine's arithmetic. qwen's specific weakness is real, and free to fix in software.

## Scorecard

| | **qwen3.8-27b** (local, llama.cpp on the Spark) | **TypeSafe Jev** (hosted, via OpenRouter) | edge |
| --- | ---: | ---: | :--- |
| **Cost, 336 rows** | $0.00 | $0.032 | qwen, trivially |
| **Cost per 1M rows** | $0 + our Spark's power/time | ~$95 | qwen |
| **Stage-1 latency, p50 / p95** | 15,286 / 15,715 ms | 249 / 431 ms | **TypeSafe, 60x** |
| **Wall time, 336 rows** | 86.4 min | 9.7 min | **TypeSafe, 8.9x** |
| **`overall_signal` final accuracy** | 98.4% (CI 97–100) | 97.7% (CI 96–99) | tie (CIs overlap) |
| **`overall_signal`, clean-XBRL rows only** | **0 misses / 55** | 1 miss / 55 | qwen, on this run |
| **Confidence on the one hosted clean-data miss** | n/a | 0.99 — *confidently wrong* | qwen |
| **Auto-routed, clean-XBRL rows, zero-error rate** | 2/2 | 49/49 | tie |
| **Auto-routed, extraction-affected rows, zero-error rate** | 0/6 | 179/216 | not a fair comparison — see caveats |
| **Extraction errors "caught" by the double check** | 2/71 (2.8%) | 8/71 (11.3%) | TypeSafe |
| **Escalations to the frontier arbiter** | 0 (see caveats — arm was broken this run) | 68/336, driven mostly by `leverage` | — |
| **Calls per row, stage 1** | 8 `/completion` calls (measured) + un-instrumented `/apply-template`/`/tokenize` calls per question | 1 HTTP call for all 8 questions | **TypeSafe** |
| **Errors (excluding the known auth issue)** | 0 | 0 | |

## What this means

1. **Final accuracy is a wash, for opposite reasons on each side.** qwen's weakness is
   calibration on two specific Noul questions; TypeSafe's weakness is the one Score question
   (`leverage` alone accounts for 52 of its 68 escalations). Neither weakness survives to the
   final number, because the cascade's job is exactly to catch this kind of thing. Read the
   Scorecard's accuracy row as "the double check is working," not as "the two models are equally
   good at reading a balance sheet" — they are not, in either direction, and the type-level table
   above is where that actually shows.

2. **The real cost difference is latency, and the leading suspect is our own code, not either
   model.** Qwen serves everything else on the Spark fast; the recorded metrics show 8
   `/completion` calls per row (one per question, as designed) taking a median 15.3 seconds
   combined, versus TypeSafe's single call answering all 8 questions in 249ms. Each of those 8
   calls is itself preceded by an `/apply-template` call and one `/tokenize` call per candidate
   answer label — real HTTP round trips this project's compiler makes but doesn't currently
   count anywhere, so the exact overhead isn't measured yet, only the total wall time is. Before
   concluding the model is slow, `llamacpp_backend.py`'s round-trip count per row should be
   instrumented directly; batching the tokenize calls and reusing one rendered template across a
   row's questions is the fix if that's confirmed. Until it's diagnosed, "free" local inference
   costs 9x the wall-clock time of a paid API call.

3. **On the one dataset that isn't muddied by extraction noise, the free model won.** Of the 60
   clean-XBRL rows, 55 have a determinate `overall_signal` truth (the other 5 are missing data
   on both sides); qwen made zero mistakes on those 55, TypeSafe's hosted Jev made one — and it
   is worth naming precisely, because it is the one finding here
   that should make anyone nervous about trusting a single confidence score: STWD's FY2021 10-K,
   real Jev said `bullish` at **0.99 confidence**, the rule engine correctly said `neutral`, and
   the Stage 2 support re-ask **validated Jev's wrong claim instead of catching it** — the one
   place in 336 rows where both the confidence score and the double check agreed with each other
   and both were wrong. One data point is not a verdict on either backend, but it is exactly the
   failure mode the whole cascade design exists to make rare, and it happened on the side with
   the reportedly-calibrated probabilities, not the side with logits read out of an open model.

4. **The double check's real blind spot is upstream extraction error, not model disagreement,
   and it is a small one either way.** Of 71 rows where a 10-K extractor's number changed a label
   versus the true XBRL value, the cascade caught it — final answer matched truth despite the
   rule engine being fed a bad number — only 2.8% of the time on qwen and 11.3% on TypeSafe. The
   reason is structural, not a backend defect: when an extractor mis-reads a number, both Jev and
   the rule engine see the *same* wrong number and agree with each other, confidently. This
   double check validates internal consistency between two systems reading the same state; it was
   never designed to catch a state that is wrong before either one sees it.

5. **One accuracy floor is a data-quality issue, not a backend issue, and it is worth saying so
   plainly.** `share_count` sits at 83.6% final accuracy for *both* backends — identical to three
   decimal places on this run, because both backends agree with the rule engine every single time
   it has an opinion; the ~16% error rate is baked into the input, not the judgment. EDGAR tags
   diluted shares outstanding as of the 10-K's cover-page filing date, not the fiscal year end, so
   the rule engine's YoY share-count comparison is systematically off by however many shares moved
   between those two dates. No amount of Jev calibration fixes this; the fix is in `xbrl.py`'s
   selection of which shares figure to use.

## Caveats, stated plainly

- 60 clean-XBRL rows, 12 tickers, up to 5 fiscal years each, single run each backend. Enough to
  see the Noul calibration gap and the latency gap clearly; not enough to certify a 0.7-point
  accuracy difference, and the "1 clean-data miss" finding above is n=1 — a second run could
  easily show zero or two.
- **The qwen run's escalation arm did not actually work.** Every one of its 22 `review`-routed
  rows was a `401 Unauthorized` from the frontier arbiter's API key, not a genuine three-way
  split. Its "0 escalated" is an auth failure, not evidence that qwen needs the arbiter less than
  TypeSafe's Jev does — we do not yet have a fair comparison of the two backends' *escalation*
  behaviour, only of what happens before escalation.
- 276 of the 336 rows are the same 12 companies replayed through 23 different 10-K extraction
  runs (`model:*` sources), specifically to measure extraction damage, not to add more investment
  signal. The "auto-routed, extraction-affected" row in the Scorecard is there to show that
  distinction matters — it is not a fair backend comparison, since it's dominated by which
  extractor produced the row, not which Jev backend read it.
- TypeSafe's cost is what OpenRouter actually billed (`usage.cost` was present on every row, not
  estimated). qwen's is genuinely $0 marginal, excluding the Spark's power and the engineering
  time already sunk into the llama.cpp backend — the same caveat jev-email-cascade states for its
  own open-weight option.
- The type-level Noul gap (23% vs 100% raw agreement) has not been root-caused. It could be a
  prompt/label-boundary issue specific to how this project's compiler forces qwen's next-token
  read (worth checking against the `hf-server` reference backend or a different local model), or
  it could be a genuine qwen limitation on this style of direct-comparison question. Either way,
  it is currently invisible in the final numbers only because the cascade happens to have a
  no-cost fallback for exactly this case.

## Ask

1. **Fix the frontier arbiter's API key and re-run the qwen path** before drawing any conclusion
   about which backend needs escalation more — right now that comparison doesn't exist.
2. **Root-cause the Noul calibration gap.** It's currently free to ignore because the rule-engine
   fallback absorbs it, but that fallback only exists because these particular Noul questions
   happen to be directly checkable from the same numbers already in the state. A future Noul
   question judged on qualitative text (sentiment, disclosure tone) would have no such fallback,
   and this gap would show up directly in the final answer.
3. **Instrument and then fix the local path's latency.** At today's ~15s/row, a full
   12-ticker × 5-year batch (60 rows) costs about 15 minutes wall clock for something the hosted
   API answers in under 20 seconds total. Add a round-trip counter to `llamacpp_backend.py`
   before assuming the fix is batching tokenize calls — that's the leading theory, not yet the
   confirmed cause.
4. **Fix `xbrl.py`'s shares-outstanding date mismatch** before trusting `share_count` on either
   backend; right now no Jev, local or hosted, can clear an 83.6% ceiling that's set by the input
   data.
