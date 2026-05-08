---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-007
slug: wu-007-btc-1d
title: WU-007: BTC 1d probability gap fill toxicity model 与 dynamic cancel replay。基于 WU-005 的 maker adverse selection 结论，建模 quote 被触达/成交的毒性，加入 quote lifecycle、撤单规则、post quote 5s/15s/30s re-evaluate、fair/mid/spot/gamma 变化触发撤单，目标是减少 toxic fill。明确 out of scope: 不接真实订单、不签名、不做 paper trading。
status: ready
priority: medium
owner_role: planner
created_at: "2026-05-05"
updated_at: "2026-05-05"
---

# Work Unit

## Objective

Build a fill-toxicity model and dynamic quote-cancel replay for BTC 1d maker execution. The outcome should treat quote touch/fill as potentially adverse information, simulate quote lifecycle decisions before fill, and measure whether dynamic cancel rules reduce toxic fills without destroying all useful opportunities.

## In Scope

- Model fill toxicity conditional on `A_edge`, `A_residual`, gamma, time-to-expiry, moneyness, spread, fair change, mid movement, and spot/reference movement.
- Add quote lifecycle replay states: quote placed, quote updated, quote canceled, quote touched, quote filled, quote expired.
- Add re-evaluation checkpoints after quote placement at 5s, 15s, and 30s.
- Add cancel rules for adverse fair movement, Polymarket mid moving toward quote too quickly, spot/reference risk, gamma escalation, edge decay, and stale quote age.
- Compare static maker-first replay against dynamic cancel replay using fill rate, toxic fill rate, missed favorable fills, closeout return, and settlement return when available.
- Keep all execution simulation offline and deterministic over stored snapshots.
- Produce bucket reports showing which cancel rules reduce toxicity and which remove too many good opportunities.

## Out Of Scope

- Real Polymarket orders, signing, API keys, cancellations, or balances.
- Paper trading account state; that belongs to WU-009.
- Changing `iv_digital_v1` fair-value model.
- Final narrowed strategy recommendation; that belongs to WU-008.
- Full websocket/CLOB depth migration unless a minimal optional hook is needed for future size fields.

## Expected Touch Points

- [controllers/generic/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_execution_replay.py:1)
- A new quote lifecycle replay module if separation is cleaner.
- [scripts/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_execution_replay.py:1) or a new dynamic-cancel replay CLI.
- [test/controllers/test_probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_execution_replay.py:1) or a new test file for quote lifecycle behavior.
- `.yxg/data/probability_gap_samples_iv_v1.sqlite`
- `.yxg/work/active/WU-007-wu-007-btc-1d.md`

## Dependencies
- WU-005 maker-first replay and adverse selection diagnostics.
- Prefer WU-006 settlement labels for final PnL validation, but WU-007 can start with closeout-only metrics if settlement labels are unavailable.
- Existing top-of-book snapshot cadence; stronger queue modeling requires future size/depth data.

## Assumptions
- Snapshot cadence is sufficient for first-pass quote lifecycle replay, but exact queue position cannot be modeled.
- A quote touched within the replay window is a useful proxy for fill risk.
- Dynamic cancel rules should be evaluated for both toxicity reduction and missed opportunity cost.

## Risks
- Cancellation rules can overfit to current few markets.
- Snapshot intervals may miss fast touch/cancel sequences.
- Without size/depth, fill probability remains approximate.
- Aggressive cancel rules may reduce all fills and create false comfort.

## Plan

1. Define quote lifecycle states and transition rules for offline replay.
2. Implement touch/fill detection separate from final fill execution.
3. Implement adverse pre-fill signals: fair drop, residual drop, mid movement, spread change, spot/reference movement, gamma change, and quote age.
4. Implement configurable cancel rules at 5s/15s/30s checkpoints.
5. Compare static maker-first vs dynamic cancel replay under the same entry candidates.
6. Add toxicity metrics: fill rate, toxic fill rate, bid-below-entry after fill, stop-loss touch, missed favorable fill, average closeout return, and settlement return when available.
7. Add bucket reports by edge, residual, gamma, time-to-expiry, moneyness, confidence, spread, and cancel reason.
8. Add tests for lifecycle transitions, cancel precedence, quote age, touch-but-cancel, missed fill, and toxicity aggregation.
9. Run the replay on the current corpus and write findings into this task artifact.
10. Identify which cancel rules should be candidates for WU-008 narrowed strategy testing.

## Verification

- Unit tests verify quote lifecycle transitions are deterministic.
- Unit tests verify cancel rules fire before fill when configured checkpoint timing requires it.
- Unit tests verify touch/fill detection uses side-specific executable ask and complement-consistent DOWN prices.
- Unit tests verify toxic fill and missed favorable fill metrics.
- Unit tests verify static maker-first and dynamic-cancel replays are comparable on the same candidate set.
- A local command reports toxicity reduction and opportunity loss against `.yxg/data/probability_gap_samples_iv_v1.sqlite`.

## Done When

- Dynamic cancel replay can be run offline with configurable cancel rules.
- The report quantifies toxicity reduction, fill-rate reduction, missed opportunity cost, and PnL impact.
- The task artifact records which cancel rules are promising enough for WU-008 and which are rejected.

## Escalate If

- Snapshot cadence is too sparse to evaluate 5s/15s/30s cancel timing.
- Toxicity cannot be reduced without eliminating nearly all fills.
- Results depend entirely on one market or one outlier bucket.
- Settlement validation from WU-006 invalidates the model edge itself, making execution optimization premature.

## Evidence Log

- WU-005 showed maker fill is a negative signal: filled samples under the same `A_edge` bucket had worse future returns than unfilled samples.
- WU-005 showed narrow `buffer=0.03` makes most high-edge quotes fill and those fills are highly toxic.
- Candidate research direction is to reduce toxic fills through dynamic cancel rules before selecting a narrowed strategy.

## Notes
- WU-007 should not decide paper readiness; it should produce execution filters for WU-008 to evaluate.
