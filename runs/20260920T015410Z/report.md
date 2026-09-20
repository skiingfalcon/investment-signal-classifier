# Run: backend=llamacpp jev_model=qwen3.8-27b gen_model=gpt-5.6-terra

n=336 state_mode=derived verify=True escalate=True wall_s=5183.1

## Routes

| route | n |
|---|---|
| auto | 8 |
| review | 22 |
| verified | 306 |

## Per-question accuracy

| question | n(stage1) | stage1 vs rules | CI | n(final) | final vs truth | CI |
|---|---|---|---|---|---|---|
| revenue_growth | 336 | 0.938 | 0.91-0.96 | 308 | 0.990 | 0.98-1.00 |
| profitability_trend | 336 | 0.997 | 0.99-1.00 | 336 | 0.967 | 0.95-0.99 |
| ocf_covers_net_income | 319 | 0.141 | 0.10-0.18 | 336 | 0.970 | 0.95-0.99 |
| eps_increased | 330 | 0.327 | 0.28-0.38 | 336 | 0.982 | 0.97-0.99 |
| leverage | 235 | 0.996 | 0.99-1.00 | 253 | 0.949 | 0.92-0.97 |
| liquidity | 336 | 0.985 | 0.97-1.00 | 225 | 0.947 | 0.92-0.97 |
| share_count | 336 | 1.000 | 1.00-1.00 | 280 | 0.836 | 0.79-0.88 |
| overall_signal | 336 | 0.899 | 0.86-0.93 | 308 | 0.984 | 0.97-1.00 |

## Agreement (stage2 / generative)

| question | stage2 n | stage2 kept jev | stage2 used rules | gen n | gen~jev | gen~rules | gen~neither |
|---|---|---|---|---|---|---|---|
| revenue_growth | 24 | 3 | 21 | 0 | 0 | 0 | 0 |
| profitability_trend | 2 | 1 | 1 | 0 | 0 | 0 | 0 |
| ocf_covers_net_income | 274 | 0 | 274 | 0 | 0 | 0 | 0 |
| eps_increased | 222 | 0 | 222 | 0 | 0 | 0 | 0 |
| leverage | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| liquidity | 6 | 1 | 5 | 0 | 0 | 0 | 0 |
| share_count | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| overall_signal | 54 | 26 | 28 | 0 | 0 | 0 | 0 |

## Extraction impact (model-sourced rows where extraction changed a label)

