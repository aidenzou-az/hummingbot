---
artifact_type: review
schema_version: "1.0"
kernel_version: "1"
id: WU-011-review
target_work_id: WU-011
verdict: pass
created_at: "2026-05-09"
updated_at: "2026-05-09"
---

# Review

## Scope Under Review
- Work unit: WU-011
- Change set: [controllers/generic/probability_gap_model_evolution.py], [scripts/probability_gap_model_evolution.py], [test/controllers/test_probability_gap_model_evolution.py], Possibly a small helper module under `controllers/generic/` if raw candidate logic becomes too large., .yxg/data/probability_gap_samples_wu006_clean.sqlite` as current clean corpus., .yxg/data/probability_gap_settlements.json` as settlement cache., .yxg/work/active/WU-011-wu-btc-1d-iv.md
- Evaluator: yxg

## Contract
- Intended outcome: Run a small offline research pass for `iv_digital_v2` raw probability candidates. The goal is to improve the probability source itself, not to tune calibration or ensemble weights. The work should determine which raw-model variants are feasible from currently stored snapshots, implement the feasible ones as offline candidates, and compare them against raw `iv_digital_v1` using the WU-010 settlement-aware scorecard.
- Required checks: Unit tests cover each raw candidate's output bounds and missing-data behavior.; Unit tests cover candidate feasibility classification.; Unit tests cover fair interval bounds and conservative edge interpretation.; A repeatable local command runs the WU-011 report against the clean corpus and settlement cache.; The report compares every implemented candidate against raw `iv_digital_v1` and naive baselines.; The report flags candidates that are blocked by missing data rather than silently omitting them.

## Findings
- Repository contains unrelated changes outside the current work: .yxg/data/probability_gap_settlements.json, controllers/generic/probability_gap_model_evolution.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_model_evolution.py

## Verification Results
- Planned checks reviewed: Unit tests cover each raw candidate's output bounds and missing-data behavior.; Unit tests cover candidate feasibility classification.; Unit tests cover fair interval bounds and conservative edge interpretation.; A repeatable local command runs the WU-011 report against the clean corpus and settlement cache.; The report compares every implemented candidate against raw `iv_digital_v1` and naive baselines.; The report flags candidates that are blocked by missing data rather than silently omitting them.
- WU-010 concluded that calibration and ensemble candidates are not ready for live adoption; raw model evolution should focus on improving the probability source itself.
- WU-010 added naive baselines and Polymarket-mid-heavy sample-bias checks; WU-011 must preserve those checks when comparing raw candidates.
- Implemented WU-011 raw candidate reporting inside `controllers/generic/probability_gap_model_evolution.py`; the existing CLI `scripts/probability_gap_model_evolution.py` now emits an `iv_digital_v2_raw_candidates` section.
- Implemented candidate feasibility checks:
- Validator summary: 0 error(s), 0 warning(s), 0 info finding(s).

## Verdict
- Status: pass
- Reason: Contract satisfied and work may be considered done.

## Follow-Up
- Run cleanup to archive completed work and refresh baseline/state artifacts.
- Suggested commit trailer: YXG-Work: WU-011
- Inspect unrelated repository changes: .yxg/data/probability_gap_settlements.json, controllers/generic/probability_gap_model_evolution.py, scripts/probability_gap_model_evolution.py, test/controllers/test_probability_gap_model_evolution.py
