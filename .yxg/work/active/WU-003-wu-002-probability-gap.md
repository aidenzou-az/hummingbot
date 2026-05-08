---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-003
slug: wu-002-probability-gap
title: 基于 WU-002 的 Probability Gap scanner，建立机会采样与事后验证框架：持续记录 Polymarket BTC Up/Down Daily 市场的 live signal、盘口、selected option provenance 与 forced-exit 前后的价格变化，用于验证 edge 的可实现性并产出后续 paper trading 门槛。要求明确采样主键、快照字段、分层采样频率、SQLite 落盘、固定入场/退出复盘规则，以及 websocket 边界：Polymarket 优先流式，Binance 采用信号正确性优先的混合模式，不要求两边在本阶段全部 websocket 化。
status: active
priority: medium
owner_role: planner
created_at: "2026-04-21"
updated_at: "2026-04-22"
---

# Work Unit

## Objective

Build the first durable opportunity-sampling and post-hoc validation layer on top of the WU-002 Probability Gap scanner so the project can answer whether scanner-reported edges are actually realizable before the forced-exit boundary. The outcome should continuously record BTC Up/Down Daily market snapshots, preserve the Binance-side provenance used to compute each signal, store those snapshots in a compact local database, and provide a deterministic replay / attribution workflow that measures whether opportunities converged, decayed, or failed before their action window expired. This task should also lock in the data-ingestion boundary for the next phase: Polymarket may move toward a stream-first market-data path, while Binance should remain signal-correctness-first and may stay hybrid rather than fully websocket-native in this phase.

## In Scope

- Define the sampling contract for WU-002 scanner outputs, including stable snapshot keys, required fields, and state transitions to capture.
- Refine the BTC 1d market lifecycle model so active opportunity windows, scheduled-but-not-yet-active markets, and terminal markets are sampled differently instead of all being treated as periodic `rejected` snapshots.
- Implement durable snapshot persistence for BTC Up/Down Daily opportunities, observations, and relevant surrounding states.
- Distinguish between opportunity sampling and market-lifecycle tracking so `outside_overlap_window` and `reference_price_not_fixed` states are recorded as bounded lifecycle transitions rather than repeatedly sampled opportunity rows.
- Use SQLite as the default first-phase storage for live snapshot capture and offline analysis.
- Record enough signal provenance to explain each sampled opportunity, including reconstructed reference price, selected option expiry, lower/upper strikes, lower/upper deltas, interpolated option proxy, Binance signal value, Polymarket top of book, classification, and forced-exit time.
- Implement a bounded sampling scheduler that checks on a short cadence but writes snapshots according to tiered rules instead of blindly writing every scheduler tick.
- Ensure that for BTC Up/Down Daily only the currently active market window is sampled at dense interval cadence; tomorrow or not-yet-started markets should only emit state-change snapshots until they become active.
- Define and implement tiered sampling behavior, including slower baseline sampling, denser sampling for tradable opportunities, denser sampling near forced exit, and immediate sampling on meaningful state changes.
- Implement a deterministic post-hoc validation workflow that converts sampled opportunities into hypothetical trades using fixed entry and exit rules.
- Define the first fixed replay rules for entry, early exit, forced exit, and signal invalidation so results are comparable across samples.
- Ensure replay entry logic actually enforces the configured `min_net_edge` threshold at open time, so sub-threshold and negative-edge snapshots cannot seed hypothetical trades and contaminate summary statistics.
- Ensure Polymarket binary-market top-of-book fields are stored with complement-consistent `UP` and `DOWN` bid/ask pairs so replay cannot use impossible mirrored prices.
- Produce summary metrics that quantify opportunity quality, including realized or best-available convergence before forced exit, time-to-convergence, maximum adverse movement, and edge decay.
- Encode the next-phase market-data boundary: Polymarket may be upgraded toward websocket-first capture if it materially improves order book fidelity, while Binance may remain a mixed REST plus metadata model so long as signal correctness is preserved.
- Add bounded verification for snapshot persistence, replay calculation, and summary metric generation where practical.
- Write durable findings back into the work artifact so WU-004 can inherit concrete thresholds instead of chat-only conclusions.

## Out Of Scope

