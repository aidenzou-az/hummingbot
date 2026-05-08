---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-004
slug: wu-004-btc-1d
title: 基于外部论文/评估反馈，开 WU-004：将 BTC 1d Probability Gap 的 Binance fair value 从 CALL delta proxy 升级为 IV-implied digital probability，使用 Polymarket 结算 horizon 重算 P(BTCUSDT > reference_price)，替换经验化 spot_option_blend；加入 Polymarket crypto taker fee/maker fee 后的 edge 计算，输出 maker/taker 两套 edge；采样记录 IV、tau、sigma、d2/p_up、fee、gamma/high-risk zone 等 provenance；更新 replay 以基于新 fair value、费用和风险过滤评估机会，并为后续 maker/paper trading 提供门槛。
status: review
priority: medium
owner_role: planner
created_at: "2026-05-03"
updated_at: "2026-05-03"
---

# Work Unit

## Objective

Upgrade the BTC 1d Probability Gap model from a CALL-delta proxy into an IV-implied digital-probability fair value engine. The work should estimate `P(BTCUSDT at Polymarket settlement > reference_price)` using Binance options IV and the Polymarket settlement horizon, replace the empirical `spot_option_blend`, calculate fee-aware maker and taker edges, persist the new model provenance into the sampling corpus, and update replay so opportunity conclusions are based on executable edge after fees and risk filters rather than raw delta-vs-ask gaps.

## In Scope
- Replace the current `CALL delta ~= probability` signal with an IV-based digital probability model for BTC Up/Down Daily markets.
- Use Binance options data to derive or select an implied volatility estimate around the Polymarket `reference_price`.
- Use the Polymarket market's own `end_time` as the probability horizon even when the selected Binance option expiry differs from that settlement time.
- Compute `p_up = P(S_T > reference_price)` and `p_down = 1 - p_up` using an inspectable Black-Scholes-style digital probability formula.
- Keep a fallback mode for cases where Binance IV is missing or unusable, but mark those rows as lower-confidence and non-tradable unless explicitly allowed by config.
- Replace `spot_option_blend` with a model that uses spot or forward as `S/F`, IV as `sigma`, and Polymarket remaining time as `tau`.
- Add fee-aware edge calculations for Polymarket crypto markets, including taker fee and maker-fee assumptions.
- Output separate maker and taker edge fields for `UP` and `DOWN`.
- Add dynamic risk provenance fields needed to evaluate edge quality: `tau`, `sigma`, `d2`, `p_up`, `p_down`, `prob_delta`, high-gamma/risk-zone classification, option expiry mismatch, and model confidence.
- Persist the new fields in SQLite snapshots without breaking existing replay on older sampled rows.
- Update replay entry and exit evaluation to support fee-aware taker replay and maker-style quoted-edge analysis.
- Add configurable filters for minimum edge after fees, minimum edge relative to recent model error, high-gamma exclusion or widening, and near-settlement safety.
- Preserve the existing BTC 1d lifecycle sampling logic, forced-exit boundaries, and complement-consistent UP/DOWN book handling.
- Document the resulting model contract clearly enough for a later paper-trading or maker-execution work unit to consume.

## Out Of Scope
- Authenticated Polymarket trading, order signing, order placement, cancellation, or live inventory management.
- A full paper-trading engine with persistent virtual positions.
- Production maker quoting logic that manages live orders on the CLOB.
- Generalizing the model to non-BTC, non-daily, sports, politics, or non-binary markets.
- Replacing the current launchd sampling scheduler unless the new schema requires a small compatible argument or logging update.
- Full websocket migration for Binance or Polymarket.
- Claiming strategy profitability from pre-upgrade historical samples that used the old delta-proxy fair value.
- Implementing a learned calibration layer with final weights unless enough labeled data already exists; this task may add the fields and replay hooks needed for calibration.

## Expected Touch Points
- [controllers/generic/probability_gap_scanner_utils.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner_utils.py:1)
- [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1)
- [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1)
- [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1)
- [test/controllers/test_probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_sampling.py:1)
- `test/controllers/` or `test/hummingbot/strategy_v2/controllers/` for new scanner/model tests if dependency state allows.
- `.yxg/data/probability_gap_samples_postfix.sqlite` as an existing corpus that must remain readable.
- `.yxg/work/active/WU-004-wu-004-btc-1d.md`

## Dependencies
- WU-002 scanner implementation and WU-003 sampling/replay persistence.
- Existing live Binance public endpoints used by the scanner: options mark data, options exchange info, spot ticker, and spot klines.
- Polymarket BTC Up/Down Daily Gamma market metadata and CLOB top-of-book fields already captured by WU-003.
- Official Polymarket fee model for crypto taker fees and maker fee assumptions.
- Sufficient live samples after the schema upgrade to evaluate the new model; old delta-proxy samples can be used for migration tests but not final model-quality conclusions.

