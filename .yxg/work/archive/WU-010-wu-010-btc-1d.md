---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-010
slug: wu-010-btc-1d
title: WU-010: BTC 1d settlement-aware model evolution. 基于 WU-006 的 settlement labels 和 clean corpus，按严格顺序推进离线研究：Phase 1 先建立 settlement-aware objective 统一评分框架，复现 WU-006 settlement 结论并输出 settlement PnL、Brier/log loss、edge bucket -> final PnL、closeout vs settlement、side bias、leave-one-market-out；Phase 2 再对 iv_digital_v1 做 probability calibration，优先 bucket/shrinkage/simple logistic，验证 gamma/tau/moneyness/spread 分桶下是否改善 calibration 和 settlement PnL；Phase 3 最后做 cross-model ensemble，对比 iv_digital_v1、realized-vol digital、spot+RV Brownian、old delta_spot_blend、Polymarket mid/microprice，并测试等权/简单权重/网格权重。范围限定为离线分析和报告，不改 live scanner 交易逻辑，不接实盘，不做 paper trading。成功标准：统一评分框架稳定复现 WU-006；校准后优于 raw iv_digital_v1 且不是单日过拟合；ensemble 比 raw iv_digital_v1 更稳定，且通过 leave-one-market-out 和 bucket 稳定性检查。
status: done
priority: medium
owner_role: planner
created_at: "2026-05-08"
updated_at: "2026-05-08"
---

# Work Unit

## Objective

Build an offline, settlement-aware model-evolution research layer for the BTC 1d probability-gap strategy. The work must start from WU-006 settlement labels and clean sampled snapshots, then determine whether probability calibration and cross-model ensemble improve on raw `iv_digital_v1` in a way that survives settlement PnL, bucket stability, and leave-one-market-out checks.

The required sequence is strict:

1. Phase 1: establish the settlement-aware objective and reproduce WU-006 conclusions.
2. Phase 2: calibrate `iv_digital_v1` only after the objective framework is stable.
3. Phase 3: compare and ensemble independent models only after calibration has a reproducible baseline.

## In Scope
- Add or extend offline analysis modules/scripts for model comparison, calibration, and ensemble research.
- Reuse WU-006 settlement labels, `.yxg/data/probability_gap_settlements.json`, and clean SQLite snapshots as input data.
- Produce a repeatable report with settlement PnL, Brier score, log loss, fair/edge buckets, closeout-vs-settlement, side bias, and leave-one-market-out metrics.
- Add naive baselines so model improvements are not confused with simple sample bias:
  - always UP
  - always DOWN
  - buy cheaper side
- Implement candidate probability models for comparison:
  - raw `iv_digital_v1`
  - calibrated `iv_digital_v1`
  - realized-vol digital
  - spot plus realized-vol Brownian digital
  - old `delta_spot_blend`
  - Polymarket mid or microprice market baseline
- Implement simple calibration candidates such as bucket calibration, shrinkage, and simple logistic-style scoring if dependency-free or already available.
- Implement simple ensemble candidates such as equal-weight, hand-weighted, and small grid-weighted combinations.
- Segment results by gamma risk, tau/time-to-expiry, moneyness, spread, side, confidence, and edge bucket where sample size permits.
- Write findings and go/no-go conclusions into this work artifact.

## Out Of Scope
- Changing live `iv_digital_v1` scanner fair-value math.
- Changing live sampling cadence, LaunchAgent schedules, or websocket/rest transport.
- Real Polymarket trading, order signing, balances, or order placement.
- Paper trading with persistent virtual balances.
- Maker/taker quote lifecycle simulation beyond reusing existing replay metrics for comparison.
- Claiming strategy profitability from fewer than 5-10 complete BTC 1d settled markets.
- Introducing heavy ML dependencies or opaque optimization that cannot be inspected from the report.
- Treating Polymarket mid as a directly tradable alpha model without side-bias and leave-one-market-out checks.
- Letting Polymarket mid enter an accepted ensemble candidate merely because it improves in-sample PnL.

## Expected Touch Points
- [controllers/generic/probability_gap_model_validation.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_model_validation.py:1)
- A new or extended offline model-comparison/calibration helper under `controllers/generic/`.
- [scripts/probability_gap_model_validation.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_model_validation.py:1) or a new CLI script for model evolution reporting.
- [test/controllers/test_probability_gap_model_validation.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_model_validation.py:1) or a new focused test file for model comparison/calibration.
- `.yxg/data/probability_gap_samples_wu006_clean.sqlite` as the current clean sample corpus.
- `.yxg/data/probability_gap_settlements.json` as durable settlement cache.
- `.yxg/work/active/WU-010-wu-010-btc-1d.md`

