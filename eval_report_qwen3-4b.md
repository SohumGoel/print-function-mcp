# Agent evaluation: Qwen/Qwen3-4B-Instruct-2507 (Colab L4, greedy decoding, 2026-11-06)

Run on commit 475c612. After this run, `radial_offset_mm` was added to `feature_position_check` and a follow-up hint to `layer_shift_impact`, because of the issues in cases 1 and 8 below.

| Metric | Value |
|---|---|
| tool_selection | 9/10 |
| arguments_exact | 8/8 |
| mean_tool_calls | 0.9 |
| mean_seconds_per_request | 9.0 |
| mean_tool_ms | 195.2 |
| total_tokens | 54005 |

| # | Expected | Called | Tool OK | Wrong args | Time (s) |
|---|---|---|---|---|---|
| 1 | feature_position_check | feature_position_check | ✅ | - | 17.6 |
| 2 | fastener_fit_check | fastener_fit_check | ✅ | - | 8.7 |
| 3 | fastener_fit_check | fastener_fit_check | ✅ | - | 7.7 |
| 4 | failure_waste | failure_waste | ✅ | - | 8.8 |
| 5 | failure_waste | failure_waste | ✅ | - | 8.9 |
| 6 | layer_shift_impact | layer_shift_impact | ✅ | - | 10.7 |
| 7 | continue_or_scrap | continue_or_scrap | ✅ | - | 11.0 |
| 8 | layer_shift_impact, continue_or_scrap | layer_shift_impact | ❌ | - | 8.3 |
| 9 | fastener_fit_check or none | fastener_fit_check (error surfaced) | ✅ | - | 6.3 |
| 10 | none | none | ✅ | - | 2.0 |

## Review of answers against tool outputs
- Case 1: correct verdict, but the answer calls 0.15 mm the "total deviation". The tool returned a 0.30 mm position zone diameter (2 × 0.15 radial offset). Wrong quantity in the prose.
- Case 3: converted 0.134 in to 3.402 mm (exact: 3.404); within the check tolerance.
- Case 4: says the cost includes "time", but machine cost was 0; adds advice the tool did not give.
- Case 5: all numbers match a hand calculation (full $6.38, wasted $2.23, 84 g, 4.9 h, 0.735 kWh), but calls the wasted filament "unused".
- Case 8: called only layer_shift_impact, saw the motor hole fail, and recommended scrapping without calling continue_or_scrap. The decision is reasonable (part non-functional, so p_usable ≈ 0), but it is not quantified.
- Cases 9–10: refused the unsupported M7 bolt and the off-topic question correctly.
