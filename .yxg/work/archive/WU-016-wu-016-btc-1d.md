---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-016
slug: wu-016-btc-1d
title: WU-016: 调整 BTC 1d probability-gap 定时采集窗口。基于 WU-015 已拆分 sampling eligibility 与 trading eligibility，当前 schedule 仍只在 12:00-17:00 和 22:00-01:00 运行，导致 00:00-12:00 early observable 与 17:00-22:00 low-confidence path 漏采。目标：只修改采集调度，不修改交易 eligibility，不改变 fair value 模型。将采集覆盖扩展为北京时间 00:00-23:45，并按阶段分频：00:00-12:00 低频约 60s，12:00-16:00 高频约 15s，16:00-22:00 中频约 30-60s，22:00-23:45 中高频约 15-30s；23:45-00:00 不采或极低频。保持 LaunchAgent 可定时触发、run_days 限制、pydeps 自修复、already_running 防重入。验证要求：脚本在不同本地时刻可计算正确 window name、end time、sleep seconds/iterations；live smoke 不 reset DB；记录当前窗口外/内行为。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-12"
updated_at: "2026-05-12"
---

# Work Unit

## Objective

Update the BTC 1d probability-gap sampling scheduler so it collects a continuous research corpus across the full useful Polymarket market day while preserving the scanner's existing trading eligibility rules. After WU-015, early and low-confidence markets can be sampled as non-tradable observations, but the current schedule still skips large parts of those paths. WU-016 should make the schedule match the new sampling model.

## In Scope
- Modify the local sampling schedule script so BTC 1d sampling covers Beijing time `00:00-23:45`.
- Add staged sampling cadence:
  - `00:00-12:00`: early observable, low frequency, target `60s`.
  - `12:00-16:00`: current strongest tradable window, high frequency, target `15s`.
  - `16:00-22:00`: post-nearest-option-expiry / low-confidence path, medium frequency, target `60s` unless implementation supports a clean `30s`.
  - `22:00-23:45`: near-expiry / exit research, target `15s-30s`.
- Keep `23:45-00:00` out of normal sampling to avoid exit-buffer and settlement noise.
- Preserve `run_days`, pydeps self-repair, logging, and already-running protection.
- Add a deterministic schedule-calculation test path or helper so the window logic can be validated without waiting for wall-clock time.
- Document exact operator behavior after the schedule change.

## Out Of Scope
- Do not modify scanner trading eligibility, including `min_minutes_before_settlement`, `max_minutes_before_settlement`, low-confidence gating, high-gamma gating, or edge thresholds.
- Do not change fair-value models, option-chain construction, forward-basis logic, replay, or settlement labeling.
- Do not reset or migrate the existing clean SQLite DB.
- Do not add real trading, paper trading, or execution logic.
- Do not solve LaunchAgent permission quirks beyond documenting any required operator reload step.

## Expected Touch Points
- [scripts/probability_gap_sampling_schedule.sh](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_sampling_schedule.sh:1)
- [scripts/com.hummingbot.probability-gap-sampling.plist](/Users/bytedance/Projects/hummingbot/scripts/com.hummingbot.probability-gap-sampling.plist:1), only if trigger cadence needs adjustment.
- A small shell-level test helper or script-level dry-run mode if needed.
- `.yxg/work/active/WU-016-wu-016-btc-1d.md`

## Dependencies
- WU-015 must remain in effect: `outside_overlap_window` snapshots are sampleable observations, not rejected-only rows.
- Existing LaunchAgent points to the repository script path, so script changes should apply on the next service start without changing the installed plist, unless the plist trigger cadence is changed.

## Assumptions
- Beijing time is the operational schedule timezone because the existing script uses local `date` and the operator is in Asia/Shanghai.
- Continuous sampling is for research corpus quality; scanner classification remains the source of truth for tradability.
- A 60s cadence is sufficient for early and post-option-expiry observable periods unless later analysis shows short-lived edges there.
- The existing 15-minute LaunchAgent `StartInterval` is acceptable if each invocation runs until the current window end and `already_running` prevents duplicates.

## Risks
- Longer daily runtime increases API calls and log volume.
- If the schedule helper is not testable with injected times, future changes may regress silently.
- If `23:45-00:00` is sampled too aggressively, settlement/top-of-book noise may pollute the research corpus.
- If old LaunchAgent processes remain running, they may need to finish naturally before the new schedule takes effect.

