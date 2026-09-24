---
marp: true
paginate: true
title: Jev for investment signals
style: |
  section { font-size: 26px; padding: 50px 70px; }
  h1 { font-size: 42px; }
  table { font-size: 21px; }
  small { font-size: 18px; }
---

# Feedback first: thresholds are ML tuning

Jev returns probabilities and our code routes on thresholds, so **tuning those thresholds is ML tuning**, even with no training.

- Our thresholds were set by judgment, never tuned on this data
- Tuning on the rows we report on → optimistic. We need a held-out set.
- Tied to one model build and one question wording. Change either → re-validate.
- Each one trades more auto-routing against more confident mistakes

**Next:** no threshold changes before the volume run · tune/hold-out split · the business's cost of a wrong signal

*Procedure, not firing arrows and then painting the target around them.*

<!--
Open with this, because the rest of the deck depends on thresholds.
The values (policy.py POLICY): 0.60 Choice confidence, 0.70 for overall_signal, 0.50 leverage, 0.75 yes/no, 0.70 stage-2 support. They came over from the email project, and nobody fitted them to this data. Results later in the deck are reported on the same rows, so read them as optimistic.
With calibrated probabilities, the cost of a mis-route is the number that actually sets the threshold, and that number has to come from the business.
-->

---

# 10-K numbers in, investment signal out

**Jev decides. Arithmetic checks. Code routes.**

A generative model only handles what those can't settle.

