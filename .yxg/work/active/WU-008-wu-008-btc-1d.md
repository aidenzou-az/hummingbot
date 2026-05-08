---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-008
slug: wu-008-btc-1d
title: WU-008: BTC 1d probability gap narrowed strategy candidate replay。基于 WU-006/WU-007 结果，只测试收窄候选策略，例如 A_edge/A_residual >= 8c 或 >=10c、buffer >= 8c、gamma/time/confidence/toxicity filter；做参数稳定性、bucket 稳定性、settlement 与 closeout 双口径回放，给出是否可进入 paper trading 的候选配置。明确 out of scope: 不做真实交易、不接 paper engine。
status: ready
priority: medium
owner_role: planner
created_at: "2026-05-05"
updated_at: "2026-05-05"
---

# Work Unit

## Objective

Evaluate a narrowed BTC 1d probability-gap strategy candidate using the model validation from WU-006 and execution filters from WU-007. The outcome should be a small set of explicit candidate configurations, tested on both closeout and settlement PnL, with a clear go/no-go decision for paper trading.

## In Scope

- Define narrowed candidate rules such as `A_edge` or `A_residual >= 8c/10c`, `buffer >= 8c`, gamma/time/confidence filters, and WU-007 toxicity/cancel filters.
- Run candidate replay over existing and newly sampled BTC 1d data.
- Evaluate both closeout PnL and settlement PnL when WU-006 labels are available.
- Evaluate parameter stability around candidate thresholds instead of optimizing one exact point.
- Evaluate bucket stability by side, gamma, time-to-expiry, moneyness, confidence, spread, edge/residual, and market date.
- Add concentration checks so results are not dominated by one or two trades.
- Produce a paper-trading go/no-go recommendation with explicit minimum evidence standards.

## Out Of Scope

- Paper trading engine implementation; that belongs to WU-009.
- Live trading, signing, real balances, or Polymarket order placement.
- Changing the fair-value model.
- Broad parameter search over all possible strategies; this task tests narrowed candidates only.
- Declaring profitability without enough complete markets and settlement-labeled trades.

## Expected Touch Points

- [controllers/generic/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_execution_replay.py:1)
- Candidate strategy replay/report module if needed.
- [scripts/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_execution_replay.py:1) or a new candidate replay CLI.
- [test/controllers/test_probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_execution_replay.py:1)
- `.yxg/data/probability_gap_samples_iv_v1.sqlite`
- `.yxg/work/active/WU-008-wu-008-btc-1d.md`

## Dependencies
- WU-006 model settlement validation should be complete or explicitly marked insufficient.
- WU-007 dynamic cancel/toxicity filters should be available.
- WU-005 baseline replay and cross-model diagnostics.
- At least 5-10 complete BTC 1d markets are preferred before a go decision.

## Assumptions
- Candidate rules should be few and explainable, not a broad overfit grid.
- If WU-006 settlement coverage is insufficient, this task can produce `no_go_more_sampling` rather than forcing a strategy.
- Paper trading should only be recommended if both closeout and settlement evidence are acceptable.

## Risks
- Current positive regions may disappear with more complete markets.
- Narrow rules can produce too few trades to evaluate.
- Dynamic cancel filters can create optimistic replay if fill/cancel timing is too favorable.
- A strategy that looks good on closeout may fail on final settlement.

## Plan

1. Import WU-006 model-validity conclusions and WU-007 execution-filter conclusions.
2. Define a small candidate set, including thresholds around `A_edge/A_residual >= 8c` and `>=10c`, `buffer >= 8c`, gamma/time/confidence filters, and cancel filters.
3. Implement candidate replay configs as named, reproducible strategy profiles.
4. Run each profile on closeout return horizons and settlement PnL.
5. Evaluate parameter neighborhoods around each candidate to test stability.
6. Evaluate concentration, per-market contribution, and outlier dependence.
7. Produce bucket reports by side, gamma, time-to-expiry, moneyness, edge/residual, confidence, spread, and market date.
8. Define paper-trading gate criteria and evaluate each candidate against them.
9. Add tests for candidate config parsing, replay determinism, stability aggregation, and go/no-go logic.
10. Write findings into this task artifact and either recommend WU-009 or more sampling/refinement.

## Verification

- Unit tests verify named candidate configs map to expected thresholds and filters.
- Unit tests verify candidate replay uses WU-006 settlement labels when present and does not mix proxy/official results silently.
- Unit tests verify WU-007 cancel filters can be enabled in candidate profiles.
- Unit tests verify parameter-neighborhood stability and concentration metrics.
- A local command outputs candidate-by-candidate closeout PnL, settlement PnL, trade count, concentration, and go/no-go.

## Done When

- A repeatable offline report evaluates the narrowed strategy candidates.
- The report states whether any candidate meets paper-trading criteria.
- If no candidate passes, the artifact states whether the next step is more sampling, model revision, or execution-filter revision.
- No paper trading code is implemented in this task.

## Escalate If

- WU-006 shows model edge is not valid enough to support a strategy.
- WU-007 shows toxicity cannot be reduced without eliminating fills.
- Candidate trade count is too low for a meaningful conclusion.
- Results are dominated by one market or one trade.
- The user wants to change thresholds beyond the narrowed candidate scope into a broad optimizer.

## Evidence Log

- WU-005 suggested `A_edge/A_residual >= 8c` as an observation threshold and `>=10c` as the stronger candidate area.
- WU-005 parameter grid showed `buffer=0.08` was the most promising region but had too few trades and high concentration.
- WU-005 fill toxicity analysis showed maker fills were worse than unfilled quote paths under the same edge bucket.

## Notes
- WU-008 is the gatekeeper for WU-009; it should not be bypassed unless the user explicitly accepts weaker evidence.
