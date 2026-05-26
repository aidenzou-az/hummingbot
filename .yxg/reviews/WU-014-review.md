---
artifact_type: review
schema_version: "1.0"
kernel_version: "1"
id: WU-014-review
target_work_id: WU-014
verdict: pass
created_at: "2026-05-10"
updated_at: "2026-05-10"
---

# Review

## Scope Under Review
- Work unit: WU-014
- Change set: [controllers/generic/probability_gap_model_evolution.py], [controllers/generic/probability_gap_option_chain.py], [controllers/generic/probability_gap_sampling.py], [scripts/probability_gap_model_evolution.py], [scripts/probability_gap_intraday_sampling.py], [scripts/probability_gap_sampling_schedule.sh], [test/controllers/test_probability_gap_model_evolution.py], [test/controllers/test_probability_gap_option_chain.py], .yxg/work/active/WU-014-wu-014-btc-1d.md
- Evaluator: yxg

## Contract
- Intended outcome: Build an offline horizon-adjusted smile candidate for BTC 1d probability-gap research.
- Required checks: Unit tests pass for smile sigma extraction and horizon projection.; Unit tests pass for missing/invalid chain rows with explicit blocked reasons.; Model-evolution report includes the new horizon-adjusted smile candidate and compact scorecard.; Smoke report against `.yxg/data/probability_gap_samples_wu013_clean.sqlite` runs without changing the online sampler.; Existing relevant tests continue to pass.

## Findings
- Repository contains unrelated changes outside the current work: .yxg/data/probability_gap_settlements.json, controllers/generic/probability_gap_sampling.py, controllers/generic/probability_gap_scanner.py, scripts/com.hummingbot.probability-gap-sampling.plist, scripts/probability_gap_intraday_sampling.py, scripts/probability_gap_sampling_schedule.sh, test/controllers/test_probability_gap_sampling.py, controllers/generic/probability_gap_forward.py, controllers/generic/probability_gap_model_evolution.py, controllers/generic/probability_gap_option_chain.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_forward.py, test/controllers/test_probability_gap_model_evolution.py, test/controllers/test_probability_gap_option_chain.py

## Verification Results
- Planned checks reviewed: Unit tests pass for smile sigma extraction and horizon projection.; Unit tests pass for missing/invalid chain rows with explicit blocked reasons.; Model-evolution report includes the new horizon-adjusted smile candidate and compact scorecard.; Smoke report against `.yxg/data/probability_gap_samples_wu013_clean.sqlite` runs without changing the online sampler.; Existing relevant tests continue to pass.
- WU-013 live smoke captured 12 reference-near option rows per tradable snapshot and marked direct call-spread as `horizon_mismatch` because option expiry was 480 minutes away from Polymarket market end.
- Current online WU-013 clean sampling should continue during WU-014; do not stop or reconfigure it as part of this work.
- Implemented `estimate_horizon_smile_sigma` using local mark-IV aggregation by strike and variance interpolation around `reference_price`.
- Added offline model candidate `iv_digital_horizon_smile_v2`: it does not use direct 08:00 UTC call-spread probability; it uses local smile sigma and projects to Polymarket `market_end_time`, preferring WU-012 `estimated_forward_price` when available.
- Validator summary: 0 error(s), 0 warning(s), 0 info finding(s).

## Verdict
- Status: pass
- Reason: Contract satisfied and work may be considered done.

## Follow-Up
- Run cleanup to archive completed work and refresh baseline/state artifacts.
- Suggested commit trailer: YXG-Work: WU-014
- Inspect unrelated repository changes: .yxg/data/probability_gap_settlements.json, controllers/generic/probability_gap_sampling.py, controllers/generic/probability_gap_scanner.py, scripts/com.hummingbot.probability-gap-sampling.plist, scripts/probability_gap_intraday_sampling.py, scripts/probability_gap_sampling_schedule.sh, test/controllers/test_probability_gap_sampling.py, controllers/generic/probability_gap_forward.py, controllers/generic/probability_gap_model_evolution.py, controllers/generic/probability_gap_option_chain.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_forward.py, test/controllers/test_probability_gap_model_evolution.py, test/controllers/test_probability_gap_option_chain.py
