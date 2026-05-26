---
artifact_type: review
schema_version: "1.0"
kernel_version: "1"
id: WU-012-review
target_work_id: WU-012
verdict: pass
created_at: "2026-05-09"
updated_at: "2026-05-09"
---

# Review

## Scope Under Review
- Work unit: WU-012
- Change set: [controllers/generic/probability_gap_scanner.py], [controllers/generic/probability_gap_sampling.py], [controllers/generic/probability_gap_model_evolution.py], [controllers/generic/probability_gap_forward.py], [scripts/probability_gap_intraday_sampling.py], [scripts/probability_gap_model_evolution.py], [test/controllers/test_probability_gap_sampling.py], [test/controllers/test_probability_gap_model_evolution.py], [test/controllers/test_probability_gap_forward.py], .yxg/work/active/WU-012-wu-012-btc-1d.md
- Evaluator: yxg

## Contract
- Intended outcome: Add reliable Binance forward/basis data collection and an offline forward-adjusted IV digital model candidate for BTC 1d probability-gap research. This work exists because WU-011 proved the current `iv_digital_forward_rf_v2` is only a risk-free fallback and cannot represent crypto carry without futures basis or funding data.
- Required checks: Unit tests cover forward price estimation from delivery futures, perp/funding fallback, and spot fallback.; Unit tests cover missing-data behavior and source/fallback labels.; Unit tests cover SQLite persistence/listing of forward fields.; Unit tests cover `iv_digital_forward_basis_v2` probability bounds and complement consistency.; A local command produces a report showing forward source coverage and scorecard results.

## Findings
- Repository contains unrelated changes outside the current work: .yxg/data/probability_gap_settlements.json, controllers/generic/probability_gap_sampling.py, controllers/generic/probability_gap_scanner.py, test/controllers/test_probability_gap_sampling.py, controllers/generic/probability_gap_forward.py, controllers/generic/probability_gap_model_evolution.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_forward.py, test/controllers/test_probability_gap_model_evolution.py

## Verification Results
- Planned checks reviewed: Unit tests cover forward price estimation from delivery futures, perp/funding fallback, and spot fallback.; Unit tests cover missing-data behavior and source/fallback labels.; Unit tests cover SQLite persistence/listing of forward fields.; Unit tests cover `iv_digital_forward_basis_v2` probability bounds and complement consistency.; A local command produces a report showing forward source coverage and scorecard results.
- WU-011 showed `iv_digital_forward_rf_v2` is effectively identical to raw `iv_digital_v1` because true futures basis is not currently stored.
- Implemented `probability_gap_forward.estimate_forward_basis` with source precedence: close delivery future, then perp mark with funding metadata, then explicit `spot_fallback`. Live scanner now joins Binance COIN-M `premiumIndex` prices with `exchangeInfo.deliveryDate` so delivery candidates have real expiry timestamps when useful.
- Extended live scanner snapshots and SQLite persistence with `forward_source`, `estimated_forward_price`, `basis_annualized`, perp mark/index/funding fields, delivery fields, and fallback reason.
- Added offline candidate `iv_digital_forward_basis_v2` and feasibility/source coverage reporting in the WU-010/WU-011 model-evolution report.
- Validator summary: 0 error(s), 0 warning(s), 0 info finding(s).

## Verdict
- Status: pass
- Reason: Contract satisfied and work may be considered done.

## Follow-Up
- Run cleanup to archive completed work and refresh baseline/state artifacts.
- Suggested commit trailer: YXG-Work: WU-012
- Inspect unrelated repository changes: .yxg/data/probability_gap_settlements.json, controllers/generic/probability_gap_sampling.py, controllers/generic/probability_gap_scanner.py, test/controllers/test_probability_gap_sampling.py, controllers/generic/probability_gap_forward.py, controllers/generic/probability_gap_model_evolution.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_forward.py, test/controllers/test_probability_gap_model_evolution.py
