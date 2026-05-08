---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-005
slug: wu-004-iv-digital
title: 基于 WU-004 的 iv_digital_v1 fair value，开新任务：实现 BTC 1d execution-aware research loop。冻结当前 fair value 模型版本，不继续改定价公式；在 SQLite/离线分析层补未来窗口诊断标签（edge/fair/book after 30s/2m/5m、max bid/min ask reachable、settlement outcome）；实现三套 replay：taker baseline、taker entry + hold、maker-first replay；maker replay 需要 quote_bid=fair-buffer、成交假设等级、take_profit/stop_loss/time_stop/forced_exit、cooldown/one-position 规则；按 gamma、time_to_expiry、moneyness、side、edge bucket、holding time、maker/taker 做 bucket report；输出 paper trading go/no-go 标准。明确 out of scope：真交易、订单签名、复杂 ML、继续大改 IV-digital 定价。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-05"
updated_at: "2026-05-05"
---

# Work Unit

## Objective

Build a small but complete execution-aware research loop on top of WU-004 `iv_digital_v1` BTC 1d fair value snapshots. The outcome should freeze the current fair-value model contract, enrich sampled snapshots with future-window diagnostic labels, implement comparable taker and maker replay modes, and produce bucketed reports that answer whether fee-aware model edge can realistically convert into positive EV under historical Polymarket book paths before any paper or live trading work begins.

## In Scope
- Freeze `iv_digital_v1` as the fair value model for this research loop; replay and reports must group by `model_version`.
- Add offline diagnostic labeling for existing and future SQLite snapshots without changing the core WU-004 pricing formula.
- Compute future-window labels for each eligible snapshot, including `edge_after_30s/2m/5m`, `fair_change_after_30s/2m/5m`, side-specific bid/ask after those horizons, `max_bid_reachable_next_5m`, and `min_ask_reachable_next_5m`.
- Add settlement outcome support when the market has resolved or when a deterministic resolution proxy is available from the stored market path.
- Implement three deterministic replay modes: taker baseline, taker entry plus hold, and maker-first replay.
- Implement maker-first replay with `quote_bid = fair - buffer`, configurable buffer components, fill-assumption levels, take-profit, stop-loss, time-stop, forced-exit, cooldown, and one-position-per-market/window rules.
- Add maker-fill adverse selection diagnostics for 5s, 30s, 2m, and 5m after entry, including adverse fair move, edge disappearance, bid below entry, and stop-loss touch.
- Add a parameter grid runner for buffer, take-profit, stop-loss, cooldown, gamma filter, and minimum time-to-expiry to evaluate robust parameter regions instead of a single best point.
- Add risk filters for `model_confidence`, `gamma_risk`, minimum time-to-expiry, spread bounds, optional top-of-book size/depth if available, and side-specific edge thresholds.
- Produce bucket reports by gamma, time-to-expiry, moneyness, side, edge bucket, holding time, model confidence, maker/taker mode, and fill-assumption level.
- Preserve WU-004 snapshot compatibility and support analysis of `.yxg/data/probability_gap_samples_iv_v1.sqlite`.
- Record enough evidence to decide whether the next step should be paper trading, more sampling, or further execution-rule refinement.

## Out Of Scope
- Authenticated Polymarket trading, order signing, live order placement, cancellation, or real inventory management.
- Paper trading with persistent virtual balances or live order lifecycle.
- Complex ML, reinforcement learning, or black-box parameter search.
- Continuing to redesign the `iv_digital_v1` fair-value formula.
- Full websocket migration or CLOB depth ingestion unless only a minimal optional hook is needed for stored size fields.
- Claiming profitability from less than the agreed sample threshold.
- Optimizing parameters to a single best point without checking nearby parameter stability.

## Expected Touch Points
- [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1)
- A new analysis/replay module if needed, likely under `controllers/generic/` or `scripts/`.
- A new CLI script for offline execution-aware replay and bucket reporting, likely under [scripts/](/Users/bytedance/Projects/hummingbot/scripts:1).
- [test/controllers/test_probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_sampling.py:1) or a new focused replay test file.
- `.yxg/data/probability_gap_samples_iv_v1.sqlite` as the primary current corpus.
- `.yxg/work/active/WU-005-wu-004-iv-digital.md`

## Dependencies
- WU-004 `iv_digital_v1` scanner fields and fee-aware maker/taker edge persistence.
- At least one post-WU-004 BTC 1d market sample, with stronger conclusions requiring 5-10 complete BTC 1d markets.
- Existing SQLite snapshot schema and replay primitives from WU-003/WU-004.
- Current Polymarket top-of-book bid/ask data captured by snapshots.
- Optional future availability of top-of-book size/depth; first version must remain useful without it.

