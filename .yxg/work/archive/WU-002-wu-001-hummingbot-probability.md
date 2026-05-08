---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-002
slug: wu-001-hummingbot-probability
title: 基于 WU-001，实现 Hummingbot 内的 Probability Gap 只读 scanner 最小版本。范围限定为 Polymarket 的 BTC Up or Down Daily 市场，采用重叠时段内的 Binance 信号有效性定义，完成基于日期的市场定位、Binance BTCUSDT 1 分钟 K 线参考价重建、信号有效窗口判断、观察对象与可交易机会分层、以及拒绝原因输出。优先采用监控型 controller 形态，不创建 executor action，不涉及下单、认证交易流或实盘执行。产出应足以支撑后续历史验证与 paper trading 任务。
status: done
priority: medium
owner_role: planner
created_at: "2026-04-16"
updated_at: "2026-04-16"
---

# Work Unit

## Objective
Implement the minimum viable read-only Probability Gap scanner inside Hummingbot for Polymarket BTC Up or Down Daily markets, using Binance spot BTCUSDT 1-minute candles as the authoritative source for the prior-day reference close and enforcing an overlap-window signal-validity discipline. The outcome should be a monitoring-oriented implementation that can discover candidate daily markets by date/slug, reconstruct the market's reference price from Binance raw market data, distinguish between markets that are merely observable and markets whose Binance signal source is still valid during a shared tradable window, and surface explicit classifications plus rejection reasons without placing orders or introducing authenticated trading flows.

## In Scope
- Implement public-data ingestion needed for the first scanner version.
- Implement market discovery and matching for Polymarket BTC Up or Down Daily markets only.
- Implement settlement-time, reference-definition, and market-shape alignment checks.
- Implement authoritative reference-price reconstruction from Binance BTCUSDT 1-minute spot klines instead of relying on Polymarket-derived helper fields such as `priceToBeat`.
- Implement overlap-window signal-validity checks so markets are only considered tradable while the Binance signal source remains live and decision-useful within a shared tradable window.
- Implement a symbol-level join between Binance Options `/eapi/v1/mark` and `/eapi/v1/exchangeInfo` so live signal classification can recover each option contract's `expiryDate` and avoid silently degrading the runtime path to `spot_only`.
- Implement strike-aware Binance option selection so the live signal uses the nearest relevant same-expiry strikes around the Polymarket reference price, rather than arbitrarily selecting any same-expiry BTC call delta.
- Implement explicit classification between `observable but not tradable` markets and `tradable` markets.
- Implement Binance signal normalization only for markets that pass the overlap-window validity screen; markets that fail the screen may still be surfaced for observation but must not enter the ranked opportunity pool.
- Use strike-neighbor interpolation or another bounded strike-aware method so the Binance-side signal is comparable to the Polymarket daily threshold event anchored at the reconstructed reference price.
- Implement first-version signal fields and ranking logic from WU-001.
- Implement a monitoring-only controller or equivalent read-only surface in Hummingbot.
- Expose ranked opportunities and rejected markets with explicit rejection reasons.
- Add bounded tests or verification artifacts for matching logic and signal calculation where practical.
- Record durable implementation discoveries back into the work artifact.

## Out Of Scope
- Authenticated Polymarket trading support.
- Real order placement, cancellation, or executor actions.
- Binance hedging or multi-leg execution.
- Generalized support for non-BTC or non-daily Up/Down event markets.
- Historical backtesting and replay beyond any minimal fixtures needed to verify logic.
- Paper trading or live trading.
- UI/dashboard work beyond whatever status output is needed for a monitoring controller.

## Expected Touch Points
- `.yxg/work/active/WU-002-wu-001-hummingbot-probability.md`
- [hummingbot/data_feed/market_data_provider.py](/Users/bytedance/Projects/hummingbot/hummingbot/data_feed/market_data_provider.py:27)
- [hummingbot/strategy_v2/controllers/controller_base.py](/Users/bytedance/Projects/hummingbot/hummingbot/strategy_v2/controllers/controller_base.py:58)
- [controllers/generic/examples/market_status_controller.py](/Users/bytedance/Projects/hummingbot/controllers/generic/examples/market_status_controller.py:1)
- [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1)
- [controllers/generic/probability_gap_scanner_utils.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner_utils.py:1)
- [test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py:1)

## Dependencies
- WU-001 archived planning contract and its evidence.
- Current Binance Options developer documentation.
- Current Polymarket public API / CLOB documentation.
- Access to public market data from both venues.

