---
marp: true
paginate: true
title: Jev for investment signals
---

# Feedback first: thresholds are ML tuning

Jev returns probabilities and our code routes on thresholds, so **tuning those thresholds is ML tuning**, even with no training.

- 0.60 choice · 0.70 `overall_signal` · 0.50 leverage · 0.75 yes/no · 0.70 support: set by judgment, never tuned
- Tuned and reported on the same 336 rows → optimistic. We need a held-out set.
- Tied to one model build and one question wording. If either changes, re-validate.
- Each one is a trade-off, not a dial with a right answer.

**Next:** no threshold changes before the volume run · tune/hold-out split · the business's cost of a wrong signal

*Procedure, not firing arrows and then painting the target around them.*

<!--
Open with this, because the rest of the deck depends on thresholds.
These values came over from the email project (policy.py POLICY), and nobody fitted them to this data. The results that follow are reported on the same rows we looked at, so read them as optimistic.
With calibrated probabilities, the cost of a mis-route is the number that actually sets the threshold, and that number has to come from the business.
-->

---

# 10-K numbers in, investment signal out

**Jev decides. Arithmetic checks. Code routes.**

A generative model only handles what those can't settle.

<small>Code, data, and every run: [github.com/skiingfalcon/investment-signal-classifier](https://github.com/skiingfalcon/investment-signal-classifier)</small>

<!--
Same pattern as jev-email-cascade. The difference: the input is numeric, so a rule engine can compute the same labels exactly, which means we get ground truth for free.
336 company-years: 60 clean XBRL rows across 12 tickers, plus 276 rows that replay those companies through 23 10-K extraction runs.
-->

---

# What we send Jev

**State**: one company-year  
current + prior facts, `change_pct`, ratios

**Questions**: 8 typed questions, not a prompt

One pass. No text generated.  
A probability for every allowed answer.

<!--
state.py renders FactSet in USD millions with derived change_pct and ratios, so Jev never does the percent maths itself.
The question wording comes from rules.THRESHOLDS, so the prompt and the rule engine can't drift apart.
How the probabilities are produced depends on the backend. See "Two ways to run Jev".
-->

---

# The investment choices

| Question | Type | Options |
| --- | --- | --- |
| `revenue_growth` | Choice | growing · flat · declining |
| `profitability_trend` | Choice | improving · stable · deteriorating · loss_making |
| `ocf_covers_net_income` | Noul | yes / no |
| `eps_increased` | Noul | yes / no |
| `leverage` | Score | 0 low · 1 moderate · 2 high |
| `liquidity` | Choice | strong · adequate · thin |
| `share_count` | Choice | buyback · stable · dilution |
| `overall_signal` | Choice | **bullish · neutral · bearish** |

Choice = pick one · Score = place on a scale · Noul = P(yes), 0.5 = cannot tell

<!--
Every Choice also has "other" (data not reported), which is the escape hatch.
Thresholds (rules.THRESHOLDS): revenue ±3%, net income ±5%, shares ±1%, debt/equity 0.5x / 2.0x, cash/debt 25% / 100%.
overall_signal: check bearish first (loss, NI down ≥5%, or revenue down ≥3%). Then bullish (revenue up ≥3%, NI up ≥5%, EPS up). Anything else is neutral.
-->

---

# One company in → Jev out

**AAPL FY2025** (hosted Jev)

| | Jev | Rules |
| --- | --- | --- |
| revenue_growth | growing · 1.00 | growing |
| profitability_trend | improving · 1.00 | improving |
| ocf_covers_net_income | P(yes) 0.03 | no |
| eps_increased | P(yes) 0.99 | yes |
| leverage | 1 · 0.99 | 1 |
| liquidity | adequate · 1.00 | adequate |
| share_count | buyback · 1.00 | buyback |
| overall_signal | **bullish · 1.00** | **bullish** |

Confident **and** agrees on all 8 → `route = auto`

<!--
runs/20260920T161159Z/results.jsonl, first row. 2,168 input tokens, 483 ms, $0.00009.
Everything agrees, so nothing else runs. The next two slides cover what happens when they don't agree.
-->

---

# Why not just trust the confidence?

Confidence is the model **grading itself**.

STWD FY2021: Jev said **bullish at 0.99**. The truth was neutral.

So we get a second opinion that doesn't come from a model: **arithmetic**.

**Doubt moves a question to the next stage.**

<!--
The rule engine (rules.py) computes the same 8 labels from the same numbers. It is independent of Jev and costs nothing.
Auto needs two independent signals to agree: Jev is confident, and Jev matches the arithmetic.
"Doubt" means Jev is below its threshold, or Jev and the rules disagree.
-->

---

# Moving between stages

| Stage | Moves on when… | Why this stage next | Cost |
| --- | --- | --- | --- |
| **1** Jev + rules | not confident, or disagrees | could be Jev *or* the rules that's wrong | 1 call |
| **2** "Do the facts support Jev's claim?" | support < 0.70 and rules have no answer | only now is paying worth it | +1 call |
| **3** Frontier arbiter | bad output or 3-way split | stop guessing | $ per call |
| **4** Human review | — | — | a person |

Each stage only sees what the cheaper one couldn't settle.  
<small>Yes/no questions skip stage 2.</small>

<!--
Stage 1 → 2: a disagreement doesn't tell you who's wrong. The rules can be missing data or hit an edge case. So ask Jev one narrower question: is its own claim supported by the numbers? High support means keep Jev (verified). Low support means use the rules' answer if it has one (also verified).
Why Noul skips stage 2: a yes/no answer already is a probability, so there is no separate claim to test. It goes straight to the rules' answer.
Stage 2 → 3: neither Jev nor the rules can settle it. Only here do we call gpt-5.6-terra. It sees the state, Jev's answers, and the rules' answers, and must return strict JSON that passes Pydantic validation.
Stage 3 → 4: invalid output, or Jev, the rules, and the arbiter all disagree. Send it to a person.
Every threshold in this table is one of the numbers from slide 1.
-->

---

# Results: 336 company-years

| | qwen3.8-27b | TypeSafe Jev |
| --- | ---: | ---: |
| Routes | 8 auto · 306 verified · 22 review | 265 auto · 3 verified · 68 escalated |
| `overall_signal` final | 98.4% | 97.7% |
| Cost | $0 | $0.032 |
| Latency p50 | 15.3 s | 249 ms |

Same final accuracy. **Very different paths to get there.**

<!--
CIs overlap on overall_signal (97–100 vs 96–99), so treat it as a tie.
qwen: its raw yes/no answers agree with the arithmetic only 23% of the time, so almost every row goes through the rules fallback and ends up "verified". Its escalation arm was broken this run (auth), which is why it shows 0 escalations and 22 review.
TypeSafe: yes/no answers are 100% on stage 1. Most of its 68 escalations come from leverage (52).
The latency gap is most likely our own per-question HTTP overhead on the local path, not the model. We haven't instrumented it yet.
Source: docs/cto-brief.md, runs/*/report.md.
-->

---

# Where it breaks

The stages check **consistency**, not **truth**.

- **STWD FY2021:** the rules disagreed, but stage 2 asked Jev again and it said "supported" (0.81). Jev was kept and it was wrong.
- **Bad extraction:** Jev and the rules read the same wrong number and agree. Only 2.8% (qwen) / 11.3% (TypeSafe) were caught.
- **`share_count` 83.6%** on both backends: a data issue, not a model issue.

<!--
STWD: stage 2 isn't independent. It's the same model checking its own claim. On clean XBRL rows the rules are the truth, so overriding them can only hurt.
Extraction: 71 rows where an extractor's number changed a label. The double check can't catch an error that sits upstream of both readers.
share_count: EDGAR's diluted-shares figure is dated at the cover page, not the fiscal year end, so the fix belongs in xbrl.py.
-->

---

# Two ways to run Jev

| | qwen3.8-27b (local) | TypeSafe Jev (hosted) |
| --- | --- | --- |
| Runs on | llama.cpp on the Spark | OpenRouter · `typesafe/jev-1.13` |
| Probabilities | we read next-token label logits | Jev returns them natively |
| Calls per row | 8 (one per question) | 1 (all 8) |
| Cost | $0 marginal | billed per token |

Same facts, questions, rules, and policy. **Only the backend changes.**

<!--
qwen: Simple Jev pushes the model to the exact spot where its answer would start, then reads the probability of each allowed answer token. Nothing is generated. See jev/llamacpp_backend.py.
TypeSafe: one HTTPS call with the same {state, questions} body. It echoes back a dated build id (jev-1.13-20260917), which we record. Pin it with --model or runs won't reproduce.
Why run both: TypeSafe is the control. When the two disagree, we can tell "qwen caused this" apart from "the questions or policy caused this". Compare with `isc compare`.
-->

---

# Takeaway

Jev **decides**. Arithmetic **checks**. Code **routes**.  
Cost only rises when there's doubt.

The thresholds that define "doubt" are next, **done properly**.

<!--
Back to slide 1: tune/hold-out split, a mis-route cost from the business, and no changes before the volume run.
Also open: instrument the local latency, rethink stage 2 as an independent check, and fix the share_count source.
-->