## Assumptions
- `iv_digital_v1` remains frozen during this task so replay changes can be evaluated independently from pricing changes.
- The first execution-aware research loop can operate from historical snapshots rather than live orders.
- Top-of-book bid/ask paths are sufficient for a first maker-fill simulation, but fill assumptions must be explicitly labeled as optimistic, conservative, or strict.
- Settlement labels may initially be partial if market resolution is not stored yet; replay can still evaluate closeout and executable path metrics without final settlement PnL.
- The goal is to find stable buckets and robust rule regions, not a single maximized backtest parameter set.
- A bucket with positive replay results should be considered a paper-trading candidate only if it is not dominated by one or two trades.

## Risks
- Maker replay can overstate fills if queue position and size are not modeled conservatively.
- Current snapshots may not include top-of-book size, limiting execution realism until size/depth is added.
- Too few complete daily markets can produce unstable bucket conclusions.
- Edge labels can be misleading if there are long sampling gaps or if future horizon matching picks stale snapshots.
- High-gamma periods can dominate apparent edge and must be filtered or separately bucketed.
- Re-entry and cooldown rules can materially alter results; conclusions must state the rule set used.
- Settlement-outcome labeling may require additional data source work if it cannot be inferred from existing snapshots.

## Plan
1. Define the frozen `iv_digital_v1` research contract and required fields for replay inputs, including handling of missing RV, moneyness, and size fields.
2. Implement future-window diagnostic labeling over ordered SQLite snapshots with configurable horizons of 30 seconds, 2 minutes, and 5 minutes.
3. Implement reachable-book metrics such as side-specific max exit bid and min entry ask over the next 5 minutes.
4. Add or stub settlement-outcome labeling with explicit source and confidence.
5. Implement taker baseline replay that preserves the current eat-ask / sell-bid behavior for sanity comparison.
6. Implement taker entry plus hold replay to test whether `iv_digital_v1` has directional predictive value when not immediately exited on edge decay.
7. Implement maker-first replay with quote buffer, fill-assumption level, take-profit, stop-loss, time-stop, forced-exit, cooldown, and one-position rules.
8. Add bucket classification helpers for gamma, model confidence, time-to-expiry, moneyness, side, edge range, spread, and holding time.
9. Produce aggregate and bucketed report output with trade counts, hit rate, realized move, best/worst path move, average hold, and concentration warnings.
10. Add maker adverse selection labels after maker fills for 5s, 30s, 2m, and 5m, grouped by gamma, time-to-expiry, moneyness, edge bucket, side, confidence, and spread.
11. Add parameter grid execution for buffer, take-profit, stop-loss, cooldown, gamma filter, and minimum time-to-expiry, with stable-region summaries instead of single-point optimization.
12. Add tests for diagnostic labels, fill assumptions, replay modes, cooldown/one-position behavior, adverse selection labels, parameter grid output, and bucket aggregation.
13. Run the report on the current `probability_gap_samples_iv_v1.sqlite` corpus and write findings into this task artifact.
14. Define paper-trading go/no-go criteria based on sample count, replay profitability, adverse selection behavior, bucket stability, concentration, and parameter robustness.

## Verification
- Unit tests verify future-window labels choose the first snapshot at or after each target horizon and handle missing future snapshots safely.
- Unit tests verify `max_bid_reachable_next_5m` and `min_ask_reachable_next_5m` are side-specific and use complement-consistent UP/DOWN prices.
- Unit tests verify taker baseline replay remains deterministic and comparable with prior replay behavior.
- Unit tests verify taker-hold replay does not exit solely because `edge_decay` fires.
- Unit tests verify maker-first fill assumptions differ as expected: optimistic, conservative, and strict.
- Unit tests verify cooldown and one-position-per-market rules prevent fragmented re-entry loops.
- Unit tests verify take-profit, stop-loss, time-stop, and forced-exit reasons are recorded correctly.
- Unit tests verify maker adverse selection labels flag adverse fair movement, edge disappearance, bid below entry, and stop-loss touch after fill.
- Unit tests verify parameter grid results include all requested parameter dimensions and can identify stable regions separately from best single rows.
- Unit tests verify bucket reports group by gamma, time-to-expiry, moneyness, side, edge bucket, and replay mode.
- A local report can run against `.yxg/data/probability_gap_samples_iv_v1.sqlite` without modifying the live sampler.
- The report clearly separates `tradable`, `observable`, and rejected lifecycle rows.

## Done When
- A repeatable offline command can run execution-aware replay on the WU-004 SQLite corpus.
- The output includes future diagnostic labels, three replay modes, maker fill-assumption levels, and bucketed performance summaries.
- The output includes maker adverse selection summaries and parameter-grid stability summaries.
- Replay results are grouped by `model_version=iv_digital_v1` and do not mix old delta-proxy rows into conclusions.
- The work artifact records initial findings from the current corpus and states whether the next step is more sampling, replay refinement, or paper trading.
- Paper-trading go/no-go criteria are written down and require at least 5-10 complete BTC 1d markets before real paper execution.

