# WU-017 BTC 1d Post-Sampling Settlement-Aware Analysis

## Executive Conclusion

Decision: **NO-GO for paper trading**.

The 10-day corpus is useful for research, but it does not yet justify paper trading. The current `iv_digital_v1` fair-value model shows some settlement signal, but it does not beat a simple `always_up` baseline on this sample, and the execution replay still fails the core requirement: the default `maker_first` strategy has negative realized move.

The next step should not be real or paper order placement. It should be another research iteration focused on execution robustness and more settled market coverage.

## Frozen Corpus

Source DB: `.yxg/data/probability_gap_samples_wu013_clean.sqlite`

Frozen DB: `.yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite`

Checksum: `b63c2ef2fc82e64b35ac7e73db608a2f9b2b1045e027b6b214aa132256f10fac`

Rows: `4654`

Observed range: `2026-05-09T04:57:35.014045+00:00` to `2026-05-19T05:45:10.741520+00:00`

Generated reports:

- `.yxg/reports/probability_gap_wu017_model_validation.json`
- `.yxg/reports/probability_gap_wu017_model_evolution.json`
- `.yxg/reports/probability_gap_wu017_execution_replay.json`

## Data Quality

Conclusion-grade markets:

- `bitcoin-up-or-down-on-may-9-2026`: 812 rows, 679 tradable.
- `bitcoin-up-or-down-on-may-11-2026`: 1051 rows, 906 tradable.
- `bitcoin-up-or-down-on-may-14-2026`: 1537 rows, 567 tradable.
- `bitcoin-up-or-down-on-may-18-2026`: 440 rows, 208 tradable.

Partial/support-only markets:

- `bitcoin-up-or-down-on-may-10-2026`: 74 rows, 0 tradable.
- `bitcoin-up-or-down-on-may-15-2026`: 709 rows, but only 4 tradable.
- `bitcoin-up-or-down-on-may-19-2026`: 10 rows, 2 tradable.

Exclude or operational-only markets:

- `bitcoin-up-or-down-on-may-12-2026`: 5 rows, 0 tradable.
- `bitcoin-up-or-down-on-may-13-2026`: 14 rows, 0 tradable.
- `bitcoin-up-or-down-on-may-16-2026`: 1 rejected row, settlement unavailable.
- `bitcoin-up-or-down-on-may-20-2026`: 1 rejected row, settlement unavailable.

Interpretation: snapshot count is not the same as independent evidence. The most reliable conclusions must be market-level, not row-level.

## Settlement Coverage

Validation entries: `2366`

Settlement source coverage:

- Total markets: `11`
- Binance 1m rule labels: `9`
- Official labels: `0`
- Unavailable: `2`

Unavailable markets:

- `bitcoin-up-or-down-on-may-16-2026`: `missing_market_end_or_observed_at`
- `bitcoin-up-or-down-on-may-20-2026`: `missing_market_end_or_observed_at`

Resolved Binance-rule labels:

- May 9: `UP`, settlement close `80530.00`, reference `80179.45`
- May 10: `UP`, settlement close `81444.05`, reference `80530.00`
- May 11: `DOWN`, settlement close `81408.98`, reference `81444.05`
- May 12: `DOWN`, settlement close `80300.24`, reference `81408.98`
- May 13: `DOWN`, settlement close `79020.40`, reference `80300.24`
- May 14: `UP`, settlement close `81481.02`, reference `79020.40`
- May 15: `DOWN`, settlement close `79154.22`, reference `81496.74`
- May 18: `DOWN`, settlement close `76324.55`, reference `78075.02`
- May 19: `UP`, settlement close `76528.00`, reference `76324.55`

## Model Validation

Raw `iv_digital_v1`:

- Entries: `2366`
- Total settlement PnL: `+47.01`
- Avg settlement PnL: `+0.01987`
- Positive PnL rate: `55.75%`
- Side bias: `DOWN=1825`, `UP=541`

Naive baselines:

- `always_up`: total `+102.04`, avg `+0.04313`, positive rate `52.75%`
- `always_down`: total `-125.70`, avg `-0.05313`
- `buy_cheaper_side`: total `-631.51`, avg `-0.26691`

Market-level raw model stability:

- May 11: `+222.63`, 906 entries.
- May 9: `-40.07`, 679 entries.
- May 14: `-21.08`, 567 entries.
- May 18: `+27.35`, 208 entries.
- May 15: `+1.37`, only 4 entries.
- May 19: `+0.44`, only 2 entries.

