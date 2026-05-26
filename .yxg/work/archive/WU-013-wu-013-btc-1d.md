---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-013
slug: wu-013-btc-1d
title: WU-013: BTC 1d Binance option-chain slice sampling + smile/call-spread digital. 基于 WU-011 结论，smile-aware digital 当前被 blocked，因为 snapshots 没有相邻 option mark/call prices。目标是扩展采样与离线研究：持久化 reference_price 附近多档 Binance option chain slice，包括 expiry、strike、call/put、mark_price、bid/ask、mark_iv、delta、underlying_price、risk_free_rate、volume/open_interest，如可用；实现 call-spread slope 近似 digital probability，并在 option expiry 与 Polymarket market_end_time mismatch 时标记 horizon_mismatch 或只作为 smile/variance 输入。范围：数据采样、SQLite/schema/report、离线 scorecard；不替换 live scanner、不接实盘、不做 paper trading。验证复用 WU-010/WU-011 scorecard，并明确数据质量和 horizon mismatch 限制。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-09"
updated_at: "2026-05-09"
---

# Work Unit

## Objective

Add Binance option-chain slice sampling and an offline smile/call-spread digital probability candidate for BTC 1d probability-gap research. This work exists because WU-011 proved `iv_digital_smile_call_spread_v2` is blocked by missing adjacent option mark/call prices in current snapshots.

The outcome should persist enough option-chain data around `reference_price` to estimate local call-price slope and determine whether smile-aware digital probability is feasible and useful under the settlement-aware scorecard.

## In Scope
- Extend sampling to persist a bounded Binance option-chain slice around `reference_price`:
  - option expiry
  - strike
  - call/put
  - mark price
  - bid/ask price where available
  - mark IV
  - delta
  - underlying price
  - risk-free rate
  - volume/open interest where available
  - data timestamp/source
- Store enough strikes around reference, for example 3 below and 3 above when available.
- Add SQLite/schema or payload support for option-chain slices without breaking existing corpora.
- Implement offline call-spread slope approximation:
  - `digital_rn ≈ -exp(r*tau) * dCallPrice/dK`
  - use local finite differences around `reference_price`
- Add horizon handling:
  - enable direct probability only when option expiry is close enough to Polymarket market end
  - otherwise mark `horizon_mismatch` and use chain only as smile/variance diagnostic
- Evaluate smile/call-spread candidate using WU-010/WU-011 scorecard and naive-baseline checks.

## Out Of Scope
- Forward/basis sampling; that belongs to WU-012.
- Replacing live scanner fair-value math.
- Real trading, paper trading, order signing, balances, or order lifecycle simulation.
- Full implied-density surface fitting or local-vol modeling.
- Heavy ML/optimization.
- Claiming profitability from sparse option-chain data or fewer than 5-10 complete settled BTC 1d markets.

## Expected Touch Points
- [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1)
- [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1)
- [controllers/generic/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_model_evolution.py:1)
- [controllers/generic/probability_gap_option_chain.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_option_chain.py:1)
- [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1)
- [scripts/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_model_evolution.py:1)
- [test/controllers/test_probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_sampling.py:1)
- [test/controllers/test_probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_model_evolution.py:1)
- [test/controllers/test_probability_gap_option_chain.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_option_chain.py:1)
- `.yxg/work/active/WU-013-wu-013-btc-1d.md`

## Dependencies
- WU-011 blocked-candidate finding for smile/call-spread digital.
- WU-010 settlement-aware scorecard and naive-baseline checks.
- Binance option chain endpoints with mark price and order book/quote fields.
- Existing sampler and SQLite snapshot persistence.

## Assumptions
- Binance option prices can be collected from public endpoints without account trading permissions.
- A local finite-difference call-spread approximation is acceptable for the first offline research pass.
- Expiry mismatch must be explicit; direct digital probability should not be trusted when Binance option expiry and Polymarket market end are materially different.

## Risks
- Binance option mark prices may be sparse, stale, or missing near the reference strike.
- Option price units may require normalization before finite differences are meaningful.
- Expiry mismatch may make the direct call-spread estimate unusable for most BTC 1d Polymarket horizons.
- Storing chain slices can increase SQLite size; the slice must remain bounded.
- Bad chain data can produce probabilities outside [0,1], which must be clipped and flagged rather than silently accepted.