## Assumptions
- Binance option mark data exposes enough IV or IV-adjacent fields to estimate `sigma`; if direct IV is unavailable or inconsistent, the task may derive IV from option marks or keep the row observable-only.
- For BTC 1d horizons, using spot as a first forward approximation is acceptable for the initial model if funding/borrow adjustment is recorded as a known limitation.
- The relevant Polymarket BTC 1d event remains a binary `UP/DOWN` market settling against Binance `BTCUSDT`.
- The first version should favor transparent formulas and explicit provenance over a black-box calibrated model.
- Maker execution and taker execution require different edge calculations; replay should not collapse them into one generic `best_net_edge`.
- Historical calibration will require labeled final outcomes and should be built on post-upgrade snapshots rather than inferred from the old delta-proxy corpus.

## Risks
- Binance option IV fields may be missing, stale, or named differently than expected, forcing a fallback to mark-price IV inversion or observable-only rows.
- A Black-Scholes digital probability with crypto spot as forward can still be biased during funding extremes, macro events, or sharp one-way BTC moves.
- Near `S ~= reference_price`, probability delta/gamma can become extremely high; small latency or spot moves can erase apparent edge.
- Fee-aware taker edge may eliminate many previously reported opportunities, reducing sample count but improving validity.
- Schema migration can break replay if older rows are not handled with sensible defaults.
- If the new model is applied to old samples without clear versioning, replay summaries could mix incompatible fair-value definitions.
- The external evaluation suggests maker-style trading may be superior, but building maker execution before fair value is corrected would compound model error.
- Official fee schedules can change; hardcoded fee values must be configurable or dynamically discoverable where practical.

## Plan
1. Inventory Binance option mark and metadata fields currently returned by live `/eapi/v1/mark` and `/eapi/v1/exchangeInfo`, especially IV, mark price, strike, expiry, side, and Greeks.
2. Define a versioned fair-value model contract: inputs, formulas, units, fallback behavior, confidence classification, and output fields.
3. Implement IV extraction or derivation around `reference_price`, using interpolation across neighboring strikes and recording selected expiry and strike provenance.
4. Replace the current `spot_option_blend` path with an IV-implied digital probability calculation on the Polymarket settlement horizon.
5. Add probability risk metrics such as `prob_delta`, high-gamma zone classification, expiry mismatch, and model confidence.
6. Add Polymarket fee-aware edge calculation with separate maker and taker fields for `UP` and `DOWN`.
7. Update scanner output, status display, and SQLite snapshot persistence to include the new model fields while preserving compatibility with existing rows.
8. Update replay to use model-version-aware fields, fee-aware entry thresholds, and risk filters; keep old rows readable but avoid using them for new profitability conclusions unless explicitly requested.
9. Add targeted unit tests for digital probability math, fee math, schema compatibility, and replay entry filtering.
10. Run a live smoke sample against current BTC 1d market and verify the new fields are populated and internally consistent.
11. Compare old delta-proxy signal versus new IV-digital signal on at least a small live sample, documenting where the trade conclusion changes.
12. Write findings and recommended thresholds back into this work artifact for the next paper-trading or maker-strategy task.

## Verification
- Unit tests verify that CALL delta is no longer used directly as `p_up` in the primary tradable path.
- Unit tests verify the digital probability formula for representative ITM, ATM, OTM, short-tau, and invalid-sigma cases.
- Unit tests verify `p_down = 1 - p_up` and the existing UP/DOWN bid/ask complement rules remain intact.
- Unit tests verify Polymarket crypto taker fee calculation uses `fee = shares * feeRate * p * (1 - p)` or the per-share equivalent.
- Unit tests verify maker edge and taker edge differ correctly when taker fees are non-zero.
- SQLite persistence tests verify new model fields are stored and older snapshots without those fields can still be listed or replayed safely.
- Replay tests verify fee-aware entry gating rejects opportunities that were positive before fees but negative after fees.
- Replay tests verify high-gamma or near-settlement filters can block or widen marginal entries.
- Live smoke run writes at least one BTC 1d snapshot with `model_version`, `sigma`, `tau`, `p_up`, `p_down`, fee-aware edge fields, and model confidence.
- Status output remains readable and surfaces the new fair value rather than only `binance_signal_kind=spot_option_blend`.

## Done When
- The BTC 1d scanner has a versioned IV-digital fair-value path that computes `p_up/p_down` on the Polymarket settlement horizon.
- The old delta-proxy signal is not used as the primary tradable fair value.
- Fee-aware maker and taker edge fields are available in scanner output and persisted snapshots.
- Replay can evaluate opportunities using post-fee edge and risk filters without breaking existing SQLite rows.
- Tests cover the model math, fee math, persistence compatibility, and replay filtering.
- A live smoke sample has verified the new fields against real Binance and Polymarket data.
- The work artifact records whether the new model materially changes candidate opportunities versus the old delta-proxy signal.

