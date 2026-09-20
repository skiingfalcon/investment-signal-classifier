# Run: backend=typesafe jev_model=typesafe/jev-1.13 gen_model=gpt-5.6-terra

n=336 state_mode=derived verify=True escalate=True wall_s=581.2

## Routes

| route | n |
|---|---|
| auto | 265 |
| escalated | 68 |
| verified | 3 |

## Per-question accuracy

| question | n(stage1) | stage1 vs rules | CI | n(final) | final vs truth | CI |
|---|---|---|---|---|---|---|
| revenue_growth | 336 | 0.997 | 0.99-1.00 | 308 | 0.987 | 0.97-1.00 |
| profitability_trend | 336 | 0.997 | 0.99-1.00 | 336 | 0.964 | 0.94-0.98 |
| ocf_covers_net_income | 319 | 1.000 | 1.00-1.00 | 336 | 0.973 | 0.96-0.99 |
| eps_increased | 330 | 1.000 | 1.00-1.00 | 336 | 0.982 | 0.97-0.99 |
| leverage | 235 | 0.996 | 0.99-1.00 | 253 | 0.988 | 0.97-1.00 |
| liquidity | 336 | 0.997 | 0.99-1.00 | 225 | 0.942 | 0.91-0.97 |
| share_count | 336 | 0.997 | 0.99-1.00 | 280 | 0.836 | 0.79-0.88 |
| overall_signal | 336 | 0.979 | 0.96-0.99 | 308 | 0.977 | 0.96-0.99 |

## Agreement (stage2 / generative)

| question | stage2 n | stage2 kept jev | stage2 used rules | gen n | gen~jev | gen~rules | gen~neither |
|---|---|---|---|---|---|---|---|
| revenue_growth | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| profitability_trend | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| ocf_covers_net_income | 0 | 0 | 0 | 12 | 0 | 0 | 12 |
| eps_increased | 0 | 0 | 0 | 6 | 0 | 0 | 6 |
| leverage | 1 | 1 | 0 | 52 | 28 | 0 | 24 |
| liquidity | 1 | 1 | 0 | 1 | 1 | 1 | 0 |
| share_count | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| overall_signal | 1 | 1 | 0 | 21 | 19 | 21 | 0 |

## Extraction impact (model-sourced rows where extraction changed a label)