Interpretation: the model has signal, but the current evidence is not robust. The positive aggregate depends heavily on May 11, while May 9 and May 14 are negative. More importantly, the model does not beat `always_up` on this sample, so it cannot yet be treated as an independent tradable edge.

## Model Evolution

Decision from model-evolution report:

- Best avg settlement PnL model: `iv_digital_bucket_shrinkage`
- Calibration status: `in_sample_only_rejected_by_leave_one_market_out`
- Recommended action: `collect_more_settled_markets_before_live_model_change`

Raw candidate comparison:

- `iv_digital_forward_rf_v2` ties the raw `iv_digital_v1` scorecard rather than improving it.
- `iv_digital_forward_basis_v2` and `iv_digital_horizon_smile_v2` have 100% coverage but weaker market stability, with min market total PnL down to `-247.13`.
- `iv_digital_smile_call_spread_v2` remains blocked with 0% coverage because option expiry is not close enough to the Polymarket market end.

Conclusion: keep `iv_digital_v1` as the tracked baseline for now. Do not promote a calibrated or ensemble model based on this corpus.

## Execution Replay

Replay snapshots: `4621`

Diagnostic coverage:

- 30s labels: `4612`
- 2m labels: `4604`
- 5m labels: `4583`

Default replay summaries:

- `maker_first`: 55 trades, total `-1.4288`, avg `-0.0260`, positive ratio `21.82%`.
- `taker_baseline`: 96 trades, total `+0.35`, avg `+0.00365`, positive ratio `14.58%`.
- `taker_hold`: 36 trades, total `+0.34`, avg `+0.00944`, positive ratio `55.56%`.

Paper-trading decision from replay:

- Decision: `no_go`
- Reason: `maker_total_realized_not_positive`

Parameter grid:

- Rows: `1080`
- Positive rows: `351`
- Best single cells show positive PnL, especially `buffer=0.08`, `gamma=low+medium`, `min_time_to_expiry=30`, `take_profit=0.01`, `stop_loss=0.05/0.08`.
- However, the stable-region view is weak: only `buffer=0.10` and `buffer=0.08` have positive average totals, and positive-row ratios are only `43.06%` and `37.04%`.

Interpretation: there are positive parameter islands, but not enough stability to call it a robust execution strategy. The default maker-first execution still loses money, so the model edge is not yet reliably convertible into realized EV.

## Answer To The Core Research Question

Does the model edge exist?

Partially. `iv_digital_v1` has positive settlement PnL and better Brier/log-loss than naive directional policies, but it underperforms `always_up` in total/average settlement PnL on this sample. That means the edge is not yet proven as a standalone trade selector.

Can the edge be executed?

Not with the current default maker-first rules. The replay's go/no-go gate rejects paper trading because default maker-first realized move is negative.

Is there a promising direction?

Yes, but it is execution-research, not live deployment. `taker_hold` and some high-buffer parameter cells show positive signs, but they require out-of-sample validation across more settled markets and stronger concentration checks.

## Recommendation

Do not start paper trading yet.

Recommended next work:

1. Continue collecting more settled BTC 1d markets under the WU-016 full-day sampling schedule until there are at least 15-20 conclusion-grade markets.
2. Open a dedicated execution-robustness WU to validate `taker_hold` and high-buffer maker variants with leave-one-market-out and market-level PnL gates.
3. Keep `iv_digital_v1` as the baseline model. Track horizon-smile as diagnostic only; do not promote it.
4. Require any candidate execution policy to pass market-level stability, not just snapshot-level or single-cell parameter-grid PnL.

## Commands Used

```bash
cp .yxg/data/probability_gap_samples_wu013_clean.sqlite \
  .yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite

shasum -a 256 \
  .yxg/data/probability_gap_samples_wu013_clean.sqlite \
  .yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite

PYTHONPATH=. python scripts/probability_gap_model_validation.py \
  --db-path .yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite \
  --fetch-binance-rule \
  --http-retry-count 3 \
  --http-backoff-seconds 1 \
  > .yxg/reports/probability_gap_wu017_model_validation.json

PYTHONPATH=. python scripts/probability_gap_model_evolution.py \
  --db-path .yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite \
  --fetch-binance-rule \
  --http-retry-count 3 \
  --http-backoff-seconds 1 \
  > .yxg/reports/probability_gap_wu017_model_evolution.json

PYTHONPATH=. python scripts/probability_gap_execution_replay.py \
  --db-path .yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite \
  --include-diagnostics \
  --include-trades \
  --include-parameter-grid \
  > .yxg/reports/probability_gap_wu017_execution_replay.json
```
