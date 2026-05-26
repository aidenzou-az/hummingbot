---
artifact_type: review
schema_version: "1.0"
kernel_version: "1"
id: WU-010-review
target_work_id: WU-010
verdict: pass
created_at: "2026-05-09"
updated_at: "2026-05-09"
---

# Review

## Scope Under Review
- Work unit: WU-010
- Change set: [controllers/generic/probability_gap_model_validation.py], A new or extended offline model-comparison/calibration helper under `controllers/generic/`., [scripts/probability_gap_model_validation.py], [test/controllers/test_probability_gap_model_validation.py], .yxg/data/probability_gap_samples_wu006_clean.sqlite` as the current clean sample corpus., .yxg/data/probability_gap_settlements.json` as durable settlement cache., .yxg/work/active/WU-010-wu-010-btc-1d.md
- Evaluator: yxg

## Contract
- Intended outcome: Build an offline, settlement-aware model-evolution research layer for the BTC 1d probability-gap strategy. The work must start from WU-006 settlement labels and clean sampled snapshots, then determine whether probability calibration and cross-model ensemble improve on raw `iv_digital_v1` in a way that survives settlement PnL, bucket stability, and leave-one-market-out checks.
- Required checks: Unit tests cover each candidate model's probability output shape and complement consistency.; Unit tests cover calibration bucket/shrinkage behavior.; Unit tests cover ensemble weighting and probability bounds.; Unit tests or report checks cover naive baselines and prevent interpreting UP-only or DOWN-only results as model alpha.; Unit tests cover settlement scorecard calculations, including Brier/log loss and side-specific settlement PnL.; A repeatable local command runs against `.yxg/data/probability_gap_samples_wu006_clean.sqlite` and `.yxg/data/probability_gap_settlements.json`.; The report demonstrates that Phase 1 reproduces WU-006 baseline metrics within expected tolerance.; The report includes leave-one-market-out or explicitly explains why the current corpus is too small for a meaningful check.; The report separates snapshot-level metrics from market-level interpretation.

## Findings
- Repository contains unrelated changes outside the current work: controllers/generic/probability_gap_model_evolution.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_model_evolution.py

## Verification Results
- Planned checks reviewed: Unit tests cover each candidate model's probability output shape and complement consistency.; Unit tests cover calibration bucket/shrinkage behavior.; Unit tests cover ensemble weighting and probability bounds.; Unit tests or report checks cover naive baselines and prevent interpreting UP-only or DOWN-only results as model alpha.; Unit tests cover settlement scorecard calculations, including Brier/log loss and side-specific settlement PnL.; A repeatable local command runs against `.yxg/data/probability_gap_samples_wu006_clean.sqlite` and `.yxg/data/probability_gap_settlements.json`.; The report demonstrates that Phase 1 reproduces WU-006 baseline metrics within expected tolerance.; The report includes leave-one-market-out or explicitly explains why the current corpus is too small for a meaningful check.; The report separates snapshot-level metrics from market-level interpretation.
- WU-006 produced a cache-backed settlement validation layer with Binance rule 1m close labels and retry/cache hardening.
- WU-006 clean corpus currently has limited settled-market coverage, enough for pipeline validation but not enough to claim strategy profitability.
- Current `iv_digital_v1` beat reconstructed old `delta_spot_blend` on same settled tradable snapshots: raw `iv_digital_v1` had smaller but more realistic edge, while old delta/spot blend produced larger apparent edge and worse settlement PnL due to side bias.
- The strict research order is intentional: settlement objective first, calibration second, ensemble last.
- Validator summary: 0 error(s), 0 warning(s), 0 info finding(s).

## Verdict
- Status: pass
- Reason: Contract satisfied and work may be considered done.

## Follow-Up
- Run cleanup to archive completed work and refresh baseline/state artifacts.
- Suggested commit trailer: YXG-Work: WU-010
- Inspect unrelated repository changes: controllers/generic/probability_gap_model_evolution.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_model_evolution.py