## Dependencies
- WU-006 settlement-aware validation and Binance rule settlement labels.
- Existing clean sampler output in `.yxg/data/probability_gap_samples_wu006_clean.sqlite`.
- Existing execution replay metrics from WU-005/WU-006 for closeout-vs-settlement comparison.
- Additional complete BTC 1d settled markets are required for strong conclusions, but the implementation must work with the current smaller corpus.

## Assumptions
- Binance rule 1m close remains the accepted reliable settlement source for already closed BTC 1d markets when official Gamma/Polymarket resolution is absent.
- Current sample size is enough to validate the analysis pipeline and detect obvious model regressions, but not enough to claim profitability.
- Calibration must be judged out-of-sample where possible; if leave-one-market-out is too small, the report must say so explicitly.
- Polymarket mid/microprice is a baseline and confidence input, not automatically ground truth.
- Polymarket mid can be used as a market baseline or anchor, but should not be treated as an accepted model improvement unless it beats naive baselines and passes side-bias plus leave-one-market-out checks.

## Risks
- Current corpus has too few settled markets, so calibration and ensemble may overfit.
- Snapshot-level counts can exaggerate evidence if repeated ticks from the same market are treated as independent.
- Settlement PnL and short-horizon closeout return may point in different directions; the report must keep those scorecards separate.
- Old `delta_spot_blend` can appear attractive in a DOWN market due to side bias rather than true calibration.
- Ensemble weights can look better through hindsight optimization; adjacent weight stability and leave-one-market-out checks are required.
- A pure or high-weight Polymarket-mid ensemble can simply learn market/outcome imbalance, especially when current settled-market count is small.

## Plan
1. Build Phase 1 report that reproduces WU-006 settlement-aware metrics for raw `iv_digital_v1`.
2. Add common model-output abstraction so each candidate model emits `fair_up`, `fair_down`, side-specific edge, residual, and confidence fields over the same snapshots.
3. Add settlement-aware scorecard: Brier, log loss, settlement PnL, edge bucket -> final PnL, residual bucket -> final PnL, closeout-vs-settlement, side bias, and leave-one-market-out.
4. Implement and test naive baselines: always UP, always DOWN, and buy cheaper side.
5. Implement and test the old `delta_spot_blend`, realized-vol digital, spot+RV Brownian, and Polymarket mid/microprice market baselines.
6. Implement Phase 2 calibration candidates for `iv_digital_v1`, starting with simple bucket/shrinkage methods before any regression-style method.
7. Evaluate calibration candidates against raw `iv_digital_v1`, with explicit overfit checks by market and bucket.
8. Implement Phase 3 ensemble candidates after calibration is measurable, using small transparent weight grids rather than opaque optimization.
9. Evaluate ensemble candidates against raw and calibrated `iv_digital_v1`; any Polymarket-mid-heavy ensemble must be flagged as non-actionable unless it beats naive baselines and passes side-bias plus leave-one-market-out checks.
10. Write a final decision section: keep raw model, adopt calibration, adopt ensemble, or collect more data before changing model.
11. Record evidence, commands, and current limitations in this artifact.

## Verification
- Unit tests cover each candidate model's probability output shape and complement consistency.
- Unit tests cover calibration bucket/shrinkage behavior.
- Unit tests cover ensemble weighting and probability bounds.
- Unit tests or report checks cover naive baselines and prevent interpreting UP-only or DOWN-only results as model alpha.
- Unit tests cover settlement scorecard calculations, including Brier/log loss and side-specific settlement PnL.
- A repeatable local command runs against `.yxg/data/probability_gap_samples_wu006_clean.sqlite` and `.yxg/data/probability_gap_settlements.json`.
- The report demonstrates that Phase 1 reproduces WU-006 baseline metrics within expected tolerance.
- The report includes leave-one-market-out or explicitly explains why the current corpus is too small for a meaningful check.
- The report separates snapshot-level metrics from market-level interpretation.

## Done When
- A repeatable offline report compares raw `iv_digital_v1`, calibrated variants, independent baselines, and ensemble variants under settlement-aware metrics.
- The report states whether calibration improves raw `iv_digital_v1` without obvious overfit.
- The report states whether any ensemble improves raw/calibrated `iv_digital_v1` with better stability rather than a single-market artifact.
- The report compares candidate models against naive baselines and flags Polymarket-mid-heavy results as market baseline or sample-bias evidence unless they pass side-bias and leave-one-market-out checks.
- The work artifact records a clear recommendation for the next step: keep collecting data, change model in a future WU, or proceed to strategy narrowing.
- Targeted tests for the new model-evolution logic pass.