## Plan
1. Identify Binance option endpoints and exact price/quote fields available for BTC options.
2. Define bounded chain-slice schema and payload format.
3. Extend sampler to capture reference-near strikes with call/put metadata and mark/bid/ask/IV/delta fields.
4. Add persistence/listing support for chain slices.
5. Implement finite-difference call-spread digital estimator with data-quality and horizon-mismatch flags.
6. Add offline scorecard entry for `iv_digital_smile_call_spread_v2`.
7. Run a smoke sample to confirm chain slices accumulate.
8. Run model-evolution report and record whether smile/call-spread is usable or still blocked by data/horizon quality.

## Verification
- Unit tests cover chain-slice serialization/persistence and backwards compatibility.
- Unit tests cover finite-difference digital probability bounds and invalid-data flags.
- Unit tests cover horizon mismatch behavior.
- A smoke sampling command shows option-chain slice rows or payloads are recorded.
- A local report shows data-quality coverage and scorecard results for the smile candidate.

## Done When
- Option-chain slices are persisted for sampled BTC 1d snapshots.
- The report states whether call-spread digital can be computed, how often it is horizon-aligned, and whether it beats raw `iv_digital_v1`.
- If still not usable, the report identifies the concrete blocker: data sparsity, price-unit mismatch, horizon mismatch, or insufficient settled markets.
- Targeted tests pass.

## Escalate If
- Binance option endpoints do not expose enough public price fields for a call-spread estimate.
- Price units cannot be normalized reliably from available data.
- Capturing enough chain data requires a larger sampler redesign than this WU should absorb.

## Evidence Log
- WU-011 showed `iv_digital_smile_call_spread_v2` is blocked because current snapshots do not store adjacent option mark/call prices.
- Binance public field check: `/eapi/v1/mark` provides markPrice, bidIV/askIV, markIV, delta, riskFreeInterest; `/eapi/v1/ticker` provides bidPrice, askPrice, volume, amount; `/eapi/v1/exchangeInfo` provides expiry, strike, side, underlying, unit and status.
- Implemented `probability_gap_option_chain.build_option_chain_slice` to persist a bounded reference-near slice, defaulting to three strikes below and three at/above reference for both CALL and PUT.
- Implemented `estimate_call_spread_digital` with `digital_rn ≈ -exp(r*tau) * dCallPrice/dK`, bounded probability output, monotonicity/data-quality checks, and explicit `horizon_mismatch` status when option expiry is not within 60 minutes of Polymarket market end.
- Extended SQLite snapshots with `option_chain_slice_json`, slice count/source/expiry, horizon mismatch minutes, and smile/call-spread probability/status/reason. Payload serialization is now recursive so nested Decimal/datetime chain rows are safe.
- Added `iv_digital_smile_call_spread_v2` to model-evolution scorecards and feasibility reporting. When chain data exists but expiry is not aligned, report status is `blocked_by_horizon_mismatch` instead of generic missing data.
- Verification: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_option_chain.py test/controllers/test_probability_gap_forward.py test/controllers/test_probability_gap_sampling.py test/controllers/test_probability_gap_model_evolution.py test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py` passed with `39 passed, 1 existing pytest config warning`.
- Verification: `python -m py_compile controllers/generic/probability_gap_option_chain.py controllers/generic/probability_gap_forward.py controllers/generic/probability_gap_scanner.py controllers/generic/probability_gap_sampling.py controllers/generic/probability_gap_model_evolution.py scripts/probability_gap_intraday_sampling.py scripts/probability_gap_model_evolution.py` passed.
- Live smoke: `PYTHONPATH=. python scripts/probability_gap_intraday_sampling.py --iterations 1 --sleep-seconds 1 --db-path .yxg/data/probability_gap_wu013_smoke.sqlite --reset-db` produced 2 rows. The tradable May 9 BTC 1d row stored `option_chain_slice_count=12`, source `binance_eapi_mark_ticker`, expiry `2026-05-09T08:00:00+00:00`, and `smile_call_spread_status=horizon_mismatch` with mismatch `480.0` minutes.
- Smoke report: `.yxg/data/probability_gap_wu013_smoke.sqlite` shows `iv_digital_smile_call_spread_v2` status `blocked_by_horizon_mismatch`, `supported_snapshots=0`, `status_counts={"horizon_mismatch": 1}`. This means data is now captured, but direct call-spread probability is correctly rejected for current BTC 1d horizon mismatch.

## Notes
- This WU should treat horizon mismatch as a first-class output, not a warning hidden inside logs.
- Current conclusion: promote chain-slice collection into the next clean sampler, but do not promote smile/call-spread fair value into live decisions for BTC 1d unless a future market has option expiry aligned with the Polymarket end time or a later WU implements a horizon-adjusted smile model.
