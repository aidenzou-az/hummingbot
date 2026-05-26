---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-014
slug: wu-014-btc-1d
title: WU-014: BTC 1d horizon-adjusted smile model research。基于 WU-013 已经能采集 Binance option-chain slice，但 direct call-spread probability 对 BTC 1d 因 Binance option expiry 08:00 UTC 与 Polymarket market_end 16:00 UTC 固定相差 480 分钟而长期 horizon_mismatch。目标是在不修改当前线上 WU-013 clean sampling 的前提下，离线利用 option_chain_slice_json、forward/basis、reference_price、market_end_time、observed_at 等字段，构建 horizon-adjusted smile 候选模型：从 reference 附近 chain slice 提取局部 IV/variance/skew 或 smile-adjusted sigma，不直接使用 08:00 UTC digital probability，而是重新投影到 Polymarket market_end_time 的 tau，计算 P(S_T > K)，并用 WU-010/WU-011 settlement-aware scorecard 与 raw iv_digital_v1、iv_digital_forward_basis_v2、iv_digital_variance_strike_v2、naive baselines 对比。范围只做离线模型、报告、测试和可行性结论；不改当前 LaunchAgent/采集任务、不替换 live scanner fair value、不做实盘或 paper trading。验证要求能在当前 WU-013 clean DB 的已采样数据上跑 smoke report，即使 settlement 不足也要输出 coverage、blocked reason、probability delta 与数据质量。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-09"
updated_at: "2026-05-09"
---

# Work Unit

## Objective

Build an offline horizon-adjusted smile candidate for BTC 1d probability-gap research.

WU-013 proved that Binance option-chain slices can be collected, but direct call-spread digital probability is structurally mismatched for BTC 1d when Binance option expiry is 08:00 UTC and Polymarket market end is 16:00 UTC. WU-014 should reuse those collected chain slices without changing the running sampler: extract local smile/IV information around `reference_price`, project it to the Polymarket `market_end_time` horizon, and evaluate the candidate against existing raw IV, forward-basis, variance-strike, and naive baselines.

## In Scope

- Add an offline model candidate such as `iv_digital_horizon_smile_v2`.
- Read existing `option_chain_slice_json`, `reference_price`, `current_spot_price`, `estimated_forward_price`, `market_end_time`, `observed_at`, and option IV fields from sampled snapshots.
- Derive a smile-adjusted sigma using reference-near chain rows, for example:
  - local mark-IV interpolation around reference
  - variance interpolation across nearby strikes
  - skew/smile diagnostic fields for reporting
- Recompute `P(S_T > K)` for the Polymarket market end horizon:
  - do not use the 08:00 UTC direct call-spread digital probability
  - use Polymarket `market_end_time` for tau
  - prefer WU-012 forward estimate when available, otherwise fall back explicitly
- Add model-evolution scorecard support and feasibility reporting:
  - coverage
  - blocked reason
  - probability delta vs raw IV and forward-basis
  - data-quality buckets
  - settlement-aware metrics when labels exist
- Add tests for sigma extraction, horizon projection, missing-data behavior, and report output.
- Run a smoke report on the current WU-013 clean DB while online sampling continues.

## Out Of Scope

- Do not modify the current LaunchAgent, plist, sampling schedule, or WU-013 clean DB path.
- Do not replace live scanner fair value or live trading signal selection.
- Do not connect real trading, paper trading, signing, balances, or order lifecycle.
- Do not implement a full implied-density surface, local-vol model, or heavy ML calibration.
- Do not claim profitability from sparse same-day smoke data or fewer than 5-10 settled BTC 1d markets.
- Do not remove or weaken the WU-013 `horizon_mismatch` guard for direct call-spread probability.

## Expected Touch Points
- [controllers/generic/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_model_evolution.py:1)
- [controllers/generic/probability_gap_option_chain.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_option_chain.py:1)
- [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1) only if listing/parsing needs compatibility fixes
- [scripts/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_model_evolution.py:1)
- [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1) for runtime dependency preflight hardening
- [scripts/probability_gap_sampling_schedule.sh](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_sampling_schedule.sh:1) for atomic `/tmp/hb_pydeps` validation/rebuild
- [test/controllers/test_probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_model_evolution.py:1)
- [test/controllers/test_probability_gap_option_chain.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_option_chain.py:1)
- `.yxg/work/active/WU-014-wu-014-btc-1d.md`

