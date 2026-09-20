# Run: backend=typesafe jev_model=typesafe/jev-1.13 gen_model=gpt-5.6-terra

n=12 state_mode=derived verify=True escalate=True wall_s=10.6

## Routes

| route | n |
|---|---|
| auto | 10 |
| escalated | 2 |

## Per-question accuracy

| question | n(stage1) | stage1 vs rules | CI | n(final) | final vs truth | CI |
|---|---|---|---|---|---|---|
| revenue_growth | 12 | 1.000 | 1.00-1.00 | 11 | 1.000 | 1.00-1.00 |
| profitability_trend | 12 | 1.000 | 1.00-1.00 | 12 | 1.000 | 1.00-1.00 |
| ocf_covers_net_income | 12 | 1.000 | 1.00-1.00 | 12 | 1.000 | 1.00-1.00 |
| eps_increased | 12 | 1.000 | 1.00-1.00 | 12 | 1.000 | 1.00-1.00 |
| leverage | 9 | 1.000 | 1.00-1.00 | 9 | 1.000 | 1.00-1.00 |
| liquidity | 12 | 1.000 | 1.00-1.00 | 8 | 1.000 | 1.00-1.00 |
| share_count | 12 | 1.000 | 1.00-1.00 | 10 | 1.000 | 1.00-1.00 |
| overall_signal | 12 | 1.000 | 1.00-1.00 | 11 | 1.000 | 1.00-1.00 |

## Agreement (stage2 / generative)

| question | stage2 n | stage2 kept jev | stage2 used rules | gen n | gen~jev | gen~rules | gen~neither |
|---|---|---|---|---|---|---|---|
| revenue_growth | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| profitability_trend | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ocf_covers_net_income | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| eps_increased | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| leverage | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| liquidity | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| share_count | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| overall_signal | 0 | 0 | 0 | 1 | 1 | 1 | 0 |

## Cost / latency

stage1 p50/p95 ms: 218.9/385.3  
stage2 p50/p95 ms: 159.4/159.4  
generative p50/p95 ms: 3716.4/5164.9  
stage1 prompt tokens total: 0 (cached: 0, hit ratio: -)  
JEV backend cost (stage1+stage2): $0.001112 (always 0 for the local llama.cpp backend; per-call billing for a hosted Jev backend)