- Authenticated Polymarket trading support.
- Paper trading execution logic or trade orchestration.
- Live order placement, cancellation, or executor actions.
- Rebuilding the entire Probability Gap scanner architecture from WU-002.
- Generalizing beyond BTC Up/Down Daily markets.
- Mandatory full websocket migration for both Binance and Polymarket in this phase.
- Production dashboarding beyond the minimum status or report surface needed to inspect sampling and replay outputs.
- Real PnL claims based on actual fills; this task only validates hypothetical, rule-based realizability.

## Expected Touch Points

- `.yxg/work/active/WU-003-wu-002-probability-gap.md`
- [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1)
- [controllers/generic/probability_gap_scanner_utils.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner_utils.py:1)
- [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1)
- [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1)
- `hummingbot/strategy_v2/` support surfaces needed to persist or expose sampled snapshots
- a new local persistence or analysis module for snapshot capture and replay
- a local SQLite artifact under `.yxg/` or another explicit repository-local data path for sampled opportunity history
- [test/controllers/test_probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_sampling.py:1)
- targeted tests for sampling, replay, and summary metrics

## Dependencies

- WU-002 archived scanner implementation and its live signal contract.
- Public Polymarket market data for BTC Up/Down Daily markets.
- Public Binance spot and options data used by WU-002.
- A repository-local writable path for durable snapshot storage.

## Assumptions

- WU-002 remains the authoritative first-phase scanner and signal-definition layer.
- The immediate goal is to validate edge realizability, not to optimize execution quality yet.
- SQLite is sufficient for first-phase live snapshot persistence and offline replay.
- A short scheduler loop may run frequently, but snapshot writes should be event-aware and tiered rather than one-row-per-tick by default.
- Polymarket order book fidelity matters more than exhaustive Binance streaming in this phase because Polymarket is the venue whose edge realization must be measured.
- Binance static option metadata may continue to come from REST if that remains the simplest correct source of expiry and strike context.
- Fixed replay rules are acceptable in this phase even if they are conservative, because comparability across samples matters more than maximizing paper returns.

## Risks

- Opportunity samples may be too sparse or too noisy if sampling frequency is miscalibrated.
- If not-yet-started markets continue to be recorded as periodic `rejected_interval` rows, the SQLite dataset will be polluted with lifecycle noise that does not represent realizable opportunity windows.
- REST-only Polymarket snapshots may miss transient order-book changes that matter for realizability, which could push this phase toward a websocket-first Polymarket capture path.
- A one-row-per-tick design could create a large amount of duplicate data without improving the decision quality of the replay analysis.
- Replay rules that are too permissive or too conservative could distort the measured usefulness of scanner signals.
- Incorrect binary complement derivation for `DOWN` bid/ask can produce impossible replay exits and materially overstate hypothetical PnL, especially around side flips.
- SQLite schema design may need revision if the first sample set shows that state transitions and opportunity windows are more complex than expected.
- Existing unrelated worktree changes under `plugins/` remain present and must not be folded into this task.

## Plan

1. Translate the WU-002 scanner output into a durable sampling contract with explicit snapshot keys, required fields, and state-transition semantics.
2. Implement a repository-local persistence layer that records scanner snapshots to SQLite with enough provenance to replay the decision later.
3. Add tiered sampling rules so the scheduler can check frequently while writes remain denser only for tradable windows, state changes, and near-exit periods.
4. Split BTC 1d market handling into at least three lifecycle buckets: active opportunity window, scheduled/not-yet-started market, and terminal market; only the active bucket should receive dense interval sampling.
5. Capture and store Binance-side provenance, Polymarket top-of-book data, classification state, overlap-window boundaries, and forced-exit timestamps for each sampled market.
6. Implement a deterministic replay workflow that turns a sampled tradable state into a hypothetical trade with fixed entry, early-exit, and forced-exit rules.
7. Tighten replay entry gating so only snapshots whose entry-side edge meets or exceeds the configured `min_net_edge` can open a replayed trade.
8. Correct the Polymarket binary complement derivation so `down_best_ask = 1 - up_best_bid` and `down_best_bid = 1 - up_best_ask`, then recompute replay outputs on the clean corpus before using them for threshold or PnL conclusions.
9. Generate per-opportunity attribution outputs and aggregate summaries that quantify convergence quality, edge decay, and opportunity usefulness.
10. Evaluate whether Polymarket capture quality is sufficient with the current transport; if not, add a bounded Polymarket stream-first path without requiring a full Binance websocket rewrite.
11. Add targeted tests and a compact operator-facing report so the results can be reviewed before opening WU-004.
12. Write findings, thresholds, lifecycle-handling rules, and transport decisions back into the work artifact so the next task starts from measured evidence rather than chat history.

