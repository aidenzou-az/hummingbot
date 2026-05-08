---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-006
slug: wu-006-btc-1d
title: WU-006: BTC 1d probability gap 模型 edge validation 与 settlement labeling。基于 WU-005 结论，补官方或可靠 proxy settlement outcome，验证 iv_digital_v1/A_edge/A_residual 对最终 settlement PnL 的 calibration、Brier/log loss、edge bucket -> final PnL；区分模型错误和执行错误。明确 out of scope: 不改定价模型、不做真实交易、不做 paper trading。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-05"
updated_at: "2026-05-05"
---

# Work Unit

## Objective

Build a settlement-aware model edge validation layer for BTC 1d probability-gap research. The outcome should attach official or clearly labeled proxy settlement outcomes to sampled Polymarket markets, then evaluate whether `iv_digital_v1`, `A_edge`, and `A_residual` predict final settlement PnL and calibrated event probabilities. This work should explicitly separate model validity from execution quality before any further strategy narrowing or paper trading.

## In Scope

- Add settlement outcome labeling for BTC 1d Polymarket markets using source precedence: official Polymarket/Gamma resolution, Binance BTCUSDT 1m rule-based close for closed BTC 1d markets, clearly labeled near-market-end proxy, then unavailable.
- Add HTTP retry/backoff and durable Binance settlement cache so historical Kline connection resets do not turn already-settled markets back into `unavailable`.
- Compute settlement PnL for hypothetical UP/DOWN entries from existing snapshots.
- Validate `iv_digital_v1` fair probabilities by fair bucket, Brier score, log loss, calibration curve, and observed win rate.
- Validate `A_edge = A_fair(side) - executable_ask(side)` against final settlement PnL and future closeout return.
- Validate `A_residual = A_fair(side) - Polymarket_mid(side)` against final settlement PnL and future closeout return.
- Compare settlement-based results with WU-005 closeout-based diagnostics to distinguish model error from execution error.
- Produce a repeatable offline report over `.yxg/data/probability_gap_samples_iv_v1.sqlite`.
- Preserve the existing `iv_digital_v1` pricing model; analysis may add labels/reports but must not change the scanner fair-value formula.

## Out Of Scope

- Changing `iv_digital_v1` fair-value math.
- Live Polymarket trading, order signing, real balances, or order placement.
- Paper trading engine or persistent virtual balances.
- Dynamic cancel or quote lifecycle simulation; that belongs to WU-007.
- Narrowed candidate strategy selection; that belongs to WU-008.
- Claiming model profitability from fewer than 5-10 complete BTC 1d settlements.

## Expected Touch Points

- [controllers/generic/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_execution_replay.py:1)
- A new settlement/model-validation helper module if needed under `controllers/generic/`.
- [scripts/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_execution_replay.py:1) or a new CLI script for settlement validation.
- [test/controllers/test_probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_execution_replay.py:1) or a new focused model-validation test file.
- `.yxg/data/probability_gap_samples_iv_v1.sqlite` as the current sample corpus.
- `.yxg/work/active/WU-006-wu-006-btc-1d.md`

## Dependencies
- WU-005 execution-aware replay and diagnostics.
- Existing `iv_digital_v1` snapshot fields, top-of-book fields, and payload data.
- At least several complete BTC 1d markets for strong conclusions; the implementation must still run with partial data and label confidence.

## Assumptions
- Polymarket BTC 1d market resolution can be fetched or inferred from a reliable source after market close.
- Near-market-end proxy labels are useful for smoke checks but must be separated from official/Binance rule settlement labels.
- The existing snapshots may stop before official close; this work can report missing settlement coverage without modifying the live sampler.

## Risks
- Official resolution may require additional API discovery or may be unavailable for older samples.
- Proxy settlement labels can be wrong near the threshold and must not be mixed with official/Binance rule labels in final conclusions.
- `forced_exit_time` is not a settlement timestamp in this strategy; it can mean Binance signal validity or strategy exit cutoff. Proxy settlement must use `market_end_time`.
- Too few settled markets can make calibration curves unstable.
- Settlement PnL may contradict short-horizon closeout return, requiring explicit interpretation rather than forcing one conclusion.
- External API connection resets can drop live ticks or hide settlement labels unless request retry and local settlement caching are used.

## Plan