## Escalate If
- Binance does not provide enough reliable option IV or mark data to estimate `sigma` without adding a materially larger pricing/inversion subsystem.
- The live option chain does not have strikes close enough to `reference_price` for stable interpolation.
- Fee data cannot be reliably determined from static category assumptions and requires authenticated or per-token CLOB fee lookup before correctness can be claimed.
- The model produces unstable probabilities near expiry that require a broader risk model before any replay conclusion is meaningful.
- Implementing this cleanly requires a paper-trading inventory model or live order lifecycle, which is intentionally out of scope.
- Tests are blocked by dependency environment issues in a way that prevents validating the new model math or replay behavior.

## Evidence Log
- Current implementation evidence: WU-003 samples show `binance_signal_kind=spot_option_blend`; scanner code currently interpolates Binance CALL `delta` around `reference_price` and blends it with an empirical spot-distance signal when option expiry and Polymarket settlement do not perfectly align.
- Current implementation evidence: `calculate_probability_gap` currently compares `binance_signal` to Polymarket `UP`/`DOWN` asks and subtracts a fixed estimated cost buffer, not a per-market taker fee formula.
- External evaluation evidence: CALL delta is a hedge sensitivity and is not strictly the risk-neutral `P(S_T > K)`; under Black-Scholes-style models, CALL delta corresponds to `N(d1)` while digital/ITM probability corresponds more closely to `N(d2)`.
- External evaluation evidence: option expiry mismatch should be handled by using the option chain to estimate volatility or distribution shape, while Polymarket `end_time` should define the probability horizon.
- External evaluation evidence: Polymarket crypto taker fee should be modeled as `shares * feeRate * p * (1 - p)` with maker fee assumed zero under the current public fee schedule; therefore thin apparent edges can disappear after fees.
- Strategy design evidence: The next reliable step is fair-value correctness and fee-aware replay, not live maker execution.
- Live endpoint inventory on 2026-05-03: Binance `/eapi/v1/mark` returns `markIV`, `bidIV`, `askIV`, `delta`, `gamma`, `vega`, `theta`, `markPrice`, and `riskFreeInterest`; `/eapi/v1/exchangeInfo` provides `optionSymbols` with `underlying`, `side`, `strikePrice`, and `expiryDate`. This is enough for an inspectable first-pass IV-digital model without mark-price IV inversion.
- Implementation update on 2026-05-03: [controllers/generic/probability_gap_scanner_utils.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner_utils.py:1) now includes `iv_digital_v1`, using interpolated `markIV`, spot as first forward approximation, Polymarket settlement `tau`, and `d2`/normal-CDF probability to compute `fair_value_up` and `fair_value_down`.
- Implementation update on 2026-05-03: the scanner now records `model_version`, `fair_value_up/down`, `option_iv`, `tau_years`, `d2`, `prob_delta`, `gamma_risk`, `model_confidence`, `expiry_mismatch_minutes`, IV strike provenance, and fee-aware maker/taker edge fields.
- Implementation update on 2026-05-03: `net_edge_up/down` and `best_net_edge` now represent fee-aware taker edge for new `iv_digital_v1` rows; maker edge is recorded separately as `maker_edge_up/down`.
- Implementation update on 2026-05-03: low model-confidence rows and high-gamma rows are downgraded to `observable` by default unless config explicitly allows them, so they do not seed tradable opportunities or replay entries.
- Implementation update on 2026-05-03: [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1) now migrates SQLite snapshots with new optional IV/fee/model columns while preserving older rows.
- Tooling update on 2026-05-03: default live sampling DB/log paths were moved to `.yxg/data/probability_gap_samples_iv_v1.sqlite` and `/tmp/probability_gap_sampling_iv_v1.log` so post-WU-004 data does not mix with the old delta-proxy corpus.
- Verification on 2026-05-03: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_sampling.py` passed with `8 passed`, covering digital probability, fee-aware edge math, SQLite persistence of new fields, existing replay gating, and complement-consistent `DOWN` replay.
- Verification on 2026-05-03: `python -m compileall` passed for the scanner, scanner utils, sampling module, and intraday sampling script.
- Live smoke on 2026-05-03: `scripts/probability_gap_intraday_sampling.py --iterations 1 --db-path .yxg/data/probability_gap_samples_iv_v1_smoke.sqlite --reset-db` wrote two rows. The active May 3 BTC market was captured as `observable / low_model_confidence` with `binance_signal_kind=iv_digital`, `model_version=iv_digital_v1`, `option_iv=0.28951070`, `tau_years=0.0004864885764205987`, `fair_value_up=0.6929725705702567`, and `expiry_mismatch_minutes=959.99999999999994`; this confirms low-confidence expiry mismatch no longer becomes a tradable opportunity.

## Notes
- This work should preserve the current 7-day sampler while the model changes. Existing live sampling can continue, but post-upgrade profitability analysis must distinguish old delta-proxy rows from new IV-digital rows.
- A later WU can convert the fair-value output into actual maker quoting or paper trading once WU-004 proves the new model and replay filters are coherent.