## Dependencies
- WU-012 forward/basis sampling fields and `iv_digital_forward_basis_v2`.
- WU-013 option-chain slice persistence and explicit direct call-spread `horizon_mismatch` status.
- Existing WU-010/WU-011 settlement-aware model-evolution report.
- Current online sampler writing `.yxg/data/probability_gap_samples_wu013_clean.sqlite`.

## Assumptions
- Current WU-013 clean snapshots include enough reference-near option rows to estimate local IV/smile diagnostics.
- For BTC 1d, direct call-spread probability remains structurally mismatched, so smile information should be used as a volatility-shape input, not as direct digital probability.
- A first-pass horizon-adjusted smile model can use deterministic interpolation rather than full surface fitting.
- It is acceptable for the first report to have limited settlement metrics if the new DB has not accumulated settled markets yet.

## Risks
- Local IV interpolation may be noisy if Binance option marks are stale, sparse, wide, or inconsistent.
- Smile-adjusted sigma may not improve over the existing variance-strike IV or forward-basis candidates.
- Small early WU-013 clean samples can make probability deltas look meaningful before settlement evidence exists.
- If option-chain prices use units unexpectedly, the model could be numerically plausible but economically wrong; tests and diagnostics must expose this.

## Plan
1. Inspect WU-013 clean snapshots and confirm which chain fields are populated across tradable rows.
2. Add deterministic helpers to extract local IV/smile-adjusted sigma from `option_chain_slice_json`.
3. Implement horizon-adjusted probability projection using Polymarket `market_end_time`, WU-012 forward estimate when available, and explicit fallbacks.
4. Register the new candidate in model-evolution scorecards and feasibility reports.
5. Add probability-delta diagnostics versus raw IV, variance-strike, and forward-basis.
6. Add targeted tests for extraction, projection, missing data, and report output.
7. Run targeted tests and a smoke report on `.yxg/data/probability_gap_samples_wu013_clean.sqlite`.
8. Record whether the candidate should be promoted, tracked, or rejected pending more settled markets.

## Verification
- Unit tests pass for smile sigma extraction and horizon projection.
- Unit tests pass for missing/invalid chain rows with explicit blocked reasons.
- Model-evolution report includes the new horizon-adjusted smile candidate and compact scorecard.
- Smoke report against `.yxg/data/probability_gap_samples_wu013_clean.sqlite` runs without changing the online sampler.
- Existing relevant tests continue to pass.

## Done When
- A horizon-adjusted smile candidate is available in the offline scorecard.
- The report clearly separates direct call-spread `horizon_mismatch` from horizon-adjusted smile projection.
- Smoke output on current WU-013 clean data shows coverage, blocked reasons, probability deltas, and any available settlement-aware metrics.
- The work artifact records a decision: promote, track with more data, or reject.

## Escalate If
- Current chain slices lack enough IV/strike fields to estimate local smile reliably.
- Implementing a meaningful model requires changing the online sampler or collecting new fields.
- The required model becomes full surface fitting or calibration rather than the bounded deterministic first pass.
- Smoke diagnostics reveal unit normalization ambiguity that cannot be resolved from public Binance fields.

