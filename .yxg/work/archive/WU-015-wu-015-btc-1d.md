---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-015
slug: wu-015-btc-1d
title: WU-015: 修正 BTC 1d 采样窗口逻辑。当前 scanner 用 max_minutes_before_settlement=720 作为第一道过滤，导致 Polymarket 市场已开始且 Binance 最早期权有重叠时，May 12 市场仍被 outside_overlap_window 阻断，不能采集有效快照。正确逻辑应拆分 sampling eligibility 与 trading eligibility：只要 Polymarket 市场已开始、reference price 已固定、盘口存在、Binance 有未来 BTC option expiry 或可用 forward/vol 数据，就允许采样并落库；是否 tradable 再由距离结算、Binance overlap/horizon、edge、gamma、exit buffer 等判定。实现要求：不把 outside_overlap_window 作为采样阻断原因；对于提前市场记录 observable/pre_trade_observable 或类似状态，保留 classification_reason 说明尚未进入 trading window；保持生命周期去重不刷 rejected 垃圾；补测试覆盖 May 12 这种 market started + Binance overlap exists + Polymarket settlement >12h 的场景；跑 live smoke 验证 May 12 能落 option_chain/forward snapshot。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-11"
updated_at: "2026-05-11"
---

# Work Unit

## Objective

Fix BTC 1d probability-gap sampling so market data can be collected as soon as a Polymarket daily market is live and its reference price is fixed, even when the market is more than the trading horizon away from settlement. `outside_overlap_window` must no longer prevent snapshot collection; it should only prevent a snapshot from being classified as tradable.

## In Scope
- Split scanner gating into sampling eligibility and trading eligibility.
- Record early-but-sampleable BTC 1d markets as `observable` snapshots with a clear `classification_reason`, such as `outside_overlap_window`.
- Preserve existing tradable behavior once the market enters the configured trading window.
- Preserve lifecycle deduplication so repeated non-tradable observations do not flood SQLite.
- Add tests covering the May 12 style case: market started, top-of-book available, Binance option overlap exists, but Polymarket settlement is more than `max_minutes_before_settlement` away.
- Run a live smoke against the current May 12 market and confirm it writes option-chain/forward fields.

## Out Of Scope
- Do not change the fair-value model, horizon-smile math, or calibration.
- Do not make early snapshots tradable before they satisfy trading eligibility.
- Do not add authenticated Polymarket/Binance trading.
- Do not rewrite the LaunchAgent scheduling model except if a minimal smoke command needs to be documented.
- Do not migrate or reset the existing sampling DB.

## Expected Touch Points
- [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1)
- [controllers/generic/probability_gap_scanner_utils.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner_utils.py:1)
- [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1)
- [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1)
- [test/controllers/test_probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_sampling.py:1)
- Scanner-focused tests if an existing test file covers probability-gap controller behavior.

## Dependencies
- WU-013/WU-014 option-chain and forward fields must remain available in snapshots.
- Current live evidence: Binance BTC Options has a future expiry at `2026-05-12T08:00:00Z`, while the May 12 Polymarket market is already live but currently rejected as `outside_overlap_window`.

## Assumptions
- The scanner's current `max_minutes_before_settlement=720` remains a trading eligibility threshold, not a sampling threshold.
- If reference price is not fixed or top-of-book is missing, the market still cannot produce a useful priced snapshot.
- Early observable snapshots are useful for model/replay research even if no trade should be placed yet.

## Risks
- If early snapshots are written too frequently, they can pollute the clean corpus; lifecycle and interval rules must remain conservative.
- If `observable` is interpreted as actionable, later analysis may confuse data collection with trading eligibility; status/reason fields must stay explicit.
- Live smoke depends on public Binance/Polymarket APIs being reachable.