## Verification

- The system can persist repeated scanner outputs for BTC Up/Down Daily markets into SQLite without losing the provenance fields needed to explain each signal.
- Snapshot writes follow the defined tiered sampling rules instead of unconditionally writing a full row on every scheduler tick.
- Scheduled/not-yet-started markets such as tomorrow's BTC daily market do not continue generating periodic `rejected_interval` rows; they only emit bounded lifecycle snapshots until they transition into an active opportunity window.
- A deterministic replay can be run from stored snapshots and produces consistent entry, exit, and attribution outputs from the same dataset.
- Replay entry logic honors the configured `min_net_edge` threshold at open time; sub-threshold or negative-edge snapshots are not allowed to open hypothetical trades.
- Stored Polymarket `DOWN` top-of-book values obey binary complement rules, so replay entry and exit prices remain internally consistent with the sampled `UP` book.
- The replay output includes at least: sampled entry price, forced-exit price, best available pre-exit move, max adverse move, holding duration, and realized or hypothetical edge outcome under the fixed rules.
- Aggregate reports can show which minimum net-edge ranges and timing conditions appear promising versus not worth carrying into paper trading.
- Any websocket adoption in this task is bounded and documented; the task must not silently convert both venues to full stream-based ingestion without evidence that it is needed.

## Done When

- A durable sampling path exists for WU-002 scanner outputs and persists the agreed snapshot schema into SQLite.
- The sampling path distinguishes active opportunity windows from scheduled lifecycle states, so the SQLite dataset is not dominated by repeated noise from markets that have not entered overlap yet.
- The sampled records preserve enough context to reconstruct why a market was classified as tradable, observable, or rejected at each sampled time.
- A bounded replay and attribution workflow exists and can score sampled opportunities using fixed entry and exit rules.
- Replay summaries are computed from trades whose openings satisfy the configured entry threshold, rather than from any `tradable` snapshot regardless of edge quality.
- Replay summaries used for threshold setting are based on complement-consistent Polymarket bid/ask fields; inflated `DOWN` exits from mirrored prices are removed before review.
- The task can produce a concrete summary of opportunity quality, including recommended minimum edge or timing thresholds for the next phase.
- The task documents whether Polymarket needs websocket-first capture in WU-004 and whether Binance can remain hybrid at this stage.
- The resulting artifact is sufficient to open WU-004 as a paper-trading decision-layer task without revisiting sampling fundamentals.

## Escalate If

- The scanner output from WU-002 lacks required provenance fields or changes shape in a way that prevents deterministic replay.
- SQLite proves too limited for the first sample volume or schema requirements.
- Polymarket REST snapshots are demonstrably too lossy to support meaningful realizability analysis.
- Binance signal provenance cannot be sampled reliably enough to replay the opportunity window.
- The work begins to require authenticated execution or live order management to answer the validation question.
- The sample set shows that fixed replay rules are misleading enough that this task would need to absorb a full paper-trading engine.

## Evidence Log