| id | changed | route | caught |
|---|---|---|---|
| GS:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T152253Z-extract-full | ocf_covers_net_income, profitability_trend | escalated | False |
| PLTR:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T152253Z-extract-full | share_count | auto | False |
| PG:FY2026-06-30:model:bonsai-2-27b-halo-vulkan/20260918T152253Z-extract-full | leverage | escalated | True |
| PLTR:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T154449Z-extract-full | share_count | auto | False |
| PG:FY2026-06-30:model:bonsai-2-27b-halo-vulkan/20260918T154449Z-extract-full | leverage | escalated | True |
| NEE:FY2025-12-31:model:bonsai-2-27b-halo-vulkan/20260918T154449Z-extract-full | share_count | auto | False |
| GS:FY2025-12-31:model:bonsai-2-27b-spark-cuda/20260918T204818Z-extract-full | ocf_covers_net_income, profitability_trend, share_count | escalated | False |
| PLTR:FY2025-12-31:model:bonsai-2-27b-spark-cuda/20260918T204818Z-extract-full | share_count | auto | False |
| PLTR:FY2025-12-31:model:bonsai-2-27b-spark-cuda/20260918T224057Z-extract-full | share_count | auto | False |
| PLTR:FY2025-12-31:model:deepseek-v4-flash-nothink-spark-cuda/20260919T121223Z-extract-full | share_count | escalated | False |
| MSFT:FY2026-06-30:model:gemma-4-31b-nothink-spark-cuda/20260919T202304Z-extract-full | share_count | auto | False |
| GS:FY2025-12-31:model:gemma-4-31b-nothink-spark-cuda/20260919T202304Z-extract-full | share_count | escalated | False |
| GS:FY2025-12-31:model:gemma-4-31b-spark-cuda/20260919T174420Z-extract-full | ocf_covers_net_income, share_count | escalated | False |
| PG:FY2026-06-30:model:glm-4.7-flash-spark-cuda/20260918T025412Z-extract-full | leverage | auto | True |
| CAT:FY2025-12-31:model:glm-4.7-flash-spark-cuda/20260918T025412Z-extract-full | share_count | auto | False |
| HD:FY2026-02-01:model:glm-4.7-flash-spark-cuda/20260918T025412Z-extract-full | share_count | auto | False |
| PLTR:FY2025-12-31:model:gpt-oss-120b-halo-rocm/20260913T044559Z-extract-full | share_count | auto | False |
| PG:FY2026-06-30:model:gpt-oss-120b-halo-rocm/20260913T044559Z-extract-full | leverage | auto | False |
| GS:FY2025-12-31:model:gpt-oss-120b-halo-vulkan/20260913T030643Z-extract-full | eps_increased | escalated | False |
| PLTR:FY2025-12-31:model:gpt-oss-120b-halo-vulkan/20260913T030643Z-extract-full | share_count | auto | False |
| AAPL:FY2025-09-27:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | auto | False |
| MSFT:FY2026-06-30:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | ocf_covers_net_income | escalated | False |
| GS:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | eps_increased, ocf_covers_net_income, profitability_trend, share_count | escalated | False |
| XOM:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | leverage, liquidity | auto | False |
| PLTR:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | auto | False |
| PG:FY2026-06-30:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | leverage | auto | True |
| CAT:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | auto | False |
| HD:FY2026-02-01:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | share_count | auto | False |
| STWD:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T030429Z-extract-full | eps_increased, ocf_covers_net_income, overall_signal, profitability_trend, revenue_growth, share_count | escalated | False |
| CAT:FY2025-12-31:model:gpt-oss-120b-spark-cuda/20260912T132250Z-extract-full | leverage, liquidity | auto | False |
| AAPL:FY2025-09-27:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | ocf_covers_net_income, share_count | escalated | False |
| MSFT:FY2026-06-30:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity | auto | False |
| GS:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | eps_increased, ocf_covers_net_income, profitability_trend, share_count | escalated | False |
| XOM:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity, share_count | auto | False |
| PLTR:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | share_count | auto | False |
| WMT:FY2026-01-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity | auto | False |
| PG:FY2026-06-30:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage | auto | True |
| NEE:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | leverage, liquidity, share_count | escalated | False |
| HD:FY2026-02-01:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | share_count | auto | False |
| STWD:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T022410Z-extract-full | eps_increased, ocf_covers_net_income, overall_signal, profitability_trend, revenue_growth, share_count | escalated | False |
| GS:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T135023Z-extract-full | ocf_covers_net_income, share_count | escalated | False |
| PLTR:FY2025-12-31:model:gpt-oss-20b-spark-cuda/20260912T135023Z-extract-full | share_count | auto | False |
| HD:FY2026-02-01:model:gpt-oss-20b-spark-cuda/20260912T135023Z-extract-full | ocf_covers_net_income, overall_signal, profitability_trend | escalated | False |
| GS:FY2025-12-31:model:laguna-s-2.1-spark-cuda/20260920T003059Z-extract-full | profitability_trend | escalated | False |
| GS:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | ocf_covers_net_income | escalated | True |
| XOM:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | leverage, liquidity | auto | False |
| PLTR:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | share_count | auto | False |
| HD:FY2026-02-01:model:nemotron-3-super-spark-cuda/20260915T122649Z-extract-full | leverage, liquidity, share_count | escalated | False |
| GS:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | ocf_covers_net_income | escalated | True |
| XOM:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | leverage, liquidity | auto | False |
| PLTR:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | share_count | auto | False |
| NEE:FY2025-12-31:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | liquidity, share_count | auto | False |
| HD:FY2026-02-01:model:nemotron-3-super-spark-cuda/20260916T103526Z-extract-full | leverage, liquidity, share_count | escalated | False |
| XOM:FY2025-12-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | leverage, liquidity | auto | False |
| NEE:FY2025-12-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | ocf_covers_net_income | escalated | False |
| INTU:FY2026-07-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | eps_increased, leverage, ocf_covers_net_income, overall_signal | escalated | False |
| STWD:FY2025-12-31:model:openai_gpt-5.6-terra/20260912T033135Z-extract-full | ocf_covers_net_income, overall_signal, profitability_trend, share_count | escalated | False |
| HD:FY2026-02-01:model:openai_gpt-5.6-terra/20260912T142344Z-extract-full | share_count | auto | False |
| MSFT:FY2026-06-30:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | overall_signal, revenue_growth, share_count | auto | False |
| GS:FY2025-12-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | ocf_covers_net_income, profitability_trend | escalated | False |
| XOM:FY2025-12-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | share_count | auto | False |
| WMT:FY2026-01-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | ocf_covers_net_income, overall_signal, profitability_trend | escalated | False |
| PG:FY2026-06-30:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | leverage | escalated | True |
| NEE:FY2025-12-31:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | leverage, share_count | escalated | False |
| HD:FY2026-02-01:model:qwen3.5-122b-a10b-spark-cuda/20260918T114214Z-extract-full | share_count | auto | False |
| GS:FY2025-12-31:model:qwen3.8-27b-halo-vulkan/20260915T145801Z-extract-full | share_count | escalated | False |
| XOM:FY2025-12-31:model:qwen3.8-27b-halo-vulkan/20260915T145801Z-extract-full | share_count | auto | False |
| HD:FY2026-02-01:model:qwen3.8-27b-halo-vulkan/20260915T145801Z-extract-full | share_count | auto | False |
| MSFT:FY2026-06-30:model:qwen3.8-27b-halo-vulkan/20260915T152312Z-extract-full | share_count | auto | False |
| HD:FY2026-02-01:model:qwen3.8-27b-halo-vulkan/20260915T152312Z-extract-full | share_count | auto | False |
| GS:FY2025-12-31:model:qwen3.8-27b-spark-cuda/20260915T024745Z-extract-full | share_count | escalated | False |

## Cost / latency

stage1 p50/p95 ms: 248.9/431.0  
stage2 p50/p95 ms: 216.5/381.9  
generative p50/p95 ms: 6869.3/10469.5  
stage1 prompt tokens total: 0 (cached: 0, hit ratio: -)  
JEV backend cost (stage1+stage2): $0.031935 (always 0 for the local llama.cpp backend; per-call billing for a hosted Jev backend)
