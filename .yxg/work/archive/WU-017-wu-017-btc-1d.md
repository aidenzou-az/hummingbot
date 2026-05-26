---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-017
slug: wu-017-btc-1d
title: WU-017: BTC 1d probability-gap post-sampling settlement-aware analysis。当前 10 天采样已因 run_days_elapsed 停止，DB `.yxg/data/probability_gap_samples_wu013_clean.sqlite` 含 4654 行，覆盖 2026-05-09 到 2026-05-19，且 WU-015/WU-016 已修正 early observable sampling 与分段 schedule。目标：冻结这批样本，做数据质量审计、settlement/proxy settlement 回填、模型验证、模型演进对比与 execution-aware replay，产出下一步是否进入 paper trading、继续采样、还是继续改模型/执行规则的明确结论。范围包括复制 frozen DB、按市场完整度分层、用 official 或 Binance 1m proxy settlement 给已 closed 市场打标签、运行 `scripts/probability_gap_model_validation.py`、`scripts/probability_gap_model_evolution.py`、`scripts/probability_gap_execution_replay.py`，并按 time bucket、side、edge bucket、confidence、gamma、spread、maker/taker/hold 参数网格输出结论。范围外：不改采样调度、不改 live scanner trading eligibility、不接实盘、不重启采样。验证要求：报告能解释哪些市场可用于结论、哪些样本只能辅助观察；settlement 标签来源清楚；replay PnL/EV 扣除当前 fee/spread 假设；给出 go/no-go 与后续 WU 建议。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-25"
updated_at: "2026-05-25"
---

# Work Unit

## Objective

Convert the completed 10-day BTC 1d sampling corpus into a settlement-aware research conclusion. The deliverable is a frozen-data analysis report that states whether the current probability-gap model and execution rules justify paper trading, require more sampling, or require model/execution changes before further live work.

## In Scope
- Freeze `.yxg/data/probability_gap_samples_wu013_clean.sqlite` into a timestamped/read-only analysis copy.
- Audit data quality by market, date, lifecycle state, field coverage, and completeness.
- Classify markets into conclusion-grade, partial-support, and exclude buckets.
- Add or refresh settlement labels for closed BTC 1d markets using official data if available and Binance 1m proxy settlement when official settlement is unavailable.
- Run settlement-aware model validation.
- Run model evolution comparison across existing candidates.
- Run execution-aware replay with diagnostics, trades, and parameter grid.
- Summarize results by time bucket, side, edge bucket, confidence, gamma risk, spread, and execution mode.
- Produce a concrete go/no-go decision for paper trading and a recommended next WU.

## Out Of Scope
- Do not restart or extend sampling.
- Do not change LaunchAgent, sampling schedule, scanner trading eligibility, or live model behavior.
- Do not add new model families unless needed only as a read-only comparison already supported by existing code.
- Do not add real trading, paper trading, order placement, or connector work.
- Do not mutate the original clean DB except for explicitly approved settlement-cache behavior; analysis should use a frozen copy.

## Expected Touch Points
- `.yxg/data/probability_gap_samples_wu013_clean.sqlite`
- `.yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite`
- `.yxg/data/probability_gap_settlements.json`
- `scripts/probability_gap_model_validation.py`
- `scripts/probability_gap_model_evolution.py`
- `scripts/probability_gap_execution_replay.py`
- `controllers/generic/probability_gap_model_validation.py`
- `controllers/generic/probability_gap_model_evolution.py`
- `controllers/generic/probability_gap_execution_replay.py`
- New analysis output under `.yxg/data/` or `.yxg/reports/` if needed.
- `.yxg/work/active/WU-017-wu-017-btc-1d.md`

## Dependencies
- WU-015/WU-016 sampling changes are already complete.
- Current DB has stopped via `run_days_elapsed`; no additional data should be added during this analysis.
- Binance historical kline access may be needed for proxy settlement.

