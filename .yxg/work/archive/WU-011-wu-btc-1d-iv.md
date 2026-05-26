---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-011
slug: wu-btc-1d-iv
title: WU: BTC 1d iv_digital_v2 raw model candidates. 基于 WU-010 结论，不继续调 calibration/ensemble，而是离线研究 raw iv_digital_v1 本身的定价来源改进。目标是实现并比较几个小而透明的 raw model variants：1) implied variance strike interpolation / expiry variance-time interpolation; 2) forward/basis adjustment 替代纯 spot; 3) smile-aware digital probability / call-spread slope approximation if stored option chain data is sufficient; 4) fair interval / model_uncertainty output for conservative edge gating. 范围限定为离线 candidate 实验和报告，不替换 live scanner，不接实盘，不做 paper trading。验证必须复用 WU-010 settlement-aware scorecard：Brier/log loss、settlement PnL、side bias、naive baseline comparison、leave-one-market-out、bucket stability。成功标准：至少一个 raw model variant 在同一批 snapshots 上比 raw iv_digital_v1 更稳，且不是单边偏置或单市场过拟合；否则结论是继续保留 raw iv_digital_v1 并继续采样。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-09"
updated_at: "2026-05-09"
---

# Work Unit

## Objective

Run a small offline research pass for `iv_digital_v2` raw probability candidates. The goal is to improve the probability source itself, not to tune calibration or ensemble weights. The work should determine which raw-model variants are feasible from currently stored snapshots, implement the feasible ones as offline candidates, and compare them against raw `iv_digital_v1` using the WU-010 settlement-aware scorecard.

The expected output is a repeatable report and a clear decision:

- keep raw `iv_digital_v1`
- promote one raw candidate into a future live-scanner change WU
- or collect richer option-chain data before raw model evolution can proceed

## In Scope
- Add offline raw model candidate logic under the model-evolution research path.
- Add a data-availability check for fields needed by each candidate:
  - implied variance strike interpolation
  - expiry variance-time interpolation
  - forward/basis adjustment
  - smile-aware digital / call-spread slope approximation
  - fair interval / uncertainty output
- Implement only candidates supported by existing snapshots or clearly report why a candidate is blocked by missing data.
- Compare each candidate against raw `iv_digital_v1`, WU-010 naive baselines, and WU-010 market baselines.
- Use the same settlement-aware scorecard as WU-010: Brier/log loss, settlement PnL, side bias, naive baseline comparison, leave-one-market-out, and bucket stability.
- Write findings and candidate feasibility into this work artifact.

## Out Of Scope
- Replacing live scanner fair-value math.
- Reintroducing calibration or ensemble optimization as the main task.
- Real trading, paper trading, order signing, balances, or order lifecycle simulation.
- Changing sampler cadence, LaunchAgent setup, or websocket/rest transport.
- Adding heavy ML dependencies.
- Claiming model superiority from fewer than 5-10 complete settled BTC 1d markets.

## Expected Touch Points
- [controllers/generic/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_model_evolution.py:1)
- [scripts/probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_model_evolution.py:1)
- [test/controllers/test_probability_gap_model_evolution.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_model_evolution.py:1)
- Possibly a small helper module under `controllers/generic/` if raw candidate logic becomes too large.
- `.yxg/data/probability_gap_samples_wu006_clean.sqlite` as current clean corpus.
- `.yxg/data/probability_gap_settlements.json` as settlement cache.
- `.yxg/work/active/WU-011-wu-btc-1d-iv.md`

## Dependencies
- WU-010 settlement-aware model-evolution framework and its naive-baseline/sample-bias checks.
- WU-006 settlement labels and Binance rule settlement cache.
- Existing snapshot fields from the clean corpus, especially `current_spot_price`, `reference_price`, `tau_years`, `option_iv`, `lower_iv`, `upper_iv`, `lower_strike`, `upper_strike`, `selected_option_expiry`, and any stored option-chain provenance in payload.

## Assumptions
- Current snapshots may not contain enough option-chain detail for true smile-aware call-spread digital probability.
- If forward/basis data is absent, the first candidate may only support a documented zero-basis or spot-forward fallback.
- `fair interval` can be evaluated as an offline uncertainty/gating metric even if it is not yet wired into live scanner decisions.
- Any candidate that merely changes side bias without improving out-of-sample metrics should be rejected.

## Risks
- Stored snapshots may not have enough data to implement the most theoretically attractive candidates.
- A small corpus can make a raw candidate look better by chance.
- Forward/basis adjustment may be negligible on BTC 1d and not worth live complexity.
- Smile-aware digital probability may require storing richer option chain snapshots in a later sampler WU before it can be implemented correctly.
- Fair interval/gating may improve risk interpretation without changing raw fair probability, so it should not be mislabeled as a better pricing model.