- WU-002 already established a live scanner for BTC Up/Down Daily markets, including reconstructed reference price, strike-aware option interpolation, overlap-window classification, and forced-exit timestamps; WU-003 should consume those outputs rather than redefine them.
- Discussion on 2026-04-21 established that the next blocking question is not scanner correctness but edge realizability before forced exit.
- Discussion on 2026-04-21 established that sampling should not blindly persist every scheduler tick because Hummingbot ticks are heartbeat-driven, while scanner refreshes and market updates are coarser and often repeated.
- Discussion on 2026-04-21 established that a tiered sampling policy is preferred: slower baseline sampling, faster sampling for tradable windows, denser sampling near forced exit, and immediate samples on meaningful state transitions.
- Discussion on 2026-04-21 established that the next phase should not force both Binance and Polymarket to migrate entirely to websocket ingestion; the preferred boundary is Polymarket stream-first if needed for order-book fidelity, while Binance may remain signal-correctness-first and hybrid.
- Implementation update on 2026-04-21: a new [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1) module now provides SQLite-backed snapshot persistence, tiered snapshot-reason selection, deterministic tradable-window replay, and aggregate replay summaries.
- Implementation update on 2026-04-21: [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1) now persists opportunities, observations, and rejections into a repository-local SQLite database, records top-of-book bid and ask fields needed for hypothetical exits, and exposes snapshot / replay counts through the scanner status surface.
- Implementation update on 2026-04-21: scanner refresh cadence is no longer a fixed 60-second baseline during active tradable windows. It now tightens dynamically using `tradable_refresh_interval` and `near_exit_refresh_interval`, while baseline windows remain on the slower cadence.
- Verification on 2026-04-21: `python -m compileall controllers/generic/probability_gap_scanner.py controllers/generic/probability_gap_sampling.py test/controllers/test_probability_gap_sampling.py` passed.
- Verification on 2026-04-21: `python -m compileall scripts/probability_gap_intraday_sampling.py` passed.
- Verification on 2026-04-21: `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_sampling.py` passed with `2 passed`, covering tiered snapshot-reason selection plus SQLite persistence and deterministic replay / summary generation.
- Verification on 2026-04-21: after tightening replay entry gating, `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_sampling.py` passed with `3 passed`. The new coverage explicitly verifies that sub-threshold and negative-edge snapshots do not open replay trades even if they are marked `tradable`.
- Verification on 2026-04-22: after tightening lifecycle-aware sampling for rejected BTC 1d markets, `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_sampling.py` passed with `4 passed`. The added coverage verifies that `rejected` markets such as `outside_overlap_window` no longer emit periodic interval snapshots and only record `state_change` when their lifecycle state actually changes.
- Verification on 2026-04-22: after correcting binary complement handling for `DOWN` replay prices, `PYTHONPATH=. pytest -q test/controllers/test_probability_gap_sampling.py` passed with `5 passed`. The added coverage verifies that replay reconstructs `DOWN` entry and exit prices from the sampled `UP` book (`down_ask = 1 - up_bid`, `down_bid = 1 - up_ask`) even if stored `DOWN` fields are stale or mirrored incorrectly.
- Implementation update on 2026-04-21: a reusable live runner now exists at [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1). It installs the same minimal scanner stubs used during smoke validation, runs the real Probability Gap scanner against live Binance and Polymarket public data, and prints per-iteration SQLite growth plus the latest sampled rows.
- Live verification on 2026-04-21: `python scripts/probability_gap_intraday_sampling.py --iterations 3 --sleep-seconds 12 --reset-db` ran successfully against live market data and wrote to [`.yxg/data/probability_gap_samples.sqlite`](/Users/bytedance/Projects/hummingbot/.yxg/data/probability_gap_samples.sqlite). The run started at `2026-04-21T07:02:11Z` and produced row growth from `2 -> 3 -> 4` across three iterations. The sampled `bitcoin-up-or-down-on-april-21-2026` market remained `tradable / UP` and was recorded first as `initial_capture` and then twice as `tradable_interval`, while `bitcoin-up-or-down-on-april-22-2026` was recorded once as `rejected / initial_capture`.
- Live verification on 2026-04-21: immediately after the intraday sampling run, the real SQLite database still reported `REPLAY_COUNT = 0` and a zeroed replay summary. This is expected because the live sample window has not yet recorded an exit event such as forced exit, classification change, side flip, or edge decay below threshold.
- Live verification on 2026-04-21: a longer real sampling window via `python scripts/probability_gap_intraday_sampling.py --iterations 20 --sleep-seconds 15 --reset-db` ran from `2026-04-21T07:08:40Z` to `2026-04-21T07:13:33Z` and grew the SQLite database from `2` to `25` rows. `bitcoin-up-or-down-on-april-21-2026` remained `tradable / UP` for all 20 iterations and accumulated `20` tradable snapshots with `best_net_edge` roughly ranging from `0.1024` to `0.1349`, while `bitcoin-up-or-down-on-april-22-2026` accumulated `5` rejected snapshots through `rejected_interval` sampling. A follow-up replay summary on the real database still returned `REPLAY_COUNT = 0`, confirming that the persistence path is stable over a longer live window and that the remaining blocker for real replay output is an actual closeout event rather than a storage or replay bug.
- Implementation hardening on 2026-04-21: a live intraday run exposed that transient DNS failures from `aiohttp` were being amplified into a full runner crash because the lightweight stubbed `ControllerBase` in [scripts/probability_gap_intraday_sampling.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_intraday_sampling.py:1) did not provide the `logger()` method expected by [ProbabilityGapScanner.update_processed_data()](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:222). The runner stub now provides `logger()` and prints per-iteration `error` state, so temporary network failures degrade into logged sampling gaps instead of terminating the whole live run.
- Analysis on 2026-04-21: the real SQLite database now contains a longer near-exit sample set with `148` rows and a nonzero replay summary (`7` replayed windows). However, replay inspection showed that several hypothetical trades were opened from snapshots whose `entry_net_edge` was below the configured `min_net_edge=0.01`, including negative-edge entries. This means the current replay implementation is too permissive at entry time and pollutes summary statistics. WU-003 therefore now explicitly includes tightening replay entry gating so only qualifying snapshots can seed replay trades before any threshold conclusions are carried into WU-004.
- Implementation update on 2026-04-21: [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1) now enforces `min_net_edge` at replay open time using the entry-side edge (`net_edge_up` or `net_edge_down`) rather than opening on any `tradable` snapshot. This prevents weak or negative-edge snapshots from seeding replay trades.
- Analysis on 2026-04-21: rerunning replay on the existing `148`-row real SQLite dataset after the entry-gating fix reduced the replay set from `7` windows to `3` valid windows. The cleaned summary is now `n_replays=3`, `positive_ratio=0.3333`, `avg_realized_move=0.0067`, `avg_best_available_move=0.0133`, and `avg_holding_minutes=4.73`. All three remaining windows are `UP` entries on `bitcoin-up-or-down-on-april-21-2026`, with one thick-edge positive replay (`entry_net_edge ≈ 0.1371`, `realized_move = +0.04`) and two thinner-edge losers (`entry_net_edge ≈ 0.0128` and `0.0356`, both `realized_move = -0.01`). The cleaned evidence now supports a more conservative interpretation: thick edges appear materially better than near-threshold entries, and the previous `7`-window summary should no longer be used for threshold setting.
- Analysis on 2026-04-22: review of the accumulated SQLite samples showed that tomorrow's BTC daily market was repeatedly recorded as `rejected_interval` while it was simply `outside_overlap_window`. For BTC 1d markets this is lifecycle noise rather than opportunity evidence, because at any given time there is effectively one active market and the next market is merely scheduled. WU-003 therefore now explicitly requires lifecycle-aware sampling: active markets may be sampled densely, but `outside_overlap_window`, `reference_price_not_fixed`, and terminal states should be recorded only on meaningful state transitions instead of periodic interval writes.
- Implementation update on 2026-04-22: [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1) now suppresses periodic interval writes for `rejected` snapshots after their initial capture. For BTC 1d this means tomorrow's market will no longer keep generating `rejected_interval` rows while it remains `outside_overlap_window`; it will only write again if its lifecycle state actually changes.
- Live verification on 2026-04-22: `python scripts/probability_gap_intraday_sampling.py --iterations 10 --sleep-seconds 8 --db-path /tmp/probability_gap_sampling_verify.sqlite --reset-db` confirmed the lifecycle-aware sampling change. The temporary SQLite database finished with `6` rows total: `5` rows for the active `bitcoin-up-or-down-on-april-22-2026` market (`initial_capture` + `tradable_interval`) and only `1` row for the scheduled `bitcoin-up-or-down-on-april-23-2026` market (`rejected / initial_capture`). No `rejected_interval` rows were emitted for the tomorrow market while it remained `outside_overlap_window`.
- Live verification on 2026-04-22: the first longer clean-corpus run at [`.yxg/data/probability_gap_samples_clean.sqlite`](/Users/bytedance/Projects/hummingbot/.yxg/data/probability_gap_samples_clean.sqlite) accumulated `601` rows without lifecycle pollution: `600` rows for the active `bitcoin-up-or-down-on-april-22-2026` market and exactly `1` lifecycle row for `bitcoin-up-or-down-on-april-23-2026`. Snapshot reasons were `478 tradable_interval`, `113 near_exit_interval`, `6 side_flip`, `2 edge_threshold_cross`, and `2 initial_capture`. Replay on the clean corpus now returns `2` valid windows: one early `UP` window (`entry_net_edge ≈ 0.0490`, `realized_move = 0.00`, `best_available_move = +0.01`, exit via `edge_decay`) and one later `DOWN` window (`entry_net_edge ≈ 0.0124`, `realized_move = +0.88`, `best_available_move = +0.89`, exit via `side_flip`). The cleaned aggregate summary is `n_replays=2`, `positive_ratio=0.5`, `avg_realized_move=0.44`, `avg_best_available_move=0.45`, `avg_holding_minutes=58.66`. This is still a small sample, but it shows the clean-corpus flow can now capture a meaningful directional regime change without tomorrow-market noise dominating the dataset.
- Analysis on 2026-04-22: inspection of the clean corpus showed that the stored `DOWN` top-of-book fields are not complement-consistent. The scanner currently derives `down_best_ask` from `1 - up_best_bid`, but the stored `down_best_bid` path is mirrored incorrectly, which can produce impossible pairs such as `down_best_ask = 0.06` and `down_best_bid = 0.94`. Under correct binary complement rules the bid should be `1 - up_best_ask`, which in the sampled `DOWN` replay would have produced an exit near `0.05` rather than `0.94`.
- Analysis on 2026-04-22: because of the incorrect `DOWN` bid derivation, the current clean-corpus replay summary is overstated and must not be used for threshold or PnL conclusions. A manual recomputation on the same two replay windows yields: the first `UP` trade remains flat (`0.94 -> 0.94`), while the second `DOWN` trade changes from the inflated `0.06 -> 0.94` path to an approximately `0.06 -> 0.05` path, i.e. a small loss rather than a large gain. WU-003 therefore now explicitly requires fixing the complement derivation and rerunning replay on the clean corpus before using the dataset for threshold setting or paper-trading decisions.
- Implementation update on 2026-04-22: [controllers/generic/probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_scanner.py:1) now stores `polymarket_down_best_bid` using the correct binary complement of the sampled `UP` ask, and [controllers/generic/probability_gap_sampling.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_sampling.py:1) now reconstructs `DOWN` entry and exit prices from the sampled `UP` book during replay. This makes replay robust against older rows whose `DOWN` fields were stored incorrectly.
- Analysis on 2026-04-22: rerunning replay on the clean corpus after the complement fix preserved `2` valid windows but materially changed the outcome. The corrected summary is now `n_replays=2`, `positive_ratio=0.0`, `avg_realized_move=-0.005`, `avg_best_available_move=0.005`, and `avg_holding_minutes=58.66`. The first `UP` replay remains flat (`0.94 -> 0.94`, exit via `edge_decay`); the second `DOWN` replay now resolves to `0.06 -> 0.05` with `realized_move = -0.01` and exit via `side_flip`. The earlier clean-corpus result showing `+0.88` on the `DOWN` window is now explicitly superseded and must not be used for threshold or paper-trading conclusions.
- Data-quality review on 2026-04-23: the current clean corpus still contains `600` historical rows whose stored `down_best_bid` does not satisfy binary complement consistency. This is expected because those rows were captured before the storage fix; replay is now robust because it reconstructs `DOWN` prices from the sampled `UP` book, but any direct SQL analysis over stored `down_*` fields on this corpus remains unsafe until a new post-fix corpus is collected.
- Data-quality review on 2026-04-23: `market_classification='tradable'` is broader than “actionable opportunity.” In the current clean corpus, `147` tradable rows have `best_net_edge < 0.01` and `143` have negative `best_net_edge`. This is not a replay bug after the entry-gating fix, but it means future threshold analysis must filter on side-specific entry edge rather than relying on the tradable classification alone.
- Data-quality review on 2026-04-23: the current clean corpus shows two distinct forced-exit regimes for the same daily market: `462` rows tied to `2026-04-22T08:00:00Z` and `138` rows tied to `2026-04-22T15:45:00Z`, with corresponding option expiries of `2026-04-22T08:00:00Z` and `2026-04-23T08:00:00Z`. This indicates the signal source rolled from same-day to next-day option expiry once the earlier contract expired. That behavior is consistent with the current implementation, but replay and future paper-trading rules must treat it as an explicit regime change rather than assuming one continuous expiry source for the whole market day.
- Live verification on 2026-04-23: the first post-fix corpus at [`.yxg/data/probability_gap_samples_postfix.sqlite`](/Users/bytedance/Projects/hummingbot/.yxg/data/probability_gap_samples_postfix.sqlite) accumulated `951` rows from `2026-04-23T04:39:27Z` through `2026-04-23T09:07:13Z`. The corpus has `949` tradable rows for `bitcoin-up-or-down-on-april-23-2026` plus two bounded lifecycle rows, one for the same market at `binance_signal_expired` and one for `bitcoin-up-or-down-on-april-24-2026` at `outside_overlap_window`.
- Data-quality review on 2026-04-23: the post-fix corpus has `0` binary complement mismatches, confirming that future stored `DOWN` bid/ask fields now satisfy the corrected relationship. It also has no duplicate `(observed_at, market_slug, signal_window_id)` keys and no repeated tomorrow-market `rejected_interval` pollution.
- Replay review on 2026-04-23: using the current replay rules on the post-fix corpus gives weak results across thresholds. At `min_net_edge=0.01`, replay returns `5` windows with `positive_ratio=0.2` and `avg_realized_move=-0.008`. At `0.05`, replay returns `17` windows with `positive_ratio=0.1176` and `avg_realized_move=-0.0059`. At `0.10`, replay returns `1` window with `realized_move=0.00`. These results do not support a positive threshold conclusion from this single day.
- Replay design review on 2026-04-23: the current replay model can repeatedly re-enter the same continuous signal regime after edge decay, producing many short fragmented windows when `min_net_edge` is raised. This is useful for debugging but may over-count opportunities relative to a real paper strategy. Before WU-004, replay should likely add a cooldown, one-position-per-market/window rule, or explicit re-entry policy so threshold statistics better approximate executable behavior.
- Tooling update on 2026-05-02: a repository-local 7-day sampling scheduler wrapper now exists at [scripts/probability_gap_sampling_schedule.sh](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_sampling_schedule.sh:1), with a launchd template at [scripts/com.hummingbot.probability-gap-sampling.plist](/Users/bytedance/Projects/hummingbot/scripts/com.hummingbot.probability-gap-sampling.plist:1). The wrapper runs the main `12:00-17:00 CST` window and evening `22:30-00:xx CST` window, uses `caffeinate` to reduce macOS sleep interruptions, writes to the post-fix corpus, and stops after `PROB_GAP_RUN_DAYS=7`.
- Verification gap on 2026-04-21: the existing controller-level scanner test suite under [test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py](/Users/bytedance/Projects/hummingbot/test/hummingbot/strategy_v2/controllers/test_probability_gap_scanner.py:1) is currently blocked by a degraded shared dependency sandbox under `/tmp/hb_pydeps` involving empty or incompatible third-party packages (`hexbytes`, `aiohttp`, `async_timeout`, `protobuf`, `bidict`, `xrpl`). This is an environment-maintenance problem rather than a direct regression from WU-003, but it currently prevents full controller-level pytest confirmation in the same path used during WU-002.

## Notes

- This task exists to decide whether WU-002 opportunities are worth elevating into a paper-trading rule layer.
- The task should prefer simple, inspectable sampling and replay logic over premature infrastructure generalization.
- If the controller-level pytest environment remains unstable, review should accept compile-time validation plus pure-module sampling tests for the new WU-003 logic, while leaving restoration of the shared `/tmp/hb_pydeps` harness as a separate environment task or opportunistic cleanup item.