## Assumptions
- WU-001 remains the governing contract for market template, signal vocabulary, and first-phase boundaries.
- Delta is used as a probability proxy, not a guaranteed true payout probability.
- The first implementation should prefer a monitoring controller with no executor actions.
- Final-settlement mismatch is acceptable for this task as long as the Binance signal is used only inside a bounded overlap window and is not treated as a terminal payout-equivalence anchor.
- Polymarket helper metadata such as `eventMetadata.priceToBeat` is not authoritative for trading logic and may be used only as a debugging cross-check.
- A BTC Up or Down Daily market becomes eligible for overlap-window scoring only after the prior-day noon ET Binance close can be reconstructed from raw Binance data.
- The trading thesis uses pre-settlement convergence inside a bounded overlap window rather than demanding identical terminal settlement points across venues.
- A market can be observable without being tradable; if the Binance signal has already expired, has not yet entered the configured overlap window, or no longer offers a decision-useful lead over Polymarket, the correct behavior is to classify the market as non-tradable rather than force a score.
- Binance `/eapi/v1/mark` alone is not authoritative for contract expiry metadata; live option-aware signal-validity checks require joining mark data with `/eapi/v1/exchangeInfo` by `symbol`.
- The overlap window for a market ends at the earlier of Binance signal expiry and the configured Polymarket exit buffer, so no signal should be treated as authoritative beyond its own validity window.
- A same-expiry option delta is only meaningful for this task if its strike is relevant to the Polymarket event threshold; deep ITM or OTM calls with the right expiry but the wrong strike are not valid direct inputs.

## Risks
- Public data from one or both venues may be insufficient to robustly align markets without additional metadata parsing.
- Daily Up/Down markets are not natively fixed-strike products until the prior-day reference close is known, so the scanner must handle a pre-fix and post-fix lifecycle.
- Overlap-window trading can still be misleading if the Binance signal is given too much weight outside its own validity interval or if the overlap window is defined too loosely.
- A nearest-expiry-only option selector can severely overstate the Binance-side signal by picking deep ITM calls whose delta is near `1`, even when those strikes are unrelated to the Polymarket threshold event.
- The repository may require a new lightweight public-data connector abstraction even for read-only scanning.
- Signal quality may degrade sharply after time-mismatch penalties, signal normalization, or depth filtering is applied.
- If the live Binance mark-to-metadata join is omitted, the runtime path can misrepresent the Binance signal as `spot_only`, which would undercut the intended option-aware classification boundary for this task.
- Unrelated repository changes under `plugins/` remain present in the worktree.

## Plan
1. Reuse WU-001 constraints and the identified Polymarket daily series examples to define the exact first supported scanner market template and signal contract in code terms.
2. Implement public-data access and normalization for the minimum Polymarket daily market fields, Binance spot BTCUSDT 1-minute klines, and Binance signal inputs needed by the scanner.
3. Implement BTC Up or Down Daily market discovery by deterministic date/slug or equivalent series-aware filtering, plus overlap-window eligibility checks.
4. Reconstruct the authoritative prior-day noon ET Binance close from raw spot klines and reject markets whose reference price is not yet fixed.
5. Implement overlap-window signal-validity checks and explicit `observable` versus `tradable` classification so that markets are only promoted into the ranked opportunity pool while the Binance signal is still alive and inside the shared tradable interval.
6. Implement live Binance Options metadata recovery by joining `/eapi/v1/mark` with `/eapi/v1/exchangeInfo` on `symbol`, then use the recovered `expiryDate` to drive signal-validity checks and normalization instead of falling back to `spot_only` by default.
7. Replace the current nearest-expiry-only option selector with a strike-aware selector that chooses the relevant same-expiry strikes around the reconstructed reference price and derives a bounded event proxy from those strikes.
8. Implement time-aware Binance signal normalization only for the subset of markets that pass the overlap-window validity screen, then compute estimated-cost adjustment, convergence ranking, and rejection reasons.
9. Expose the scanner through a monitoring-only Hummingbot controller or equivalent status surface, making the `observable` versus `tradable` distinction visible.
10. Add targeted verification for pre-fix, observable-but-non-tradable, and tradable daily-market paths, including fixture-backed coverage that strike-aware selection prevents deep-ITM same-expiry deltas from inflating the Binance-side signal, then update the work artifact with discoveries and remaining gaps.
11. Before review, tighten the closeout surface so operator-visible status includes the selected option expiry, the lower/upper strikes used for interpolation, the interpolated option proxy, the overlap-window end, and the effective forced-exit timestamp for each tradable market.
12. Before review, run one final live regression over the current day market and confirm the reported classification, selected strikes, edge, and suggested exit time are internally consistent with the latest Binance/Polymarket data.