## Plan
1. Add a candidate data-availability report over the current clean corpus.
2. Define raw candidate specs and classify each as `implemented`, `fallback`, or `blocked_by_missing_data`.
3. Implement feasible variants:
   - variance-interpolated IV digital where stored lower/upper IV or strike provenance supports it
   - forward-adjusted IV digital with explicit fallback assumptions
   - fair interval / uncertainty bounds around raw `iv_digital_v1`
4. Add a blocked/feasibility result for smile-aware call-spread digital if stored option prices are insufficient.
5. Reuse WU-010 scoring to compare raw candidates, raw `iv_digital_v1`, naive baselines, and Polymarket mid baseline.
6. Add tests for candidate feasibility, probability bounds, complement consistency, and blocked-candidate reporting.
7. Run the report on `.yxg/data/probability_gap_samples_wu006_clean.sqlite`.
8. Record whether any candidate deserves a future live-scanner implementation WU.

## Verification
- Unit tests cover each raw candidate's output bounds and missing-data behavior.
- Unit tests cover candidate feasibility classification.
- Unit tests cover fair interval bounds and conservative edge interpretation.
- A repeatable local command runs the WU-011 report against the clean corpus and settlement cache.
- The report compares every implemented candidate against raw `iv_digital_v1` and naive baselines.
- The report flags candidates that are blocked by missing data rather than silently omitting them.

## Done When
- A repeatable offline report lists raw candidate feasibility and scorecards.
- The report states whether any `iv_digital_v2` candidate beats raw `iv_digital_v1` without one-sided or single-market overfit.
- The report identifies any additional data that must be collected before smile-aware or forward-aware raw models can be implemented properly.
- Targeted tests pass.

## Escalate If
- Current snapshots lack the option-chain fields needed for variance interpolation or smile-aware digital approximation.
- A candidate appears better only because it collapses into always-UP/always-DOWN behavior.
- The best raw candidate improves Brier/log loss but worsens settlement PnL or leave-one-market-out.
- Implementing a candidate requires live API changes or sampler changes that exceed this small offline WU.

## Evidence Log
- WU-010 concluded that calibration and ensemble candidates are not ready for live adoption; raw model evolution should focus on improving the probability source itself.
- WU-010 added naive baselines and Polymarket-mid-heavy sample-bias checks; WU-011 must preserve those checks when comparing raw candidates.
- Implemented WU-011 raw candidate reporting inside `controllers/generic/probability_gap_model_evolution.py`; the existing CLI `scripts/probability_gap_model_evolution.py` now emits an `iv_digital_v2_raw_candidates` section.
- Implemented candidate feasibility checks:
  - `iv_digital_variance_strike_v2`: implemented, supported on 2477/2477 tradable snapshots by stored lower/upper strike and IV provenance.
  - `iv_digital_forward_rf_v2`: fallback, supported on 2477/2477 snapshots but only uses risk-free-rate forward fallback because true futures basis is not stored.
  - `iv_digital_smile_call_spread_v2`: blocked by missing data because current snapshots do not store adjacent option mark/call prices.
  - `fair_interval_uncertainty`: implemented, supported on 2477/2477 snapshots using lower/upper IV provenance.
- Real-corpus command: `PYTHONPATH=. python scripts/probability_gap_model_evolution.py --db-path .yxg/data/probability_gap_samples_wu006_clean.sqlite --fetch-binance-rule --http-retry-count 1 --http-backoff-seconds 0`.
- Real-corpus settlement coverage at execution time: 5 markets total, 4 `binance_rule_1m_close`, 1 unavailable, 2477 settlement-labeled tradable entries.
- Raw candidate scorecard: raw `iv_digital_v1` total settlement PnL 1.18, Brier 0.261590, side bias DOWN 1614 / UP 863; `iv_digital_forward_rf_v2` is effectively identical to raw; `iv_digital_variance_strike_v2` total settlement PnL 3.13, Brier 0.261462, side bias DOWN 1593 / UP 884.
- Market stability remains weak: both raw and variance-strike v2 are positive in only 1 of 3 labeled markets and negative in 2 of 3. Variance-strike v2 improves total PnL by only 1.95 and worsens the worst-market loss slightly, so it is not enough for a live model change.
- Fair interval result: 2477 intervals, average width 0.03195, 31.8% have width >= 5c, and all intervals contain raw fair. This is useful as an uncertainty/gating signal, not a replacement probability model yet.
- WU-011 decision: no raw v2 candidate should replace `iv_digital_v1` now. `iv_digital_variance_strike_v2` is worth tracking with more settled markets; smile-aware digital requires richer option price-chain sampling.
- Verification passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_model_evolution.py test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 31 passed, 1 existing pytest config warning.
- Compile verification passed: `python -m py_compile controllers/generic/probability_gap_model_evolution.py scripts/probability_gap_model_evolution.py`.

## Notes
- This is a small offline research WU. If data availability is insufficient, the correct outcome is to document the gap and open a later sampler/data WU, not to invent unsupported pricing logic.