## Plan
1. Inspect current scheduler and plist trigger behavior.
2. Refactor schedule-window calculation into a testable/dry-run path or helper.
3. Implement the new staged windows and per-window sleep seconds.
4. Keep current DB/log/env/run-days/pydeps/already-running behavior intact.
5. Validate schedule decisions for representative Beijing times: `00:30`, `11:59`, `12:00`, `15:59`, `16:00`, `21:59`, `22:00`, `23:44`, `23:45`, `23:59`.
6. Run shell syntax checks and a safe live smoke that does not reset DB.
7. Record evidence and operator reload instructions.

## Verification
- Dry-run or helper output shows correct window name, end time, cadence, and skip behavior for representative local times.
- `bash -n scripts/probability_gap_sampling_schedule.sh` passes.
- A live one-shot smoke can run without resetting the DB.
- Existing probability-gap Python tests do not need full rerun unless Python files are touched; if they are touched, rerun focused tests.

## Done When
- The scheduler covers `00:00-23:45` with staged cadence and skips `23:45-00:00`.
- Trading eligibility remains unchanged.
- The operator can reload LaunchAgent or let the next start pick up the new script with clear instructions.
- Verification evidence is recorded in this artifact.

## Escalate If
- LaunchAgent cannot support the desired daily coverage without creating excessive overlapping processes.
- API limits or observed runtime make `00:00-23:45` coverage unsafe.
- The script cannot be tested deterministically without a larger rewrite.

## Evidence Log
- Current scheduler evidence: [scripts/probability_gap_sampling_schedule.sh](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_sampling_schedule.sh:80) only allows `12:00-17:00` and `22:00-01:00`.
- Current LaunchAgent evidence: [scripts/com.hummingbot.probability-gap-sampling.plist](/Users/bytedance/Projects/hummingbot/scripts/com.hummingbot.probability-gap-sampling.plist:17) triggers at `12:00`, `22:30`, `RunAtLoad`, and every `900s`.
- WU-015 evidence: early May 12 market can now be written as `observable | outside_overlap_window` with option-chain and forward fields, so skipping `00:00-12:00` now loses useful research data.
- Implemented staged schedule windows in [scripts/probability_gap_sampling_schedule.sh](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_sampling_schedule.sh:1): `early_observable` `00:00-12:00` at `60s`, `trading_core` `12:00-16:00` at `15s`, `post_option_observable` `16:00-22:00` at `60s`, and `near_exit_observable` `22:00-23:45` at `30s`; `23:45-00:00` skips.
- Added `PROB_GAP_SCHEDULE_DRY_RUN=1` and `PROB_GAP_SCHEDULE_NOW_LOCAL='YYYY-MM-DD HH:MM:SS'` support so window calculation can be validated without starting the sampler.
- Updated repo plist explicit calendar triggers to `00:00`, `12:00`, `16:00`, and `22:00`; `StartInterval=900`, `RunAtLoad`, run-days, pydeps repair, and already-running protection remain.
- Verification: `bash -n scripts/probability_gap_sampling_schedule.sh` passed.
- Verification: `plutil -lint scripts/com.hummingbot.probability-gap-sampling.plist` returned `OK`.
- Dry-run verification covered `00:30`, `11:59`, `12:00`, `15:59`, `16:00`, `21:59`, `22:00`, `23:44`, `23:45`, and `23:59`; outputs matched expected windows and skipped `23:45-00:00`.
- Live smoke without resetting DB: `PROB_GAP_PYDEPS_PATH=/tmp/hb_pydeps PYTHONPATH=/tmp/hb_pydeps:. /Users/bytedance/.pyenv/versions/3.12.4/bin/python -u scripts/probability_gap_intraday_sampling.py --iterations 1 --sleep-seconds 1 --db-path .yxg/data/probability_gap_wu016_smoke.sqlite` wrote May 12 as `tradable | iv_digital_live` with `option_chain_slice_count=12` and `forward_source=perp_mark`.
- Operator note: the installed plist under `~/Library/LaunchAgents/` is stale relative to the repo plist, and `launchctl print gui/$(id -u)/com.hummingbot.probability-gap-sampling` currently reports the service is not loaded. The operator must copy the repo plist and bootstrap it to activate the new explicit calendar triggers.

## Notes
- Recommendation: keep scanner trading window conservative for now; WU-016 is only about research sampling completeness.