## Verification
- The scanner only emits ranked opportunities for markets that pass the declared overlap-window validity and alignment checks.
- Rejected markets surface machine-readable or operator-readable rejection reasons.
- Markets that are observable but not tradable are surfaced distinctly rather than silently mixed into either opportunities or generic rejections.
- Live Binance option-aware classification is driven by joined `/mark` plus `/exchangeInfo` metadata rather than by assuming `expiryDate` exists inside `/mark`.
- Markets can still qualify for observation or trading even when Binance expiry and Polymarket settlement differ, provided the signal is used only inside the bounded overlap window.
- The Binance-side signal for a daily market is derived from strike-relevant options near the reconstructed threshold, not from an arbitrary same-expiry call.
- The implementation exposes the first-version signal fields defined in WU-001.
- The controller or status surface produces ranked opportunities without creating executor actions.
- The status surface shows enough provenance to explain a live trade judgement, including which option expiry and strikes were used to derive the Binance-side signal and when that signal stops being actionable.
- Verification covers at least representative cases for daily-market discovery, pre-fix rejection, observable-but-non-tradable classification, and tradable-market ranking.

## Done When
- A Hummingbot read-only scanner exists for Polymarket BTC Up or Down Daily markets.
- It can ingest the required public inputs from Polymarket, Binance spot BTCUSDT klines, and the chosen Binance overlap-window signal source.
- It joins Binance live mark data with Binance option contract metadata so signal-validity decisions can use actual option expiries.
- It uses recovered option expiries to determine when a Binance signal is live, when the overlap window opens, and when the signal must no longer be treated as actionable.
- It uses strike-aware option selection near the reconstructed reference price so the Binance-side signal is interpretable as an event-relevant proxy rather than an arbitrary same-expiry call delta.
- It can match or reject markets using explicit alignment rules.
- It reconstructs the market reference price from Binance raw data instead of consuming Polymarket helper metadata as source truth.
- It distinguishes between merely observable markets and truly tradable markets using an explicit overlap-window signal-validity rule.
- It can compute and display ranked opportunities plus rejection reasons without treating Binance as a terminal payout-equivalence anchor outside its signal-validity window.
- It exposes enough per-market provenance in status output to support operator review of live opportunities before the task is sent to review.
- It does not place orders or require authenticated trading support.
- The resulting implementation is sufficient to open the next task for historical validation and replay without revisiting first-phase scope.

## Escalate If
- The required public APIs cannot provide enough data to match markets and compute the signal reliably.
- A bounded overlap window cannot be defined deterministically enough to support signal validity decisions for the target market class.
- Binance spot data cannot reliably provide the noon ET reference candle needed to fix the daily market strike.
- The chosen Binance signal source cannot be shown to retain decision-useful validity during a bounded overlap window.
- The scanner requires authenticated venue access just to perform first-phase read-only work.
- The implementation needs broader market coverage or a UI surface that materially changes the product contract.
- The work starts to imply execution logic, hedging logic, or paper/live trading support.

