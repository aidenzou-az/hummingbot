---
artifact_type: work
schema_version: "1.0"
kernel_version: "1"
id: WU-001
slug: polymarket-binance-options-probability
title: 把 Polymarket 与 Binance Options 的 Probability Gap 策略转成 Hummingbot 内的正式任务单。范围包括：确认合规与市场可执行性约束；定义市场匹配、结算时点对齐与概率信号口径；规划只读 scanner 的最小可行实现；明确后续回测、paper trading、实盘的阶段边界。当前不进入实现，不创建 roadmap 之外的新功能需求，先产出可执行的 work contract。
status: done
priority: medium
owner_role: planner
created_at: "2026-04-16"
updated_at: "2026-04-16"
---

# Work Unit

## Objective
Produce a durable work contract for automating the Polymarket vs Binance Options "Probability Gap" strategy inside Hummingbot, limited to feasibility confirmation, signal definition, market/time alignment rules, and the minimum viable design for a read-only scanner. This work unit should leave the repository with a clear implementation contract for later coding, backtesting, paper trading, and live-trading phases without starting those phases yet.

## In Scope
- Confirm external execution constraints that materially affect automation, including venue API access and geographic/account restrictions.
- Define the target strategy as a probability-signal trading system rather than assume it is true riskless arbitrage.
- Specify how Binance Options data and Polymarket market/order book data should be matched.
- Define settlement-time and market-resolution alignment requirements.
- Define the signal shape for the first version, including probability proxy, edge calculation, and cost/risk adjustments.
- Plan the minimum viable read-only scanner.
- Define the phase boundaries for later backtesting, paper trading, and live trading.
- Record durable evidence from repository inspection and external documentation that supports the work contract.

## Out Of Scope
- Implementing a Polymarket connector.
- Implementing a Binance Options connector.
- Writing a live executor or placing real orders.
- Adding unrelated strategy features, dashboards, or generalized event-market support.
- Treating the strategy as a production-ready arbitrage system without validation.
- Creating a new roadmap beyond the agreed phase sequence.

## Expected Touch Points
- `.yxg/work/active/WU-001-polymarket-binance-options-probability.md`
- `.yxg/STATE.md`
- `.yxg/INDEX.md`
- [hummingbot/connector/exchange_py_base.py](/Users/bytedance/Projects/hummingbot/hummingbot/connector/exchange_py_base.py:37)
- [hummingbot/connector/exchange/binance/binance_exchange.py](/Users/bytedance/Projects/hummingbot/hummingbot/connector/exchange/binance/binance_exchange.py:30)
- [hummingbot/data_feed/market_data_provider.py](/Users/bytedance/Projects/hummingbot/hummingbot/data_feed/market_data_provider.py:27)
- [hummingbot/strategy_v2/controllers/controller_base.py](/Users/bytedance/Projects/hummingbot/hummingbot/strategy_v2/controllers/controller_base.py:58)
- [hummingbot/strategy_v2/executors/arbitrage_executor/arbitrage_executor.py](/Users/bytedance/Projects/hummingbot/hummingbot/strategy_v2/executors/arbitrage_executor/arbitrage_executor.py:18)
- [controllers/generic/examples/market_status_controller.py](/Users/bytedance/Projects/hummingbot/controllers/generic/examples/market_status_controller.py:1)
- [controllers/generic/arbitrage_controller.py](/Users/bytedance/Projects/hummingbot/controllers/generic/arbitrage_controller.py:1)
- Future implementation surfaces, if approved later:
- `hummingbot/connector/<new polymarket surface>`
- `hummingbot/connector/<new binance options surface or data source>`
- `hummingbot/strategy_v2/controllers/<probability gap controller>`

## Dependencies
- Existing `.yxg` baseline import for this repository.
- Access to current Binance Options and Polymarket developer documentation.
- A user decision later on whether the environment and account setup are legally and operationally allowed to place Polymarket orders.

## Assumptions
- Binance Options delta is treated as an institutionally informed probability proxy, not as a guaranteed true payout probability.
- The first implementation phase should be read-only and should not place orders.
- The initial target market class is narrow and explicitly matchable, such as BTC same-day threshold markets, rather than arbitrary prediction markets.
- Hummingbot is a reasonable host for the eventual automation because it already provides connector, controller, and executor abstractions.

## Risks
- Polymarket may be unavailable for authenticated trading in the actual execution jurisdiction or account context.
- Binance option settlement definitions and Polymarket market resolution rules may not align tightly enough for the strategy to be valid.
- Delta may be a noisy probability proxy near expiry, especially after volatility shocks or liquidity dislocations.
- A quoted edge may disappear after spread, fees, slippage, and partial-fill effects are applied.
- The repository currently appears to lack both a Polymarket connector and a Binance Options connector, increasing implementation cost.

## Plan
1. Confirm the external constraints that govern whether the strategy can be automated at all, including API capability and trading restrictions.
2. Define the exact target market template, matching rules, settlement alignment checks, and signal vocabulary.
3. Specify the minimum viable read-only scanner, including inputs, outputs, ranking fields, and non-goals.
4. Map the likely Hummingbot integration points and identify the missing connector/controller/executor surfaces.
5. Define the phase gates for backtesting, paper trading, and live trading so later work does not skip validation.
6. Finalize this work contract with evidence, assumptions, risks, verification criteria, and escalation triggers.

