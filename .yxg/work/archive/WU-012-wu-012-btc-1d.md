---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-012
slug: wu-012-btc-1d
title: WU-012: BTC 1d Binance forward/basis sampling + forward-adjusted iv digital. 基于 WU-011 结论，当前 iv_digital_forward_rf_v2 只是 risk-free fallback，因为没有真实 futures basis。目标是补 Binance forward/basis 数据采样与离线 forward-adjusted IV digital 候选：采集/保存 spot price、perp mark price、funding rate、next funding time、可用 delivery futures price、estimated_forward_price、basis_annualized，并用 Polymarket market_end_time horizon 计算 F(T)，再评估 p_up = N((ln(F/K)-0.5*sigma^2*tau)/(sigma*sqrt(tau)))。范围：先离线采样字段、存储、报告和 scorecard；不替换 live scanner、不接实盘、不做 paper trading。验证复用 WU-010/WU-011 scorecard，并要求与 raw iv_digital_v1、naive baselines 对比。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-09"
updated_at: "2026-05-09"
---

# Work Unit

## Objective

Add reliable Binance forward/basis data collection and an offline forward-adjusted IV digital model candidate for BTC 1d probability-gap research. This work exists because WU-011 proved the current `iv_digital_forward_rf_v2` is only a risk-free fallback and cannot represent crypto carry without futures basis or funding data.

The outcome should be a repeatable sampler/report path that stores forward inputs, estimates `F(T)` for the Polymarket `market_end_time` horizon, and evaluates a forward-adjusted digital probability candidate against raw `iv_digital_v1`.

## In Scope
- Extend offline/live sampling payloads or auxiliary persistence with forward/basis inputs:
  - Binance spot price
  - Binance perpetual mark price
  - current/next funding rate and next funding time
  - delivery futures price when available for a useful BTC expiry
  - estimated forward price for Polymarket `market_end_time`
  - basis or funding-implied carry, annualized where meaningful
- Add deterministic forward-estimation logic with clear source precedence:
  - delivery futures closest to market end if available and reliable
  - otherwise perp mark plus funding/carry approximation
  - otherwise explicit spot fallback marked as degraded
- Add offline model candidate `iv_digital_forward_basis_v2` using `F(T)`:
  - `p_up = N((ln(F/K) - 0.5*sigma^2*tau) / (sigma*sqrt(tau)))`
- Add schema/report fields needed to inspect source, timestamp, horizon, and fallback reason.
- Evaluate the candidate with WU-010/WU-011 scorecard against raw `iv_digital_v1`, naive baselines, and available raw candidates.

## Out Of Scope
- Replacing live scanner fair-value math.
- Real trading, paper trading, order signing, balances, or order lifecycle simulation.
- Smile/call-spread digital probability; that belongs to WU-013.
- Full futures curve modeling beyond the closest useful BTC delivery/perp basis approximation.
- Claiming live model superiority before enough settled markets exist.
- Adding opaque ML or calibration on top of the forward candidate.

## Expected Touch Points
- [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1)
- [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1)
- [controllers/generic/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_model_evolution.py:1)
- [controllers/generic/probability_gap_forward.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_forward.py:1)
- [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1)
- [scripts/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_model_evolution.py:1)
- [test/controllers/test_probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_sampling.py:1)
- [test/controllers/test_probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_model_evolution.py:1)
- [test/controllers/test_probability_gap_forward.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_forward.py:1)
- `.yxg/work/active/WU-012-wu-012-btc-1d.md`

## Dependencies
- WU-011 raw candidate feasibility report.
- WU-010 settlement-aware scorecard and naive-baseline checks.
- Binance public endpoints for spot, perp/funding, and delivery futures metadata/prices.
- Existing sampler and SQLite snapshot persistence.

## Assumptions
- Perp/funding approximation is acceptable as a documented fallback when dated delivery futures are absent or unusable for the Polymarket horizon.
- Forward/basis effects may be small for BTC 1d, so the correct result may be "no material improvement".
- All forward data must be timestamped close enough to the snapshot to be useful.

## Risks
- Binance delivery futures may not have a useful expiry close to Polymarket daily market end.
- Funding-rate extrapolation can be wrong during stressed markets.
- Adding data fields can make old SQLite corpora partially sparse; reports must handle missing forward fields cleanly.
- A forward candidate can appear better from tiny samples while not improving out-of-sample performance.