## Evidence Log
- WU-001 defines the first-phase Probability Gap scanner and its monitoring-only controller shape; this work refines the supported market template based on concrete Polymarket BTC daily-market examples discovered during implementation.
- WU-001 identified [controllers/generic/examples/market_status_controller.py](/Users/bytedance/Projects/hummingbot/controllers/generic/examples/market_status_controller.py:1) as a relevant pattern for a no-executor monitoring controller.
- WU-001 identified [hummingbot/data_feed/market_data_provider.py](/Users/bytedance/Projects/hummingbot/hummingbot/data_feed/market_data_provider.py:27) as a relevant public-data integration surface.
- Implementation discovery on 2026-04-16: the currently accessible Binance options public REST surface is `https://eapi.binance.com/eapi/v1/...`; the older `vapi` hostname redirected to the main Binance site in this environment.
- Implementation discovery on 2026-04-16: `GET /eapi/v1/exchangeInfo` provides option symbols with `underlying`, `side`, `strikePrice`, and `expiryDate`, and `GET /eapi/v1/mark` provides `delta` and IV fields needed for the first scanner version.
- Implementation discovery on 2026-04-16: Polymarket gamma market responses for `bitcoin-up-or-down-on-april-16-2026` and `bitcoin-up-or-down-on-april-17-2026` show that the relevant first supported market family is the `BTC Up or Down Daily` series, not a generic fixed-threshold BTC market.
- Implementation discovery on 2026-04-16: these daily markets resolve against Binance `BTC_USDT` 1-minute candle closes at noon ET (`16:00:00Z` for the sampled dates), with `Up/Down` outcomes and explicit comparison against the prior day's noon ET close.
- Implementation discovery on 2026-04-16: the sampled April 16 market included `eventMetadata.priceToBeat = 73792.01`, but the same reference close was independently reconstructed from Binance spot `BTCUSDT` 1-minute klines at `2026-04-15T16:00:00Z`; the task therefore treats Binance raw data as authoritative and `priceToBeat` only as a cross-check.
- Implementation discovery on 2026-04-16: the sampled April 17 market did not yet expose a fixed reference price from the prior day, confirming that daily Up/Down markets have a pre-fix lifecycle where options-based pricing must be rejected as `reference_price_not_fixed`.
- Implementation discovery on 2026-04-16: Polymarket gamma market responses already expose enough first-phase fields for the daily-market scanner, including `question`, `slug`, `endDate`, `resolutionSource`, `description`, `bestBid`, `bestAsk`, `outcomePrices`, `clobTokenIds`, and event metadata, so the first implementation did not require a new connector abstraction.
- Verification on 2026-04-16: `PYTHONPATH=/tmp/hb_pydeps pytest -q test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py` passed with 5 tests, adding a controller-level end-to-end path over `update_processed_data()`, `get_custom_info()`, `to_format_status()`, and `stop()`.
- Verification on 2026-04-16: local runtime dependencies were installed under `/tmp/hb_pydeps`, Hummingbot Cython extensions were built in place, and a live controller harness successfully imported `controllers.generic.probability_gap_scanner`, fetched real Binance/Polymarket public data, produced status output, and exited cleanly after a runtime fix to `ProbabilityGapScanner.stop()`.
- Live-scan observation on 2026-04-16: with the original generic threshold-market scanner and the first 500 active Polymarket markets returned by gamma, the live scanner produced `0` ranked opportunities and `500` rejections; this is now understood as a market-discovery mismatch against the actual target `BTC Up or Down Daily` series rather than just a lack of live opportunities.
- Implementation update on 2026-04-16: the scanner was reworked from generic threshold parsing to deterministic `BTC Up or Down Daily` discovery using the current and next `America/New_York` market dates to build the target Polymarket slugs.
- Implementation update on 2026-04-16: the scanner now reconstructs the authoritative reference price from Binance spot `BTCUSDT` 1-minute klines at the prior-day noon ET candle open timestamp and no longer consumes Polymarket `priceToBeat` as a source input.
- Implementation update on 2026-04-16: the first rescope attempt kept a strict same-day Binance Options expiry requirement, which caused the live April 16 market to be rejected as `no_binance_same_day_expiry`; this is now treated as evidence that payout-matched options mapping is too strict for the intended overlap-window convergence strategy.
- Verification on 2026-04-16: `PYTHONPATH=/tmp/hb_pydeps pytest -q test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py` now passes with 6 tests covering daily-market parsing, slug generation, missing same-day expiry rejection, interpolated strike mapping, probability-gap calculation, and controller behavior across both post-fix and pre-fix daily markets.
- Live-scan observation on 2026-04-16 after re-scoping: the scanner fetched exactly 2 target markets, `bitcoin-up-or-down-on-april-16-2026` and `bitcoin-up-or-down-on-april-17-2026`, and produced 2 explicit rejections: `no_binance_same_day_expiry` for the April 16 market and `reference_price_not_fixed` for the April 17 market.
- Strategy update on 2026-04-16: the accepted next direction is to treat trading-hours overlap as insufficient on its own. A market is only tradable if the Binance-side signal does not materially extend beyond Polymarket settlement; otherwise it may be surfaced for observation only.
- Strategy update on 2026-04-17: the contract was revised again to treat Binance as a staged signal source rather than a final-settlement proxy. Final expiry mismatch is acceptable for first-phase scanning as long as the strategy only uses Binance inside the bounded interval where the signal is live and both venues are still tradable.
- Strategy update on 2026-04-17: under the revised contract, the effective overlap window for a market ends at the earlier of Binance signal expiry and the configured Polymarket exit buffer, and classification should be based on signal validity within that window rather than on strict settlement-horizon equivalence.
- Implementation update on 2026-04-17: `build_binance_overlap_signal()` was revised to treat a live option expiry as sufficient for `tradable` classification inside the overlap window, using `spot_option_blend` with an overlap penalty derived from the difference between time-to-settlement and time-to-signal-expiry instead of rejecting the market solely because final settlement points differ.
- Verification on 2026-04-17: `PYTHONPATH=/tmp/hb_pydeps pytest -q test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py` still passes with 7 tests after the contract revision, and the controller test now expects an in-window market with a live option signal to enter the ranked opportunity pool as `tradable` with `classification_reason = overlap_window_live`.
- Live-scan observation on 2026-04-17 at `05:00:43Z` (`2026-04-17 01:00:43-04:00` America/New_York): the scanner fetched `bitcoin-up-or-down-on-april-17-2026` and `bitcoin-up-or-down-on-april-18-2026`, promoted the April 17 market into `opportunities` with `signal_kind = spot_option_blend`, `classification_reason = overlap_window_live`, `minutes_to_signal_expiry = 179.27`, `minutes_to_settlement = 659.27`, and `best_side = UP`, while the April 18 market remained rejected as `outside_overlap_window`. This confirms the implementation now follows the overlap-window signal-validity contract rather than the earlier strict settlement-horizon rule.
- Review finding on 2026-04-17: the current option selector still chooses a Binance signal by nearest expiry only, without conditioning on strike. Live inspection of the `2026-04-17T08:00:00Z` BTC call chain showed many deep ITM calls with `delta = 1.0` at strikes such as `56000`, `58000`, and `60000`; because the selector ignores strike, it can overstate the Binance-side event proxy and make Polymarket look artificially cheap.
- Review finding on 2026-04-17: for the April 17 daily market with reconstructed reference price near `74754.2` and live spot near `74646`, the relevant same-expiry strikes are around `74500` and `75000`, whose live deltas were approximately `0.656` and `0.176`. This demonstrates that strike-aware interpolation is required before treating the Binance-side value as comparable to the Polymarket `Up/Down` threshold market.
- Implementation update on 2026-04-17: `_select_latest_option_signal()` now uses the nearest same-expiry strikes around the reconstructed reference price and linearly interpolates their deltas instead of selecting an arbitrary same-expiry call by expiry alone.
- Verification on 2026-04-17: `PYTHONPATH=/tmp/hb_pydeps pytest -q test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py` still passes with 7 tests after the strike-aware selector was introduced, including a direct interpolation test showing that a deep ITM `56000-C` no longer overrides the `74500/75000` neighborhood for an event anchored near `74754.2`.
- Live-scan observation on 2026-04-17 at `06:03:58Z` (`2026-04-17 02:03:58-04:00` America/New_York): after strike-aware interpolation, the April 17 market remained `tradable` with `classification_reason = overlap_window_live`, but the Binance-side blended signal dropped to approximately `0.4319`, flipping `best_side` from `UP` to `DOWN`. With `Up ask = 0.50`, `Down ask = 0.51`, and `estimated_cost = 0.010`, the resulting net edges were approximately `net_edge_up = -0.0781` and `net_edge_down = +0.0481`. This confirms the previous strong `UP` conclusion was an artifact of strike-insensitive option selection.
- Closeout verification on 2026-04-20 at `12:29:49Z` (`2026-04-20 08:29:49-04:00` America/New_York): the final live regression for WU-002 fetched `bitcoin-up-or-down-on-april-20-2026` and `bitcoin-up-or-down-on-april-21-2026`, produced 1 tradable opportunity and 1 rejection, and showed the new provenance fields end-to-end in the live opportunity record. For the April 20 market, the scanner reported `selected_option_expiry = 2026-04-21T08:00:00Z`, `lower_strike = 75500`, `lower_delta = 0.48089706`, `upper_strike = 76000`, `upper_delta = 0.35248743`, `interpolated_option_delta = 0.4116714284670`, `binance_signal_value = 0.4076576447170`, `best_side = UP`, `best_net_edge = 0.0376576447170`, and `forced_exit_time = 2026-04-20T15:45:00Z`, while the April 21 market remained rejected as `outside_overlap_window`. This confirms the status surface now exposes enough provenance to explain a live judgement before review.
- Implementation update on 2026-04-16: the scanner was further refactored away from same-day-expiry mapping toward overlap-window scoring, but subsequent review showed that overlap in trading hours alone is too weak a criterion for tradeability when Binance risk extends materially past Polymarket settlement.
- Implementation update on 2026-04-16: the current overlap-window implementation can still surface a same-day Polymarket market as an opportunity using a `spot_only` Binance signal. Under the stricter settlement-horizon definition, this behavior should be treated as too permissive and revised.
- Verification on 2026-04-16: `PYTHONPATH=/tmp/hb_pydeps pytest -q test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py` passes with 6 tests under the stricter settlement-horizon model, covering overlap-window rejection, observable-but-non-tradable Binance signal construction, convergence-score calculation, and controller behavior across observable and out-of-window daily markets.
- Implementation update on 2026-04-16: the controller now separates `opportunities`, `observations`, and `rejected_markets`, and only promotes markets into the ranked opportunity pool when the Binance signal is explicitly marked `tradable`; horizon-mismatched markets remain visible as `observable` with an explicit `classification_reason`.
- Live-scan observation on 2026-04-16 after settlement-horizon tightening: the scanner fetched exactly 2 target markets, classified `bitcoin-up-or-down-on-april-16-2026` as `observable` with `classification_reason = settlement_horizon_mismatch`, and rejected `bitcoin-up-or-down-on-april-17-2026` as `outside_overlap_window`. Under the current contract, this is the desired behavior because mere trading-hours overlap is insufficient for tradeability.
- Implementation discovery on 2026-04-16: live Binance `/eapi/v1/mark` responses expose `symbol`, `delta`, and IV fields but do not expose `expiryDate`; this required joining `/mark` with `/exchangeInfo` symbol metadata in the controller rather than assuming expiry information exists inside the mark payload itself.
- Work-contract update on 2026-04-16: the missing live Binance mark-to-metadata join was explicitly pulled into WU-002, because option-aware settlement-horizon classification is part of this task's first-phase contract rather than a later enhancement.
- Implementation update on 2026-04-16: the controller now fetches `/eapi/v1/mark` and `/eapi/v1/exchangeInfo` together, joins them by option `symbol`, filters for `BTCUSDT` call contracts, and selects the nearest-expiry delta using recovered `expiryDate` metadata for live settlement-horizon evaluation.
- Verification on 2026-04-16: `PYTHONPATH=/tmp/hb_pydeps pytest -q test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py` now passes with 7 tests, including a direct join-path test showing that `_select_latest_option_signal()` can recover the correct expiry from `/exchangeInfo` even when `/mark` omits it.
- Live-scan observation on 2026-04-16 after implementing the mark-to-metadata join: the scanner still fetched exactly 2 target markets, but `bitcoin-up-or-down-on-april-16-2026` is now classified as `observable` with `binance_signal_kind = spot_option_blend` and `classification_reason = settlement_horizon_mismatch`, while `bitcoin-up-or-down-on-april-17-2026` remains rejected as `outside_overlap_window`. This confirms that the live path no longer silently degrades to `spot_only`; it now performs option-aware classification and still keeps the market out of the tradable set under the strict horizon rule.
- Live-scan observation on 2026-04-16 at `18:20:48Z` (`2026-04-16 14:20:48-04:00` America/New_York): the scanner still fetched exactly 2 target markets, `bitcoin-up-or-down-on-april-16-2026` and `bitcoin-up-or-down-on-april-17-2026`, but now returned 2 explicit rejections and 0 observations because the April 16 market had already passed its `2026-04-16T16:00:00Z` settlement point (`market_already_settled`) while the April 17 market remained outside the configured overlap window (`outside_overlap_window`). This confirms the latest runtime behavior is time-sensitive and that prior observable results for the April 16 market applied only before noon ET settlement.

## Notes
- This task is the first implementation follow-on from WU-001 and should stay strictly narrower than the later backtesting, paper-trading, and live-trading phases.
- If this work proves that read-only market matching is not viable, the correct outcome is a bounded failure with explicit reasons, not silent scope expansion.
- The first implementation was originally framed as an exact-strike threshold-market scanner; this task is now explicitly re-scoped to the `BTC Up or Down Daily` market family and then revised toward overlap-window signal validity, where Binance acts as a bounded live signal source rather than a strict final-settlement proxy.
- As of 2026-04-20, the remaining work in WU-002 is closeout-oriented rather than architectural: improve operator-visible provenance in the status surface, perform one last live regression with that richer output, and then send the task to review if the results remain consistent.