## Verification
- The work artifact contains a concrete objective, scope boundary, phased plan, and explicit non-goals.
- The contract records durable evidence for external constraints and repository integration points.
- The scanner definition is specific enough that a later implementation task can be created without reopening basic strategy questions.
- The contract explicitly states that live trading is out of scope for this work unit.
- The contract narrows the first supported market template, matching rules, and output fields enough that an implementer can build a scanner without making product-contract assumptions in code.

## Done When
- This work unit documents:
- the strategy classification and its core caveats
- the external execution constraints
- the market and settlement alignment rules
- the minimum viable read-only scanner scope
- the later phase boundaries for backtesting, paper trading, and live trading
- the likely Hummingbot touch points and missing infrastructure
- the preferred first implementation shape inside Hummingbot
- A follow-on implementation task could be created from this contract without needing to restate the core strategy assumptions.

## Escalate If
- Polymarket authenticated trading is blocked for the intended deployment jurisdiction or account setup.
- No exact or safely approximate market mapping can be defined between Polymarket events and Binance Options strikes/expiries.
- The signal cannot survive realistic transaction-cost assumptions in historical or simulated analysis.
- The strategy requires a hedged second leg from the start rather than the agreed read-only or single-venue first phase.
- Repository constraints or missing abstractions make Hummingbot a poor host for the first implementation phase.

## Evidence Log
- Repository evidence: Hummingbot already has generic exchange/strategy abstractions in [hummingbot/connector/exchange_py_base.py](/Users/bytedance/Projects/hummingbot/hummingbot/connector/exchange_py_base.py:37), [hummingbot/strategy_v2/controllers/controller_base.py](/Users/bytedance/Projects/hummingbot/hummingbot/strategy_v2/controllers/controller_base.py:58), and [hummingbot/strategy_v2/executors/arbitrage_executor/arbitrage_executor.py](/Users/bytedance/Projects/hummingbot/hummingbot/strategy_v2/executors/arbitrage_executor/arbitrage_executor.py:18).
- Repository evidence: current search did not reveal an existing `polymarket` connector or a `binance options` connector in this repository.
- Repository evidence: [controllers/generic/examples/market_status_controller.py](/Users/bytedance/Projects/hummingbot/controllers/generic/examples/market_status_controller.py:1) is a monitoring-only controller that updates processed data and returns no executor actions, which is a good fit for a first-phase read-only scanner.
- Repository evidence: [hummingbot/data_feed/market_data_provider.py](/Users/bytedance/Projects/hummingbot/hummingbot/data_feed/market_data_provider.py:27) already supports non-trading connector access and periodic rate updates, which is relevant if the scanner is built on public-data connectors before authenticated trading support exists.
- Repository evidence: [controllers/generic/arbitrage_controller.py](/Users/bytedance/Projects/hummingbot/controllers/generic/arbitrage_controller.py:1) shows the pattern for later controller-to-executor escalation if the scanner graduates into active trading.
- External evidence as of 2026-04-16: Binance Options developer docs expose option reference and mark data, including `strikePrice`, `expiryDate`, and `delta`. Sources: https://github.com/options-docs/en
- External evidence as of 2026-04-16: Polymarket provides public API access for market discovery and CLOB data, while authenticated trading uses a separate signed flow. Sources: https://docs.polymarket.com/api-reference/introduction and https://docs.polymarket.com/api-reference/authentication
- External evidence as of 2026-04-16: Polymarket documents geographic restrictions and lists the United States as blocked for trading access. Source: https://docs.polymarket.com/api-reference/geoblock
- External evidence as of 2026-04-16: CME educational material describes option delta as an approximate probability of expiring in the money, supporting its use only as a proxy signal rather than a guaranteed true probability. Source: https://www.cmegroup.com/education/courses/option-greeks/options-delta-the-greeks.html

## Notes
- Current intent is to transform prior strategy discussion into a formal planning contract, not to begin implementation.
- The preferred execution order established in chat is: constraints and market definition, then read-only scanner, then backtesting and simulation, then paper trading, then small-scale live trading if validated.
- Preferred first supported market template: BTC same-day threshold markets only, where the Polymarket question can be mapped to a single strike and a single same-day Binance expiry without ambiguous fallback logic.
- Matching rule for the first implementation: require exact or explicitly documented nearest-neighbor matching on underlying, threshold, expiry date, settlement timestamp, and reference-price definition; reject markets that fail exact settlement-definition checks.
- Scanner signal vocabulary for the first implementation: `binance_delta_proxy`, `polymarket_yes_best_ask`, `polymarket_no_best_ask`, `polymarket_mid`, `gross_edge_yes`, `gross_edge_no`, `estimated_cost`, `net_edge_yes`, `net_edge_no`, `depth_score`, `alignment_confidence`, and `rejection_reason`.
- Preferred first implementation shape inside Hummingbot: a monitoring-only controller that emits processed status and ranked opportunities, but no executor actions, until the signal and matching logic are validated.
- Recommended follow-on work split after this contract:
- scanner and market-matching implementation
- historical validation and replay
- paper-trading integration
- live-trading enablement only if prior gates pass
- Completion semantics: this work unit is complete when the planning contract is accepted. Actual strategy execution or coding must begin in a follow-on work unit rather than extending WU-001 beyond its planning scope.
- Administrative note: a prior `pass` review on WU-001 was reverted because it was interpreted as broader strategy completion instead of planning-contract completion. The intended meaning for final closure is contract completion only.