## Escalate If
- The current clean corpus has too few complete markets to distinguish calibration improvement from overfit.
- Settlement labels are missing, stale, or conflict with official outcomes.
- Calibration improves Brier/log loss but worsens settlement PnL or side bias materially.
- Ensemble improvement depends on one market, one side, or a single brittle weight combination.
- A candidate only beats raw `iv_digital_v1` by collapsing into always-UP, always-DOWN, or Polymarket-mid-heavy behavior.
- Implementing a candidate model requires nontrivial new dependencies or live data sources not already present.

## Evidence Log
- WU-006 produced a cache-backed settlement validation layer with Binance rule 1m close labels and retry/cache hardening.
- WU-006 clean corpus currently has limited settled-market coverage, enough for pipeline validation but not enough to claim strategy profitability.
- Current `iv_digital_v1` beat reconstructed old `delta_spot_blend` on same settled tradable snapshots: raw `iv_digital_v1` had smaller but more realistic edge, while old delta/spot blend produced larger apparent edge and worse settlement PnL due to side bias.
- The strict research order is intentional: settlement objective first, calibration second, ensemble last.
- Implemented offline model evolution module `controllers/generic/probability_gap_model_evolution.py` and CLI `scripts/probability_gap_model_evolution.py`.
- Phase 1 scorecard reproduces WU-006 baseline on `.yxg/data/probability_gap_samples_wu006_clean.sqlite`: 5 markets total, 3 `binance_rule_1m_close`, 2 unavailable, 1597 settlement-labeled entries, raw baseline average settlement PnL 0.024809, total settlement PnL 39.62, Brier 0.196161.
- Phase 2 adds `iv_digital_bucket_shrinkage`. In-sample calibration looks strong, but leave-one-market-out rejects it: May 6 and May 7 held-out markets are negative, so this is not acceptable evidence for a live model change.
- Phase 3 adds independent model comparisons and ensemble variants: raw `iv_digital_v1`, calibrated `iv_digital_bucket_shrinkage`, realized-vol digital, spot+RV Brownian, old `delta_spot_blend`, Polymarket mid, fixed-weight ensembles, and a 15-candidate 0/25/50/75/100 weight grid.
- Current real-corpus model comparison: old `delta_spot_blend` remains worse than raw `iv_digital_v1`; realized-vol and spot+RV Brownian are negative; fixed-weight ensembles do not clearly improve raw `iv_digital_v1`; the grid's top in-sample PnL is pure Polymarket mid with UP-only side bias, so it is likely sample/outcome bias rather than a robust ensemble.
- Current decision: collect more settled markets before changing the live model. No calibration or ensemble candidate is accepted for live scanner use in this WU.
- User review clarification added: Polymarket mid is a market baseline/anchor, not an alpha model by default. WU-010 must add naive baselines and prevent Polymarket-mid-heavy in-sample wins from being interpreted as actionable model upgrades without side-bias and leave-one-market-out support.
- Implemented naive baselines and sample-bias flags in the model evolution report: `naive_always_up`, `naive_always_down`, and `naive_buy_cheaper_side`.
- Updated real-corpus report after naive baseline checks: `naive_always_up` has total settlement PnL 126.82 and UP-only side bias; pure `polymarket_mid` has the same effective outcome and is now flagged as `one_sided_selection`, `polymarket_mid_heavy`, and `non_actionable_sample_bias_risk`.
- `naive_buy_cheaper_side` is near flat in the current corpus: total settlement PnL 4.49 with UP-heavy side bias. This supports treating the pure Polymarket-mid win as sample/outcome bias rather than model alpha.
- The report now records a market-baseline policy: Polymarket mid is non-actionable unless it beats naive baselines without one-sided behavior or leave-one-market-out failure.
- Verification passed: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_model_evolution.py test/controllers/test_probability_gap_model_validation.py test/controllers/test_probability_gap_execution_replay.py test/controllers/test_probability_gap_sampling.py` -> 30 passed, 1 existing pytest config warning.
- Compile verification passed: `python -m py_compile controllers/generic/probability_gap_model_evolution.py scripts/probability_gap_model_evolution.py`.

## Notes
- This is an offline research task. It should not alter live trading behavior until a later work unit explicitly accepts a model change.