## Assumptions
- Binance 1m proxy settlement is acceptable for already closed BTC 1d markets when official settlement is unavailable, because the market resolution references Binance BTCUSDT.
- Snapshot-level counts are not independent observations; conclusions must be grouped by market and bucket rather than relying only on raw row counts.
- Partial markets can provide directional or operational evidence but should not dominate go/no-go conclusions.

## Risks
- The corpus has missing days and partial markets, so the sample may be insufficient for paper-trading approval.
- Network or Binance historical kline errors may leave some settlements unresolved.
- Parameter-grid replay can overfit if the conclusion is based on one narrow winning parameter.
- Sparse trades after filters may make positive PnL statistically weak.

## Plan
1. Freeze the DB with a stable filename and record checksum/counts.
2. Produce data-quality tables by market/date/classification/field coverage.
3. Determine which market slugs are conclusion-grade, partial-support, or excluded.
4. Run settlement-aware validation on the frozen DB with Binance-rule/proxy settlement enabled.
5. Run model evolution report on the frozen DB.
6. Run execution replay with diagnostics, trades, and parameter grid.
7. Inspect outputs for stable regions versus overfit single-point wins.
8. Write a concise report with go/no-go decision and next WU recommendation.
9. Record all commands and key results in this work artifact.

## Verification
- Frozen DB exists and row counts match the original at freeze time.
- Data-quality report identifies usable and unusable markets.
- Settlement source is explicit for every market included in settlement-aware metrics.
- Model validation and model evolution scripts complete or their blockers are documented.
- Execution replay includes diagnostics, trades, and parameter grid.
- Final conclusion distinguishes snapshot edge, settlement edge, and execution-realizable EV.

## Done When
- There is a frozen-data analysis output and a written conclusion answering: paper trading now, continue sampling, or improve model/execution first.
- The conclusion names the specific buckets or market regimes that support it.
- Any data insufficiency is explicit and does not get hidden behind aggregate PnL.

## Escalate If
- Fewer than two conclusion-grade markets have settlement labels.
- Settlement retrieval fails for most closed markets.
- Replay scripts fail in a way that requires code changes rather than analysis-only work.
- Results show apparent profitability only in a single market or single narrow parameter cell.

## Evidence Log
- Current live check on 2026-05-25: LaunchAgent is loaded but not running; logs show `SCHEDULE_STOP ... reason=run_days_elapsed`, so the planned sampling window has completed.
- Current DB evidence: `.yxg/data/probability_gap_samples_wu013_clean.sqlite` has `4654` rows from `2026-05-09T04:57:35.014045+00:00` to `2026-05-19T05:45:10.741520+00:00`.
- Current market coverage is uneven: high-row markets include May 9, May 11, May 14, and May 18; May 10, May 12, May 13, May 15, and May 19 are partial or sparse.
- Frozen analysis DB created: `.yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite`; checksum matches source at freeze time: `b63c2ef2fc82e64b35ac7e73db608a2f9b2b1045e027b6b214aa132256f10fac`.
- Settlement-aware validation completed: `.yxg/reports/probability_gap_wu017_model_validation.json`. It produced `2366` validation entries and settlement labels for `9` markets from Binance 1m rule data; `2` markets were unavailable because market end or observation metadata was missing.
- Model-evolution comparison completed: `.yxg/reports/probability_gap_wu017_model_evolution.json`. It recommends keeping raw `iv_digital_v1`; calibration is `in_sample_only_rejected_by_leave_one_market_out`, and the report recommends collecting more settled markets before live model changes.
- Execution replay completed: `.yxg/reports/probability_gap_wu017_execution_replay.json`. Default `maker_first` result is negative (`55` trades, total realized move `-1.4288`, avg `-0.0260`), so the replay decision is `no_go`.
- Final written report: `.yxg/reports/probability_gap_wu017_post_sampling_report.md`. Conclusion: do not enter paper trading yet; continue more settled-market collection and open a dedicated execution-robustness WU for `taker_hold` and high-buffer maker variants.

## Notes
- This WU is intentionally analysis-only. If the result is promising, open a separate paper-trading WU.