## Escalate If
- The existing snapshot cadence is too sparse to compute 30s/2m/5m labels reliably.
- Maker replay cannot be made credible without order size, queue position, or deeper CLOB data.
- Settlement outcome cannot be obtained or inferred in a way that supports final PnL validation.
- Results are entirely driven by one day or one outlier bucket, preventing meaningful strategy conclusions.
- Implementing this task starts requiring live trading credentials, signing, or order lifecycle management.
- The analysis reveals that `iv_digital_v1` itself is unstable enough that execution research cannot proceed without repricing work.

## Evidence Log
- WU-004 changed the scanner to persist `iv_digital_v1` fields including `fair_value_up/down`, `option_iv`, `tau_years`, `d2`, `prob_delta`, `gamma_risk`, `model_confidence`, `expiry_mismatch_minutes`, and fee-aware `maker_edge_*` / `taker_edge_*`.
- WU-004 moved live sampling defaults to `.yxg/data/probability_gap_samples_iv_v1.sqlite` and `/tmp/probability_gap_sampling_iv_v1.log`.
- May 4 replay using the existing taker-style logic was weak: thresholds around `0.03-0.05` produced negative average realized move, showing current replay is not sufficient as an execution strategy.
- Discussion on 2026-05-05 established that the next problem is no longer just calculating edge, but converting edge into executable positive EV through maker-first execution rules and better replay diagnostics.
- Implemented offline execution-aware replay in `controllers/generic/probability_gap_execution_replay.py` and CLI `scripts/probability_gap_execution_replay.py`; the live sampler schema was not changed.
- Added tests in `test/controllers/test_probability_gap_execution_replay.py` covering future-window labels, complement-consistent DOWN book metrics, taker-hold behavior, maker fill assumptions, and bucket grouping.
- Verification command passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 13 passed.
- Current corpus command: `PYTHONPATH=. python scripts/probability_gap_execution_replay.py --db-path .yxg/data/probability_gap_samples_iv_v1.sqlite --min-edge 0.02 --quote-buffer 0.03 --take-profit 0.03 --stop-loss 0.02 --time-stop-minutes 20 --fill-assumption conservative`.
- Current corpus result at execution time: 1193 `iv_digital_v1` snapshots, 1193 diagnostics, coverage 30s=1190, 2m=1187, 5m=1178, 3 distinct markets.
- Conservative replay summary: `taker_baseline` 12 trades, total move -0.02, avg -0.0017, positive ratio 0.333; `taker_hold` 12 trades, total move -0.07, avg -0.0058, positive ratio 0.333; `maker_first` 37 trades, total move -1.7701, avg -0.0478, positive ratio 0.0.
- Maker fill-assumption sensitivity on current corpus: optimistic 39 trades total -1.9301, conservative 37 trades total -1.7701, strict 35 trades total -1.6234; all are `no_go` due fewer than 5 markets and negative maker total realized move.
- Initial interpretation: the current `iv_digital_v1` edge still does not convert to executable positive EV under this first maker-first path simulation; likely next work should tighten entry filters, stop entering into adverse quote fills, and continue sampling until at least 5-10 complete markets.
- Added maker adverse selection diagnostics for 5s, 30s, 2m, and 5m after fill, with flags for adverse fair move, edge disappeared, bid below entry, and stop-loss touched.
- Added parameter grid support covering buffer 0.02/0.03/0.05/0.08/0.10, take-profit 0.01/0.02/0.03, stop-loss 0.02/0.03/0.05/0.08, cooldown 0/5/10 minutes, gamma low-only vs low+medium, and min time-to-expiry 30/60/120 minutes.
- Verification command after adverse/grid additions passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 15 passed.
- Current adverse selection report on 1210 snapshots: 32 grouped rows; many maker buckets have `bid_below_entry_ratio=1.0` and `stop_loss_touched_ratio=1.0`, confirming maker fills are frequently followed by immediately worse executable exit prices.
- Current parameter grid report: 1080 rows, 209 positive rows. Best rows use buffer 0.08, gamma low-only, min time-to-expiry 60m, take-profit 0.03, but only 4 trades and top-trade concentration around 0.74-0.76, so this is not enough to claim a stable profitable region.

## Notes
- Current live sampling should continue accumulating `iv_digital_v1` data while this offline research loop is implemented, unless the implementation requires schema changes that would corrupt the live corpus.
- This task should be completed before any paper-trading or live-trading connector work is opened.
