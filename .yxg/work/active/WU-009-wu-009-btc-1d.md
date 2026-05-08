---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-009
slug: wu-009-btc-1d
title: WU-009: BTC 1d probability gap paper trading engine。仅在 WU-008 给出 go 条件后，实现虚拟资金、虚拟持仓、订单生命周期、maker quote/cancel/fill 模拟账本、风控限额和日报；不接真实 Polymarket 下单，不使用真实资金。
status: ready
priority: medium
owner_role: planner
created_at: "2026-05-05"
updated_at: "2026-05-05"
---

# Work Unit

## Objective

Implement a paper trading engine for the BTC 1d probability-gap strategy only after WU-008 produces a go decision. The outcome should simulate virtual capital, positions, order lifecycle, maker quote/cancel/fill events, risk limits, and reporting without using real funds or sending real Polymarket orders.

## In Scope

- Implement a virtual portfolio with cash, reserved cash, positions, realized PnL, unrealized PnL, and per-market exposure.
- Implement simulated order lifecycle: create quote, update quote, cancel quote, simulated fill, closeout, forced exit, and settlement.
- Consume the narrowed strategy configuration from WU-008.
- Apply risk controls: max stake per market, max daily loss, max open exposure, side concentration, market cooldown, and forced-exit cutoff.
- Persist paper trades and daily reports to local storage.
- Produce daily/market reports comparing paper fills against replay expectations.
- Keep all orders simulated; no authenticated Polymarket or wallet actions.

## Out Of Scope

- Real trading, signing, wallet access, API keys, or live Polymarket order placement.
- Strategy discovery or broad parameter optimization; WU-009 should use WU-008-approved rules.
- Changing fair-value model or scanner pricing.
- Replacing live sampling infrastructure unless minimal integration is required to feed the paper engine.
- Claiming production readiness.

## Expected Touch Points

- New paper trading module under `controllers/generic/` or `scripts/`.
- Existing probability-gap replay/strategy modules if shared config objects are needed.
- A CLI/script for running paper trading over live snapshots or replayed snapshots.
- Local paper-trade storage under `.yxg/data/` or another explicit local data path.
- Tests under `test/controllers/`.
- `.yxg/work/active/WU-009-wu-009-btc-1d.md`

## Dependencies
- WU-008 must produce a `go_paper` candidate configuration.
- WU-006 settlement validation and WU-007 toxicity/cancel filters should be incorporated into the WU-008 candidate.
- Live sampling must be stable enough to feed paper decisions.

## Assumptions
- Paper trading can use stored snapshots or live scanner snapshots as inputs.
- Simulated fills remain an approximation until real order queue/depth data is available.
- The first paper engine should prioritize auditability and risk limits over speed.

## Risks
- Paper fills can be over-optimistic without queue position and size.
- A live paper loop can fail silently if sampling stops or dependencies break.
- Risk controls may not reflect real market impact.
- Users may confuse paper results with production-readiness if reports are not explicit.

## Plan

1. Confirm WU-008 has a `go_paper` candidate and import its strategy config.
2. Define paper portfolio, order, fill, position, and report data models.
3. Implement deterministic paper order lifecycle over snapshot inputs.
4. Implement virtual risk controls and hard stop conditions.
5. Implement persistence for paper orders, fills, positions, and daily reports.
6. Add a CLI or scheduler-friendly runner for paper trading.
7. Add reporting comparing paper outcomes with replay assumptions.
8. Add tests for portfolio accounting, fills, cancels, risk limits, forced exit, settlement, and reporting.
9. Run a dry paper session on historical snapshots before live paper mode.
10. Document exact run commands and operational checks.

## Verification

- Unit tests verify cash/reserve/position accounting.
- Unit tests verify order lifecycle transitions and cancel/fill precedence.
- Unit tests verify risk limits block new orders and force stop when required.
- Unit tests verify settlement and forced-exit accounting.
- A dry run over historical snapshots produces a complete paper ledger and report.
- The runner cannot send real orders and has no credential requirement.

## Done When

- Paper trading can run with the WU-008-approved candidate config and produce persistent simulated trades.
- Reports include PnL, drawdown, fill rate, toxic fill diagnostics, market exposure, and rule violations.
- The implementation has no real trading side effects.
- The task artifact records how to run, monitor, and stop the paper engine.

## Escalate If

- WU-008 does not produce a `go_paper` candidate.
- Paper fills require order size/depth data not available in snapshots.
- Risk limits cannot be implemented without ambiguous user policy.
- The user requests real trading or credentials before paper trading is validated.

## Evidence Log

- WU-009 is intentionally gated behind WU-008 and should not be executed until a narrowed candidate passes go/no-go criteria.
- Current strategy research has not yet justified paper trading; WU-009 is a future task placeholder with strict dependencies.

## Notes
- This task should remain draft/blocked until WU-008 recommends paper trading.