| id | changed | route | caught |
|---|---|---|---|
| GS:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T152253Z-extract-full | ocf_covers_net_income, profitability_trend | verified | False |
| PLTR:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T152253Z-extract-full | share_count | verified | False |
| PG:FY2026-06-30:model:bonsai-2-27b-halo-vulkan/20260918T152253Z-extract-full | leverage | verified | False |
| PLTR:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T154449Z-extract-full | share_count | verified | False |
| PG:FY2026-06-30:model:bonsai-2-27b-halo-vulkan/20260918T154449Z-extract-full | leverage | verified | False |
| NEE:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T154449Z-extract-full | share_count | verified | False |
| GS:FY2025-12-31:model:bonsai-2-27b-spark-cuda/20260918T204818Z-extract-full | ocf_covers_net_income, profitability_trend, share_count | verified | False |
| PLTR:FY2025-12-31:model:bonsai-2-27b-spark-cuda/20260918T204818Z-extract-full | share_count | verified | False |
| PLTR:FY2025-12-31:model:bonsai-2-27b-spark-cuda/20260918T224057Z-extract-full | share_count | verified | False |
| PLTR:FY2025-12-31:model:deepseek-v4-flash-nothink-spark-cuda/20260919T121223Z-extract-full | share_count | verified | False |
| MSFT:FY2026-06-30:model:gemma-4-31b-nothink-spark-cuda/20260919T202304Z-extract-full | share_count | verified | False |
| GS:FY2025-12-31:model:gemma-4-31b-nothink-spark-cuda/20260919T202304Z-extract-full | share_count | review | False |
| GS:FY2025-12-31:model:gemma-4-31b-spark-cuda/20260919T174420Z-extract-full | ocf_covers_net_income, share_count | review | False |
| PG:FY2026-06-30:model:glm-4.7-flash-spark-cuda/20260918T025412Z-extract-full | leverage | review | False |
| CAT:FY2025-12-31:model:glm-4.7-flash-spark-cuda/20260918T025412Z-extract-full | share_count | verified | False |
| HD:FY2026-02-01:model:glm-4.7-flash-spark-cuda/20260918T025412Z-extract-full | share_count | verified | False |
| PLTR:FY2025-12-31:model:gpt-oss-120b-halo-rocm/20260913T044559Z-extract-full | share_count | verified | False |
| PG:FY2026-06-30:model:gpt-oss-120b-halo-rocm/20260913T044559Z-extract-full | leverage | verified | False |
| GS:FY2025-12-31:model:gpt-oss-120b-halo-vulkan/20260913T030643Z-extract-full | eps_increased | review | False |
| PLTR:FY2025-12-31:model:gpt-oss-120b-halo-vulkan/20260913T030643Z-extract-full | share_count | verified | False |
| AAPL:FY2025-09-27:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | verified | False |
| MSFT:FY2026-06-30:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | ocf_covers_net_income | verified | False |
| GS:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | eps_increased, ocf_covers_net_income, profitability_trend, share_count | auto | False |
| XOM:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | leverage, liquidity | verified | False |
| PLTR:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | verified | False |
| PG:FY2026-06-30:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | leverage | review | False |
| CAT:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | verified | False |
| HD:FY2026-02-01:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | verified | False |
| STWD:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | eps_increased, ocf_covers_net_income, overall_signal, profitability_trend, revenue_growth, share_count | auto | False |
| CAT:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T132250Z-extract-full | leverage, liquidity | verified | False |
| AAPL:FY2025-09-27:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | ocf_covers_net_income, share_count | verified | False |
| MSFT:FY2026-06-30:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity | verified | False |
| GS:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | eps_increased, ocf_covers_net_income, profitability_trend, share_count | auto | False |
| XOM:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity, share_count | review | False |
| PLTR:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | share_count | verified | False |
| WMT:FY2026-01-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity | verified | False |
| PG:FY2026-06-30:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage | review | False |
| NEE:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity, share_count | verified | False |
| HD:FY2026-02-01:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | share_count | verified | False |
| STWD:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | eps_increased, ocf_covers_net_income, overall_signal, profitability_trend, revenue_growth, share_count | auto | False |
| GS:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T135023Z-extract-full | ocf_covers_net_income, share_count | review | False |
| PLTR:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T135023Z-extract-full | share_count | verified | False |
| HD:FY2026-02-01:model:gpt-oss-20b-spark-cuda/20260912T135023Z-extract-full | ocf_covers_net_income, overall_signal, profitability_trend | review | False |
| GS:FY2025-12-31:model:laguna-s-2.1-spark-cuda/20260920T003059Z-extract-full | profitability_trend | verified | False |
| GS:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | ocf_covers_net_income | verified | True |
| XOM:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | leverage, liquidity | verified | False |
| PLTR:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | share_count | verified | False |
| HD:FY2026-02-01:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | leverage, liquidity, share_count | verified | False |
| GS:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | ocf_covers_net_income | review | True |
| XOM:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | leverage, liquidity | verified | False |
| PLTR:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | share_count | verified | False |
| NEE:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | liquidity, share_count | verified | False |
| HD:FY2026-02-01:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | leverage, liquidity, share_count | verified | False |
| XOM:FY2025-12-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | leverage, liquidity | verified | False |
| NEE:FY2025-12-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | ocf_covers_net_income | auto | False |
| INTU:FY2026-07-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | eps_increased, leverage, ocf_covers_net_income, overall_signal | auto | False |
| STWD:FY2025-12-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | ocf_covers_net_income, overall_signal, profitability_trend, share_count | verified | False |
| HD:FY2026-02-01:model:openai_gpt-5.6-terra/20260912T142344Z-extract-full | share_count | verified | False |
| MSFT:FY2026-06-30:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | overall_signal, revenue_growth, share_count | review | False |
| GS:FY2025-12-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | ocf_covers_net_income, profitability_trend | verified | False |
| XOM:FY2025-12-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | share_count | verified | False |
| WMT:FY2026-01-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | ocf_covers_net_income, overall_signal, profitability_trend | review | False |
| PG:FY2026-06-30:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | leverage | verified | False |
| NEE:FY2025-12-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | leverage, share_count | verified | False |
| HD:FY2026-02-01:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | share_count | verified | False |
| GS:FY2025-12-31:model:qwen3.8-27b-halo-vulkan/20260915T145801Z-extract-full | share_count | verified | False |
| XOM:FY2025-12-31:model:qwen3.8-27b-halo-vulkan/20260915T145801Z-extract-full | share_count | verified | False |
| HD:FY2026-02-01:model:qwen3.8-27b-halo-vulkan/20260915T145801Z-extract-full | share_count | verified | False |
| MSFT:FY2026-06-30:model:qwen3.8-27b-halo-vulkan/20260915T152312Z-extract-full | share_count | verified | False |
| HD:FY2026-02-01:model:qwen3.8-27b-halo-vulkan/20260915T152312Z-extract-full | share_count | verified | False |
| GS:FY2025-12-31:model:qwen3.8-27b-spark-cuda/20260915T024745Z-extract-full | share_count | verified | False |

## Cost / latency

stage1 p50/p95 ms: 15286.4/15715.1  
stage2 p50/p95 ms: 1438.8/1757.8  
generative p50/p95 ms: 330.9/444.2  
stage1 prompt tokens total: 4107480 (cached: 4107480, hit ratio: 1.000)  
JEV backend cost (stage1+stage2): $0.000000 (always 0 for the local llama.cpp backend; per-call billing for a hosted Jev backend)