1. Identify available Polymarket resolution fields or APIs for BTC 1d Up/Down markets and define source precedence: official first, Binance 1m rule settlement second, proxy third, unavailable last.
2. Implement settlement outcome labeling with `outcome`, `source`, `confidence`, and `resolved_at` metadata.
3. Compute settlement PnL for side-specific entries from stored snapshots.
4. Add fair bucket calibration for `iv_digital_v1` UP probability and side-specific fair values.
5. Add `A_edge` and `A_residual` settlement-PnL truth tables by edge bucket, side, gamma, time-to-expiry, confidence, and spread.
6. Add closeout-vs-settlement comparison to classify likely model error vs execution error.
7. Add Brier score and log loss, separating official and proxy samples.
8. Add tests for label source precedence, proxy confidence, calibration buckets, Brier/log loss, and settlement PnL.
9. Run the report on the current corpus and write findings into this task artifact.
10. Define the minimum evidence threshold needed before WU-008 can claim a model-backed strategy candidate.
11. Add WU-006 closeout hardening: retry/backoff for Binance/Gamma fetches, JSON settlement cache read/write, and explicit fetch-failure labels.

## Verification

- Unit tests verify settlement source precedence and confidence labels.
- Unit tests verify official, Binance rule, and proxy settlements are never merged silently in aggregate conclusions.
- Unit tests verify side-specific settlement PnL for UP and DOWN entries.
- Unit tests verify fair bucket calibration, Brier score, and log loss calculations.
- Unit tests verify `A_edge` and `A_residual` truth tables use executable side prices and complement-consistent DOWN prices.
- A local command runs against `.yxg/data/probability_gap_samples_iv_v1.sqlite` and reports official/Binance-rule/proxy/unavailable settlement counts.
- Unit tests verify cached Binance settlement labels survive network fetch failure.
- Unit tests verify Binance kline retry succeeds after transient failures and records fetch failures distinctly when exhausted.
- The report clearly states whether model edge is validated, invalidated, or still under-sampled.

## Done When

- A repeatable command outputs settlement labeling coverage and model edge validation over the WU-004/WU-005 corpus.
- The output separates official settlement, Binance rule settlement, proxy settlement, and unavailable settlement.
- The output includes calibration, Brier/log loss, edge bucket settlement PnL, and closeout-vs-settlement comparison.
- The work artifact records current findings and whether enough evidence exists to proceed toward WU-008.

## Escalate If

- Official settlement cannot be fetched or reliably inferred for BTC 1d markets.
- Available samples do not include enough complete markets to compute useful calibration.
- Proxy outcomes conflict with official outcomes.
- Settlement validation shows `iv_digital_v1` is materially miscalibrated, requiring a new pricing-model task before WU-007/WU-008.

## Evidence Log