## Plan
1. Inspect current scanner classification flow and snapshot persistence rules.
2. Refactor overlap-window rejection so `outside_overlap_window` becomes an observable/non-tradable reason after reference, book, forward, and option-chain fields are collected.
3. Keep `market_already_settled`, `inside_exit_buffer`, missing reference, and missing top-of-book behavior conservative.
4. Ensure status output and DB snapshot fields preserve `classification_reason` and do not imply an early market is tradable.
5. Add targeted tests for outside-window observable sampling and existing tradable behavior.
6. Run focused pytest, compile checks, and a 1-iteration live smoke against the current DB or a temporary smoke DB.
7. Record verification evidence and final decision in this work artifact.

## Verification
- Focused pytest for scanner/sampling behavior passes.
- Existing probability-gap model/sampling tests still pass.
- A live smoke during the May 12 pre-12h period writes an observable May 12 snapshot with option-chain and forward fields instead of only a rejected `outside_overlap_window` row.
- The live smoke must not mark the early snapshot as tradable before trading eligibility is met.

## Done When
- `outside_overlap_window` no longer blocks data collection for live, reference-fixed BTC 1d markets with top-of-book and Binance data.
- Early snapshots are persisted as non-tradable observations with clear reason fields.
- Tests and live smoke evidence are recorded.

## Escalate If
- Polymarket does not expose top-of-book for early markets through the current Gamma path.
- Binance option-chain data is unavailable or lacks enough expiry/mark fields for early snapshots.
- The persistence layer cannot represent a non-tradable observation without breaking replay assumptions.

## Evidence Log
- 2026-05-12 00:54 CST live check: Binance BTC Options earliest future expiry was `2026-05-12T08:00:00Z`, about 906 minutes away, so Binance has a future expiry overlapping the already-live May 12 Polymarket market.
- Current bug evidence: May 12 rows in `.yxg/data/probability_gap_samples_wu013_clean.sqlite` are rejected with `classification_reason=outside_overlap_window` before the scanner reaches reference/option/forward snapshot construction.
- Implemented `overlap_reason_blocks_sampling`: `outside_overlap_window` no longer blocks sampling, while `inside_exit_buffer` and `market_already_settled` remain hard sampling blockers.
- Scanner now computes the trading-window reason before reference/signal construction but only applies `outside_overlap_window` after model, option-chain, and forward fields are built; such rows are persisted as `observable`, not `tradable`.
- Verification: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_sampling.py test/controllers/test_probability_gap_option_chain.py test/controllers/test_probability_gap_forward.py test/controllers/test_probability_gap_model_evolution.py test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py` passed with `43 passed, 1 existing pytest config warning`.
- Verification: `PROB_GAP_PYDEPS_PATH=/tmp/hb_pydeps PYTHONPATH=/tmp/hb_pydeps:. /Users/bytedance/.pyenv/versions/3.12.4/bin/python -m py_compile controllers/generic/probability_gap_scanner.py controllers/generic/probability_gap_scanner_utils.py scripts/probability_gap_intraday_sampling.py` passed.
- Live smoke using temporary DB: `probability_gap_intraday_sampling.py --iterations 1 --sleep-seconds 1 --db-path .yxg/data/probability_gap_wu015_smoke.sqlite --reset-db` wrote `bitcoin-up-or-down-on-may-12-2026` as `observable | outside_overlap_window` with `option_chain_slice_count=12`, `forward_source=perp_mark`, `selected_option_expiry=2026-05-12T08:00:00+00:00`, and `smile_call_spread_status=horizon_mismatch`.
- Live smoke against the official clean DB without reset appended the same May 12 early observable snapshot at `2026-05-11T16:59:32.807328+00:00`; the row has `best_side=DOWN`, `best_net_edge=-0.0209304262226913`, `option_chain_slice_count=12`, and is not marked tradable.
- Runtime note: the already-running LaunchAgent process was started before the code change and could not be killed from this shell due macOS permissions; it will exit at its configured window end and future LaunchAgent starts will load the fixed code. A direct one-shot run was used to confirm and append the corrected May 12 snapshot immediately.

## Notes
- none