## Plan
1. Identify Binance endpoints and fields for BTC spot, perp mark/funding, and delivery futures prices.
2. Add a small forward/basis data model and source-precedence function.
3. Extend sampler payload and SQLite schema/listing logic to persist forward fields.
4. Implement `iv_digital_forward_basis_v2` as an offline model candidate.
5. Add feasibility/fallback reporting for delivery, perp, and spot-only sources.
6. Run a smoke sample or use live fetch where possible to verify forward fields populate.
7. Run model-evolution scorecard on the updated corpus or a smoke corpus.
8. Record whether forward/basis data materially changes probabilities or remains a negligible/degraded candidate.

## Verification
- Unit tests cover forward price estimation from delivery futures, perp/funding fallback, and spot fallback.
- Unit tests cover missing-data behavior and source/fallback labels.
- Unit tests cover SQLite persistence/listing of forward fields.
- Unit tests cover `iv_digital_forward_basis_v2` probability bounds and complement consistency.
- A local command produces a report showing forward source coverage and scorecard results.

## Done When
- Forward/basis fields are collected or explicitly marked unavailable/degraded in sampled snapshots.
- Offline report shows coverage by forward source and candidate performance against raw `iv_digital_v1`.
- The work artifact states whether forward/basis should be promoted, tracked, or rejected.
- Targeted tests pass.

## Escalate If
- Binance endpoints do not expose usable delivery/perp/funding fields in the current environment.
- Forward data is too sparse or stale to align with Polymarket market snapshots.
- The implementation would require live trading/account permissions rather than public market data.

## Evidence Log
- WU-011 showed `iv_digital_forward_rf_v2` is effectively identical to raw `iv_digital_v1` because true futures basis is not currently stored.
- Implemented `probability_gap_forward.estimate_forward_basis` with source precedence: close delivery future, then perp mark with funding metadata, then explicit `spot_fallback`. Live scanner now joins Binance COIN-M `premiumIndex` prices with `exchangeInfo.deliveryDate` so delivery candidates have real expiry timestamps when useful.
- Extended live scanner snapshots and SQLite persistence with `forward_source`, `estimated_forward_price`, `basis_annualized`, perp mark/index/funding fields, delivery fields, and fallback reason.
- Added offline candidate `iv_digital_forward_basis_v2` and feasibility/source coverage reporting in the WU-010/WU-011 model-evolution report.
- Verification: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_forward.py test/controllers/test_probability_gap_sampling.py test/controllers/test_probability_gap_model_evolution.py test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py` passed with `35 passed, 1 existing pytest config warning`.
- Verification: `python -m py_compile controllers/generic/probability_gap_forward.py controllers/generic/probability_gap_scanner.py controllers/generic/probability_gap_sampling.py controllers/generic/probability_gap_model_evolution.py scripts/probability_gap_intraday_sampling.py scripts/probability_gap_model_evolution.py` passed.
- Live smoke: `PYTHONPATH=. python scripts/probability_gap_intraday_sampling.py --iterations 1 --sleep-seconds 1 --db-path .yxg/data/probability_gap_wu012_smoke.sqlite --reset-db` produced 2 rows, including one tradable BTC 1d snapshot with `forward_source=perp_mark`, `estimated_forward_price=80385.04563768`, `perp_index_price=80428.46782609`, `perp_last_funding_rate=-0.00002763`.
- Smoke report: `.yxg/data/probability_gap_wu012_smoke.sqlite` shows `iv_digital_forward_basis_v2` feasibility coverage 1/1 tradable snapshot with `forward_source_counts={"perp_mark": 1}`. It has no settlement score yet because the smoke market is not settled.
- Smoke comparison on the live row: raw `fair_up=0.6628106319382792`, risk-free forward fair was effectively identical, while basis-adjusted fair was `0.6379110783181831`; the gap came from perp mark being below spot over a short horizon. This confirms the new candidate is no longer the old risk-free fallback.

## Notes
- This WU should produce data and an offline candidate first. A later WU should decide whether to wire a successful forward-adjusted model into live scanner logic.
- Current old corpora do not contain forward fields, so `iv_digital_forward_basis_v2` can only be evaluated on newly sampled snapshots. Do not infer model superiority from the one-row smoke.