- WU-005 showed `A_edge` and `A_residual` have positive short-horizon return correlation, but maker fill is toxic and settlement validation is missing.
- Cross-model checks showed `iv_digital_v1` has the strongest closeout-return ranking among tested models, but current samples are not enough for final EV claims.
- Current SQLite snapshots did not include official `settlement_outcome`; near-final proxy checks were possible only for a small number of markets.
- Implemented settlement/model validation in `controllers/generic/probability_gap_model_validation.py` and CLI `scripts/probability_gap_model_validation.py`.
- The validator originally enforced source precedence: explicit Gamma official outcome, closed binary Gamma prices, then `proxy_near_forced_exit`, then `unavailable`.
- Added tests in `test/controllers/test_probability_gap_model_validation.py` covering official field extraction, closed binary price extraction, proxy labeling, official-over-proxy precedence, side-specific settlement PnL, calibration/truth tables, and source-separated reports.
- Verification passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 22 passed.
- Current live corpus command: `PYTHONPATH=. python scripts/probability_gap_model_validation.py --db-path .yxg/data/probability_gap_samples_iv_v1.sqlite --fetch-official`.
- Current corpus settlement coverage: 4 markets total, 0 official, 3 `proxy_near_forced_exit`, 1 unavailable. Gamma fetch did not provide official outcomes for these sampled slugs.
- Proxy labels: May 3 UP at 40.179s before forced exit, May 4 UP at 1.831s before forced exit, May 5 UP at 12.958s before forced exit; May 6 unavailable.
- Proxy calibration over 921 tradable entries: Brier 0.0334, log loss 0.1991, fair buckets 70-80% and 80-90% both had actual UP rate 100%. This is directionally consistent but not sufficient because all proxy outcomes are UP and official settlement count is zero.
- Proxy settlement PnL for side-specific entries is negative across current `A_edge` and `A_residual` buckets because the tradable entries are mostly DOWN while all proxy outcomes are UP. Average settlement PnL over entries with 5m closeout data was about -0.117.
- Closeout-vs-settlement comparison under proxy labels: avg 5m closeout -0.0091 vs avg settlement -0.1170; avg 20m closeout -0.0072 vs avg settlement -0.1171. This supports the previous conclusion that short-horizon closeout ranking is not enough to claim final settlement EV.
- Current conclusion: implementation is complete, but evidence is insufficient for WU-008 go. Need official settlements or more complete markets before model edge can be considered settlement-validated.
- Revision after user clarification: for already closed BTC 1d markets, Binance BTCUSDT 1m close is acceptable as the rule-based settlement source because it matches the market's BTC price reference source better than a near-final snapshot proxy.
- Implemented `binance_rule_1m_close` settlement labeling in `controllers/generic/probability_gap_model_validation.py`, with precedence now: Gamma official explicit/binary prices -> Binance BTCUSDT 1m close at stored `market_end_time` -> `proxy_near_market_end` -> `unavailable`.
- Added CLI flag `--fetch-binance-rule` to `scripts/probability_gap_model_validation.py`.
- Added tests covering Binance rule labels, Binance-over-proxy precedence, and source-separated official/Binance/proxy/unavailable reports.
- Revision verification passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 24 passed.
- Revised corpus command: `PYTHONPATH=. python scripts/probability_gap_model_validation.py --db-path .yxg/data/probability_gap_samples_iv_v1.sqlite --fetch-official --fetch-binance-rule`.
- Initial revised corpus settlement coverage was 4 markets total, 0 official, 2 `binance_rule_1m_close`, 1 `proxy_near_forced_exit`, 1 unavailable.
- Binance rule labels: May 3 UP with settlement close 78677.42000000 vs reference 78465.05000000; May 4 UP with settlement close 80076.27000000 vs reference 78677.42000000.
- Accuracy review found the May 5 proxy label was not valid: the snapshot was near `forced_exit_time`/Binance signal cutoff, not near Polymarket `market_end_time`.
- Fixed proxy settlement to require snapshots near stored `market_end_time`; `forced_exit_time` is no longer used as a settlement proxy timestamp.
- Fixed model-validation `time_to_expiry_bucket` to use `market_end_time` rather than `forced_exit_time`.
- Post-fix corpus settlement coverage: 4 markets total, 0 official, 2 `binance_rule_1m_close`, 0 proxy, 2 unavailable.
- Post-fix labels: May 3 UP by Binance rule, May 4 UP by Binance rule, May 5 unavailable until market end data is available, May 6 unavailable.
- Post-fix verification passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 24 passed.
- Revised settlement validation still does not approve WU-008: Binance-labeled entries have Brier 0.0327 and log loss 0.1969, but tradable entries remain mostly DOWN while both closed outcomes are UP, so settlement PnL is negative. This supports continuing with more complete-market data and WU-007 execution/toxicity work rather than claiming strategy profitability.
- WU-006 closeout repair added after clean sampling exposed repeated `Connection reset by peer` from Binance/Gamma. Required fix: keep sampling/reporting deterministic by retrying transient HTTP failures and persisting successful Binance settlement closes locally.
- Implemented WU-006 closeout hardening:
  - `controllers/generic/probability_gap_scanner.py` now retries live HTTP requests with short exponential backoff and caches Binance reference 1m closes in memory.
  - `controllers/generic/probability_gap_model_validation.py` now retries Gamma/Binance offline fetches, supports durable settlement cache at `.yxg/data/probability_gap_settlements.json`, and emits `binance_rule_fetch_failed` instead of silently collapsing exhausted network failures into generic `unavailable`.
  - `scripts/probability_gap_model_validation.py` now supports `--settlement-cache-json`, `--no-settlement-cache`, `--http-retry-count`, and `--http-backoff-seconds`.
- Seeded `.yxg/data/probability_gap_settlements.json` with previously verified Binance rule settlements for May 5-7 so current clean-corpus analysis remains reproducible during Binance connection resets.
- Added tests for transient Binance kline retry, cache fallback under network failure, and explicit fetch-failure labels.
- Closeout hardening verification passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 27 passed.
- Full scanner test path was not run in this environment because `test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py` requires missing package `cachetools`.
- Cache-backed clean corpus command: `PYTHONPATH=. python scripts/probability_gap_model_validation.py --db-path .yxg/data/probability_gap_samples_wu006_clean.sqlite --fetch-official --fetch-binance-rule --http-retry-count 1 --http-backoff-seconds 0`.
- Cache-backed clean corpus coverage now remains stable under current Binance reset: 5 markets total, 3 `binance_rule_1m_close`, 2 unavailable, 1597 settlement-labeled entries, Brier 0.1962.

## Notes
- This is the next recommended task before deeper execution strategy work because model EV must be separated from execution EV.