## Evidence Log
- WU-013 live smoke captured 12 reference-near option rows per tradable snapshot and marked direct call-spread as `horizon_mismatch` because option expiry was 480 minutes away from Polymarket market end.
- Current online WU-013 clean sampling should continue during WU-014; do not stop or reconfigure it as part of this work.
- Implemented `estimate_horizon_smile_sigma` using local mark-IV aggregation by strike and variance interpolation around `reference_price`.
- Added offline model candidate `iv_digital_horizon_smile_v2`: it does not use direct 08:00 UTC call-spread probability; it uses local smile sigma and projects to Polymarket `market_end_time`, preferring WU-012 `estimated_forward_price` when available.
- Added feasibility/status reporting and probability-delta diagnostics versus `iv_digital_v1`, `iv_digital_forward_basis_v2`, `iv_digital_variance_strike_v2`, and realized-vol digital.
- Verification: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_option_chain.py test/controllers/test_probability_gap_forward.py test/controllers/test_probability_gap_sampling.py test/controllers/test_probability_gap_model_evolution.py test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py` passed with `42 passed, 1 existing pytest config warning`.
- Verification: `python -m py_compile controllers/generic/probability_gap_option_chain.py controllers/generic/probability_gap_model_evolution.py scripts/probability_gap_model_evolution.py` passed.
- Smoke report command: `PYTHONPATH=. python scripts/probability_gap_model_evolution.py --db-path .yxg/data/probability_gap_samples_wu013_clean.sqlite --no-settlement-cache > /tmp/probability_gap_model_evolution_wu014_smoke.json`.
- Smoke report result on current WU-013 clean DB: direct `iv_digital_smile_call_spread_v2` remains `blocked_by_horizon_mismatch` with `277/277` tradable snapshots marked `horizon_mismatch`; new `iv_digital_horizon_smile_v2` is `implemented` with `277/277` supported snapshots.
- Smoke probability deltas: horizon-adjusted smile average delta versus `iv_digital_forward_basis_v2` is about `-0.0000419`, versus raw `iv_digital_v1` about `-0.02722`, versus variance-strike about `-0.02717`. Settlement score entries are still `0` because the current WU-013 clean DB has not accumulated settled labels yet.
- 收口修复：2026-05-10 发现 launchd 采样窗口后段再次出现 `module 'aiohttp' has no attribute 'ClientTimeout'`。根因是 `/tmp/hb_pydeps/aiohttp` 残缺，只剩少量 `.so`，Python 导入为空 namespace package，`aiohttp.__file__ = None`，没有 `ClientTimeout`。
- Added schedule-level dependency hardening: before starting a sampling window, `probability_gap_sampling_schedule.sh` validates `aiohttp.ClientTimeout`; if invalid, it installs required dependencies into a temporary target and atomically replaces `/tmp/hb_pydeps`.
- Added script-level dependency preflight: `probability_gap_intraday_sampling.py` now uses configurable `PROB_GAP_PYDEPS_PATH` instead of hard-coded `/tmp/hb_pydeps`, and fails fast with an explicit `aiohttp_invalid_missing_ClientTimeout` error if the dependency is still invalid.
- Smoke after dependency rebuild repaired `aiohttp` (`/tmp/hb_pydeps/aiohttp/__init__.py`, version `3.13.5`, `ClientTimeout=True`) but exposed a separate concurrent HTTP issue: `_request_json` closed the shared aiohttp session from inside one failed request, causing sibling `asyncio.gather` requests to fail with `Connector is closed`.
- Fixed scanner HTTP retry behavior so one request failure no longer closes the shared session while other concurrent requests are in flight.
- Closeout verification: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_option_chain.py test/controllers/test_probability_gap_forward.py test/controllers/test_probability_gap_sampling.py test/controllers/test_probability_gap_model_evolution.py test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py` passed again with `42 passed, 1 existing pytest config warning`.
- Closeout verification: `PROB_GAP_PYDEPS_PATH=/tmp/hb_pydeps PYTHONPATH=/tmp/hb_pydeps:. /Users/bytedance/.pyenv/versions/3.12.4/bin/python -m py_compile controllers/generic/probability_gap_scanner.py scripts/probability_gap_intraday_sampling.py controllers/generic/probability_gap_model_evolution.py controllers/generic/probability_gap_option_chain.py` passed.
- Closeout live smoke: `PROB_GAP_PYDEPS_PATH=/tmp/hb_pydeps PYTHONPATH=/tmp/hb_pydeps:. /Users/bytedance/.pyenv/versions/3.12.4/bin/python -u scripts/probability_gap_intraday_sampling.py --iterations 1 --sleep-seconds 1 --db-path .yxg/data/probability_gap_wu014_closeout_smoke.sqlite --reset-db` completed without `ClientTimeout` or `Connector is closed`.
- Closeout DB check: the smoke DB recorded `bitcoin-up-or-down-on-may-10-2026` as `observable` with `forward_source=perp_mark`, `option_chain_slice_count=12`, `smile_call_spread_status=horizon_mismatch`, and non-empty `option_chain_slice_json`.

## Notes
- WU-014 is intended to prevent the 10-day WU-013 clean sampling window from being wasted: already-collected chain slices should be usable retroactively for horizon-adjusted research.
- Current decision: track `iv_digital_horizon_smile_v2` in offline reports, but do not promote it to live fair value yet. Early data shows it is almost identical to forward-basis after horizon projection; settlement evidence is not available yet.