<small>Code, data, and every run: [github.com/skiingfalcon/investment-signal-classifier](https://github.com/skiingfalcon/investment-signal-classifier)</small>

<!--
Same pattern as jev-email-cascade. The difference: the input is numeric, so a rule engine can compute the same labels exactly, which means we get an answer key for free.
336 company-years: 60 clean XBRL rows across 12 tickers, plus 276 rows that replay those companies through 23 10-K extraction runs.
-->

---

# Why Jev? Why two levels?

**Why not a chat model?** It writes text: slow, billed per token, and the confidence it types isn't a probability.  
**Jev** reads once and returns real probabilities that code can route on.

**Why not just arithmetic?** Here it's the answer key. Real filings also have text (MD&A, footnotes) that arithmetic can't read, so we need to know how far Jev can be trusted.

**Why both?** Jev alone grades itself. Arithmetic alone can't judge.  
Auto only when **both agree**.

<!--
This slide holds the rest of the deck together.
Chat model: it can return JSON, but the number inside that JSON is text it generated, not a calibrated probability. It also pays for a decode step for every output token. Jev does one pass: 249 ms p50 for all 8 questions on the hosted build.
Arithmetic: we picked numeric questions on purpose so there is ground truth. That is how we can measure Jev at all. The questions worth automating later are the ones with no rule behind them.
Two levels: two independent signals. For an auto-route to be wrong, both have to be wrong the same way at the same time. Slide "What if a tier is missing?" puts numbers on it.
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

<small>Choice = pick one · Score = place on a scale · Noul = P(yes), 0.5 = cannot tell</small>

<!--
Every Choice also has "other" (data not reported), which is the escape hatch.
Thresholds (rules.THRESHOLDS): revenue ±3%, net income ±5%, shares ±1%, debt/equity 0.5x / 2.0x, cash/debt 25% / 100%.
overall_signal: check bearish first (loss, NI down ≥5%, or revenue down ≥3%). Then bullish (revenue up ≥3%, NI up ≥5%, EPS up). Anything else is neutral.
-->

---

# One company in → Jev out: AAPL FY2025

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
Hosted Jev, runs/20260920T161159Z/results.jsonl, first row. 2,168 input tokens, 483 ms, $0.00009.
P(yes) 0.03 means Jev is confident the answer is no, and the rules agree.
Everything agrees, so nothing else runs. The next slides cover what happens when they don't agree.
-->

---

# Why not just trust the confidence?

Confidence is the model **grading itself**.

STWD FY2021: Jev said **bullish at 0.99**. The truth was neutral.

So we check it against something that isn't a model: **arithmetic**.

**Doubt moves a question to the next stage.**

<!--
"Doubt" means Jev is below its threshold, or Jev and the rules disagree.
This is the "why two levels" from slide 3, shown on a real row.
-->

---

# Moving between stages

| Stage | Moves on when… | Why the next stage | Cost |
| --- | --- | --- | --- |
| **1** Jev + rules | not confident, or disagrees | either side could be wrong | 1 call |
| **2** Re-ask Jev, else take the rules' answer | still no answer | only now is paying worth it | +1 call |
| **3** Frontier arbiter | bad output or 3-way split | stop guessing | $ per call |
| **4** Human review | — | — | a person |

Each stage only sees what the cheaper one couldn't settle.

<small>Yes/no questions skip the re-ask and go straight to the rules' answer.</small>

<!--
Stage 1 → 2: a disagreement doesn't tell you who's wrong. The rules can be missing data. Stage 2 asks Jev one narrower question: are the numbers consistent with your answer? Support ≥ 0.70 keeps Jev. Otherwise it takes the rules' answer if the rules have one. Either way the route is "verified".
Yes/no: the answer already is a probability, so there's no separate claim to re-test.
Stage 2 → 3: nobody has an answer. Only now do we call gpt-5.6-terra. It sees the state, Jev's answers, and the rules' answers, and must return strict JSON that passes Pydantic validation.
Stage 3 → 4: invalid output, or Jev, the rules, and the arbiter all disagree. A person decides.
Every threshold in this table is one of the numbers from slide 1.
-->

---

# What if a tier is missing?

| Without… | What happens | In our runs |
| --- | --- | --- |
| **Rules check** | confident mistakes go straight through | qwen: **108 of 427** clean answers wrong, vs 0 |
| **Stage 2** | every dispute goes to the paid model | qwen: **306 more rows** billed |
| **Arbiter** | disputes wait for a person | qwen hit this: **22 rows** to review |
| **Human review** | 3-way splits get guessed | a wrong signal ships silently |

The tiers are insurance. **You don't know in advance which model you have.**

<!--
Rules check: "trust confidence" means accept every stage-1 answer that clears its threshold. On the 60 clean XBRL rows (427 scoreable answers), qwen got 108 wrong that way, mostly its yes/no answers. With the cascade it got 0 wrong. On clean rows the rules are the truth, so 0 is expected, not impressive. The 108 is the point.
Hosted Jev barely needed it on clean rows (5 wrong either way). On extraction-damaged rows the fallback made it slightly worse (78 → 95 wrong), because the rules follow the bad number too. See "Where it breaks".
Stage 2: with verify off, stage 2's disputes skip the rules fallback and go to the arbiter. For qwen that is the 306 "verified" rows (583 answers).
Arbiter: qwen's escalation arm was broken this run (auth), so 22 rows went to review. That is the measured cost of losing that tier. For hosted Jev it would be 68 rows (20%).
Human: an arbiter that returns invalid output, or disagrees with both, would otherwise be accepted as-is.
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
qwen: its raw yes/no answers agree with the arithmetic only 23% of the time, so almost every row goes through the rules fallback and ends up "verified".
TypeSafe: yes/no answers are 100% on stage 1. Most of its 68 escalations come from leverage (52).
The latency gap is most likely our own per-question HTTP overhead on the local path, not the model. We haven't instrumented it yet.
Source: docs/cto-brief.md, runs/*/report.md.
-->

---

# Where it breaks

The stages check **consistency**, not **truth**.

- **Stage 2's re-ask** kept Jev's answer 5 times, and **all 5 were wrong** (STWD included). The rules fallback did the real work.
- **Bad extraction:** Jev and the rules read the same wrong number and agree. Only 2.8% (qwen) / 11.3% (TypeSafe) were caught.
- **`share_count` 83.6%** on both backends: a data issue, not a model issue.

<!--
Re-ask: it's the same model checking its own claim, so it isn't independent. All 5 were on clean XBRL rows, where the rules are the truth, so overriding the rules can only hurt there. Keep the fallback, rethink the re-ask. Across both runs the fallback resolved 585 answers.
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
Also open: rethink the stage-2 re-ask as an independent check, instrument the local latency, and fix the share_count source.
-->
