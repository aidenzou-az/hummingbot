---
artifact_type: review
schema_version: "1.0"
kernel_version: "1"
id: WU-005-review
target_work_id: WU-005
verdict: pass
created_at: "2026-05-05"
updated_at: "2026-05-05"
---

# Review

## Scope Under Review
- Work unit: WU-005
- Change set: [controllers/generic/probability_gap_sampling.py], A new analysis/replay module if needed, likely under `controllers/generic/` or `scripts/`., A new CLI script for offline execution-aware replay and bucket reporting, likely under [scripts/], [test/controllers/test_probability_gap_sampling.py], .yxg/data/probability_gap_samples_iv_v1.sqlite` as the primary current corpus., .yxg/work/active/WU-005-wu-004-iv-digital.md
- Evaluator: yxg

## Contract
- Intended outcome: Build a small but complete execution-aware research loop on top of WU-004 `iv_digital_v1` BTC 1d fair value snapshots. The outcome should freeze the current fair-value model contract, enrich sampled snapshots with future-window diagnostic labels, implement comparable taker and maker replay modes, and produce bucketed reports that answer whether fee-aware model edge can realistically convert into positive EV under historical Polymarket book paths before any paper or live trading work begins.
- Required checks: Unit tests verify future-window labels choose the first snapshot at or after each target horizon and handle missing future snapshots safely.; Unit tests verify `max_bid_reachable_next_5m` and `min_ask_reachable_next_5m` are side-specific and use complement-consistent UP/DOWN prices.; Unit tests verify taker baseline replay remains deterministic and comparable with prior replay behavior.; Unit tests verify taker-hold replay does not exit solely because `edge_decay` fires.; Unit tests verify maker-first fill assumptions differ as expected: optimistic, conservative, and strict.; Unit tests verify cooldown and one-position-per-market rules prevent fragmented re-entry loops.; Unit tests verify take-profit, stop-loss, time-stop, and forced-exit reasons are recorded correctly.; Unit tests verify maker adverse selection labels flag adverse fair movement, edge disappearance, bid below entry, and stop-loss touch after fill.; Unit tests verify parameter grid results include all requested parameter dimensions and can identify stable regions separately from best single rows.; Unit tests verify bucket reports group by gamma, time-to-expiry, moneyness, side, edge bucket, and replay mode.; A local report can run against `.yxg/data/probability_gap_samples_iv_v1.sqlite` without modifying the live sampler.; The report clearly separates `tradable`, `observable`, and rejected lifecycle rows.

## Findings
- Repository contains unrelated changes outside the current work: controllers/generic/probability_gap_execution_replay.py, controllers/generic/probability_gap_sampling.py, controllers/generic/probability_gap_scanner.py, controllers/generic/probability_gap_scanner_utils.py, plugins/, scripts/com.hummingbot.probability-gap-sampling.plist, scripts/probability_gap_execution_replay.py, scripts/probability_gap_intraday_sampling.py, scripts/probability_gap_sampling_schedule.sh, test/controllers/, test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py

## Verification Results
- Planned checks reviewed: Unit tests verify future-window labels choose the first snapshot at or after each target horizon and handle missing future snapshots safely.; Unit tests verify `max_bid_reachable_next_5m` and `min_ask_reachable_next_5m` are side-specific and use complement-consistent UP/DOWN prices.; Unit tests verify taker baseline replay remains deterministic and comparable with prior replay behavior.; Unit tests verify taker-hold replay does not exit solely because `edge_decay` fires.; Unit tests verify maker-first fill assumptions differ as expected: optimistic, conservative, and strict.; Unit tests verify cooldown and one-position-per-market rules prevent fragmented re-entry loops.; Unit tests verify take-profit, stop-loss, time-stop, and forced-exit reasons are recorded correctly.; Unit tests verify maker adverse selection labels flag adverse fair movement, edge disappearance, bid below entry, and stop-loss touch after fill.; Unit tests verify parameter grid results include all requested parameter dimensions and can identify stable regions separately from best single rows.; Unit tests verify bucket reports group by gamma, time-to-expiry, moneyness, side, edge bucket, and replay mode.; A local report can run against `.yxg/data/probability_gap_samples_iv_v1.sqlite` without modifying the live sampler.; The report clearly separates `tradable`, `observable`, and rejected lifecycle rows.
- WU-004 changed the scanner to persist `iv_digital_v1` fields including `fair_value_up/down`, `option_iv`, `tau_years`, `d2`, `prob_delta`, `gamma_risk`, `model_confidence`, `expiry_mismatch_minutes`, and fee-aware `maker_edge_*` / `taker_edge_*`.
- WU-004 moved live sampling defaults to `.yxg/data/probability_gap_samples_iv_v1.sqlite` and `/tmp/probability_gap_sampling_iv_v1.log`.
- May 4 replay using the existing taker-style logic was weak: thresholds around `0.03-0.05` produced negative average realized move, showing current replay is not sufficient as an execution strategy.
- Discussion on 2026-05-05 established that the next problem is no longer just calculating edge, but converting edge into executable positive EV through maker-first execution rules and better replay diagnostics.
- Validator summary: 0 error(s), 0 warning(s), 0 info finding(s).

## Verdict
- Status: pass
- Reason: Contract satisfied and work may be considered done.

## Follow-Up
- Run cleanup to archive completed work and refresh baseline/state artifacts.
- Suggested commit trailer: YXG-Work: WU-005
- Inspect unrelated repository changes: controllers/generic/probability_gap_execution_replay.py, controllers/generic/probability_gap_sampling.py, controllers/generic/probability_gap_scanner.py, controllers/generic/probability_gap_scanner_utils.py, plugins/, scripts/com.hummingbot.probability-gap-sampling.plist, scripts/probability_gap_execution_replay.py, scripts/probability_gap_intraday_sampling.py, scripts/probability_gap_sampling_schedule.sh, test/controllers/, test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py
