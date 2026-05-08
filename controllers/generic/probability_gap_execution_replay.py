from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from controllers.generic.probability_gap_sampling import (
    ONE,
    ZERO,
    _complementary_down_ask,
    _complementary_down_bid,
    _entry_edge,
    _entry_ask,
    _exit_bid,
    replay_tradable_windows,
)


@dataclass(frozen=True)
class ExecutionReplayConfig:
    model_version: str = "iv_digital_v1"
    min_edge: Decimal = Decimal("0.02")
    quote_buffer: Decimal = Decimal("0.03")
    take_profit: Decimal = Decimal("0.03")
    stop_loss: Decimal = Decimal("0.02")
    time_stop_minutes: Decimal = Decimal("20")
    cooldown_seconds: int = 300
    min_time_to_expiry_minutes: Decimal = Decimal("15")
    max_spread: Decimal = Decimal("0.08")
    max_quote_wait_minutes: Decimal = Decimal("5")
    allowed_model_confidence: Tuple[str, ...] = ("medium", "high")
    allowed_gamma_risk: Tuple[str, ...] = ("low", "medium")
    fill_assumption: str = "conservative"


@dataclass(frozen=True)
class FutureDiagnostics:
    market_slug: str
    observed_at: datetime
    side: str
    model_version: str
    edge_after_30s: Optional[Decimal]
    edge_after_2m: Optional[Decimal]
    edge_after_5m: Optional[Decimal]
    fair_change_after_30s: Optional[Decimal]
    fair_change_after_2m: Optional[Decimal]
    fair_change_after_5m: Optional[Decimal]
    best_bid_after_30s: Optional[Decimal]
    best_bid_after_2m: Optional[Decimal]
    best_bid_after_5m: Optional[Decimal]
    best_ask_after_30s: Optional[Decimal]
    best_ask_after_2m: Optional[Decimal]
    best_ask_after_5m: Optional[Decimal]
    max_bid_reachable_next_5m: Optional[Decimal]
    min_ask_reachable_next_5m: Optional[Decimal]
    settlement_outcome: str
    settlement_source: str


@dataclass(frozen=True)
class ExecutionTrade:
    mode: str
    fill_assumption: str
    market_slug: str
    signal_window_id: str
    side: str
    model_version: str
    entry_signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    exit_reason: str
    quote_price: Optional[Decimal]
    entry_price: Decimal
    exit_price: Decimal
    realized_move: Decimal
    best_available_move: Decimal
    worst_available_move: Decimal
    holding_minutes: Decimal
    entry_net_edge: Decimal
    entry_fair: Optional[Decimal]
    gamma_risk: str
    model_confidence: str
    time_to_expiry_bucket: str
    moneyness_bucket: str
    edge_bucket: str
    spread_bucket: str


@dataclass(frozen=True)
class AdverseSelectionEvent:
    market_slug: str
    side: str
    fill_assumption: str
    horizon_seconds: int
    entry_time: datetime
    entry_price: Decimal
    entry_fair: Optional[Decimal]
    entry_edge: Decimal
    fair_change: Optional[Decimal]
    adverse_fair_move: Optional[bool]
    edge_value: Optional[Decimal]
    edge_disappeared: Optional[bool]
    bid_value: Optional[Decimal]
    bid_below_entry: Optional[bool]
    stop_loss_touched: bool
    gamma_risk: str
    model_confidence: str
    time_to_expiry_bucket: str
    moneyness_bucket: str
    edge_bucket: str
    spread_bucket: str


def build_future_diagnostics(
    snapshots: Sequence[Dict[str, Any]],
    horizons_seconds: Tuple[int, int, int] = (30, 120, 300),
) -> List[FutureDiagnostics]:
    grouped = _group_market_snapshots(snapshots)
    diagnostics: List[FutureDiagnostics] = []
    for market_slug, market_snapshots in grouped.items():
        ordered = _ordered_snapshots(market_snapshots)
        for index, snapshot in enumerate(ordered):
            observed_at = snapshot.get("observed_at")
            side = snapshot.get("best_side", "")
            if observed_at is None or side not in ("UP", "DOWN"):
                continue
            future = [
                _first_snapshot_at_or_after(ordered, index + 1, observed_at + timedelta(seconds=seconds))
                for seconds in horizons_seconds
            ]
            edge_values = [_entry_edge(item, side) if item is not None else None for item in future]
            fair_now = _side_fair(snapshot, side)
            fair_changes = [
                _decimal_difference(_side_fair(item, side) if item is not None else None, fair_now)
                for item in future
            ]
            bids = [_exit_bid(item, side) if item is not None else None for item in future]
            asks = [_entry_ask(item, side) if item is not None else None for item in future]
            reachable = _snapshots_until(ordered, index + 1, observed_at + timedelta(seconds=300))
            reachable_bids = [_exit_bid(item, side) for item in reachable]
            reachable_asks = [_entry_ask(item, side) for item in reachable]
            diagnostics.append(
                FutureDiagnostics(
                    market_slug=market_slug,
                    observed_at=observed_at,
                    side=side,
                    model_version=snapshot.get("model_version", ""),
                    edge_after_30s=edge_values[0],
                    edge_after_2m=edge_values[1],
                    edge_after_5m=edge_values[2],
                    fair_change_after_30s=fair_changes[0],
                    fair_change_after_2m=fair_changes[1],
                    fair_change_after_5m=fair_changes[2],
                    best_bid_after_30s=bids[0],
                    best_bid_after_2m=bids[1],
                    best_bid_after_5m=bids[2],
                    best_ask_after_30s=asks[0],
                    best_ask_after_2m=asks[1],
                    best_ask_after_5m=asks[2],
                    max_bid_reachable_next_5m=_max_decimal(reachable_bids),
                    min_ask_reachable_next_5m=_min_decimal(reachable_asks),
                    settlement_outcome=_settlement_outcome(snapshot),
                    settlement_source=_settlement_source(snapshot),
                )
            )
    return diagnostics


def replay_taker_baseline(
    snapshots: Sequence[Dict[str, Any]],
    config: ExecutionReplayConfig,
) -> List[ExecutionTrade]:
    filtered = [snapshot for snapshot in snapshots if _model_allowed(snapshot, config)]
    baseline = replay_tradable_windows(filtered, min_net_edge=config.min_edge)
    by_key = {
        (snapshot["market_slug"], snapshot["signal_window_id"], snapshot["observed_at"]): snapshot
        for snapshot in filtered
    }
    trades: List[ExecutionTrade] = []
    for trade in baseline:
        entry_snapshot = by_key.get((trade.market_slug, trade.signal_window_id, trade.entry_time), {})
        trades.append(
            _execution_trade_from_values(
                mode="taker_baseline",
                fill_assumption="immediate",
                entry_snapshot=entry_snapshot,
                side=trade.side,
                entry_signal_time=trade.entry_time,
                entry_time=trade.entry_time,
                exit_time=trade.exit_time,
                exit_reason=trade.exit_reason,
                quote_price=None,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                best_available_move=trade.best_available_move,
                worst_available_move=trade.worst_available_move,
                entry_net_edge=trade.entry_net_edge,
            )
        )
    return trades


def replay_taker_entry_hold(
    snapshots: Sequence[Dict[str, Any]],
    config: ExecutionReplayConfig,
) -> List[ExecutionTrade]:
    return _replay_position_mode(snapshots, config, mode="taker_hold")


def replay_maker_first(
    snapshots: Sequence[Dict[str, Any]],
    config: ExecutionReplayConfig,
) -> List[ExecutionTrade]:
    return _replay_position_mode(snapshots, config, mode="maker_first")


def run_execution_research(
    snapshots: Sequence[Dict[str, Any]],
    config: ExecutionReplayConfig,
    include_parameter_grid: bool = False,
) -> Dict[str, Any]:
    model_snapshots = [snapshot for snapshot in snapshots if _model_allowed(snapshot, config)]
    diagnostics = build_future_diagnostics(model_snapshots)
    trades_by_mode = {
        "taker_baseline": replay_taker_baseline(model_snapshots, config),
        "taker_hold": replay_taker_entry_hold(model_snapshots, config),
        "maker_first": replay_maker_first(model_snapshots, config),
    }
    all_trades = [trade for trades in trades_by_mode.values() for trade in trades]
    maker_adverse_events = build_maker_adverse_selection_events(model_snapshots, config)
    report = {
        "model_version": config.model_version,
        "snapshot_count": len(model_snapshots),
        "diagnostic_count": len(diagnostics),
        "diagnostic_coverage": _diagnostic_coverage(diagnostics),
        "summaries": {
            mode: summarize_execution_trades(trades)
            for mode, trades in trades_by_mode.items()
        },
        "bucket_report": bucket_execution_trades(all_trades),
        "adverse_selection_report": summarize_adverse_selection(maker_adverse_events),
        "paper_trading_go_no_go": paper_trading_go_no_go(all_trades, model_snapshots),
        "trades": [_serializable_trade(trade) for trade in all_trades],
    }
    if include_parameter_grid:
        report["parameter_grid"] = run_parameter_grid(model_snapshots, config)
    return report


def summarize_execution_trades(trades: Sequence[ExecutionTrade]) -> Dict[str, Any]:
    if not trades:
        return {
            "n_trades": 0,
            "positive_ratio": 0.0,
            "total_realized_move": 0.0,
            "avg_realized_move": 0.0,
            "avg_best_available_move": 0.0,
            "avg_worst_available_move": 0.0,
            "avg_holding_minutes": 0.0,
            "top_trade_concentration": 0.0,
        }
    count = Decimal(str(len(trades)))
    realized_total = sum((trade.realized_move for trade in trades), ZERO)
    positive = sum(1 for trade in trades if trade.realized_move > ZERO)
    best_total = sum((trade.best_available_move for trade in trades), ZERO)
    worst_total = sum((trade.worst_available_move for trade in trades), ZERO)
    holding_total = sum((trade.holding_minutes for trade in trades), ZERO)
    abs_total = sum((abs(trade.realized_move) for trade in trades), ZERO)
    max_abs = max((abs(trade.realized_move) for trade in trades), default=ZERO)
    concentration = Decimal("0") if abs_total == ZERO else max_abs / abs_total
    return {
        "n_trades": len(trades),
        "positive_ratio": float(Decimal(str(positive)) / count),
        "total_realized_move": float(realized_total),
        "avg_realized_move": float(realized_total / count),
        "avg_best_available_move": float(best_total / count),
        "avg_worst_available_move": float(worst_total / count),
        "avg_holding_minutes": float(holding_total / count),
        "top_trade_concentration": float(concentration),
    }


def bucket_execution_trades(trades: Sequence[ExecutionTrade]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, ...], List[ExecutionTrade]] = {}
    for trade in trades:
        key = (
            trade.mode,
            trade.fill_assumption,
            trade.side,
            trade.gamma_risk,
            trade.model_confidence,
            trade.time_to_expiry_bucket,
            trade.moneyness_bucket,
            trade.edge_bucket,
        )
        grouped.setdefault(key, []).append(trade)
    buckets = []
    for key, bucket_trades in sorted(grouped.items()):
        summary = summarize_execution_trades(bucket_trades)
        buckets.append(
            {
                "mode": key[0],
                "fill_assumption": key[1],
                "side": key[2],
                "gamma_risk": key[3],
                "model_confidence": key[4],
                "time_to_expiry_bucket": key[5],
                "moneyness_bucket": key[6],
                "edge_bucket": key[7],
                **summary,
            }
        )
    return buckets


def build_maker_adverse_selection_events(
    snapshots: Sequence[Dict[str, Any]],
    config: ExecutionReplayConfig,
    horizons_seconds: Tuple[int, ...] = (5, 30, 120, 300),
) -> List[AdverseSelectionEvent]:
    grouped = _group_market_snapshots([snapshot for snapshot in snapshots if _model_allowed(snapshot, config)])
    events: List[AdverseSelectionEvent] = []
    for market_snapshots in grouped.values():
        ordered = _ordered_snapshots(market_snapshots)
        index = 0
        blocked_until: Optional[datetime] = None
        while index < len(ordered):
            signal = ordered[index]
            signal_time = signal.get("observed_at")
            if signal_time is None:
                index += 1
                continue
            if blocked_until is not None and signal_time < blocked_until:
                index += 1
                continue
            side = signal.get("best_side", "")
            if not _eligible_entry(signal, side, config, "maker_first"):
                index += 1
                continue
            fair = _side_fair(signal, side)
            if fair is None:
                index += 1
                continue
            quote_price = _clamp_probability(fair - config.quote_buffer)
            fill_index = _find_maker_fill_index(ordered, index, side, quote_price, config)
            if fill_index is None:
                index += 1
                continue
            entry_snapshot = ordered[fill_index]
            entry_time = entry_snapshot.get("observed_at")
            if entry_time is None:
                index += 1
                continue
            entry_edge = _mode_entry_edge(signal, side, "maker_first") or ZERO
            entry_fair = _side_fair(signal, side)
            stop_loss_touch = False
            for horizon_seconds in horizons_seconds:
                future = _first_snapshot_at_or_after(
                    ordered,
                    fill_index + 1,
                    entry_time + timedelta(seconds=horizon_seconds),
                )
                path = _snapshots_until(
                    ordered,
                    fill_index + 1,
                    entry_time + timedelta(seconds=horizon_seconds),
                )
                min_move = _min_decimal(
                    (_decimal_difference(_exit_bid(item, side), quote_price) for item in path)
                )
                if min_move is not None and min_move <= -config.stop_loss:
                    stop_loss_touch = True
                future_fair = _side_fair(future, side) if future is not None else None
                fair_change = _decimal_difference(future_fair, entry_fair)
                edge_value = _mode_entry_edge(future, side, "maker_first") if future is not None else None
                bid_value = _exit_bid(future, side) if future is not None else None
                events.append(
                    AdverseSelectionEvent(
                        market_slug=signal.get("market_slug", ""),
                        side=side,
                        fill_assumption=config.fill_assumption,
                        horizon_seconds=horizon_seconds,
                        entry_time=entry_time,
                        entry_price=quote_price,
                        entry_fair=entry_fair,
                        entry_edge=entry_edge,
                        fair_change=fair_change,
                        adverse_fair_move=None if fair_change is None else fair_change < ZERO,
                        edge_value=edge_value,
                        edge_disappeared=None if edge_value is None else edge_value <= ZERO,
                        bid_value=bid_value,
                        bid_below_entry=None if bid_value is None else bid_value < quote_price,
                        stop_loss_touched=stop_loss_touch,
                        gamma_risk=signal.get("gamma_risk", ""),
                        model_confidence=signal.get("model_confidence", ""),
                        time_to_expiry_bucket=_time_to_expiry_bucket(signal),
                        moneyness_bucket=_moneyness_bucket(signal),
                        edge_bucket=_edge_bucket(entry_edge),
                        spread_bucket=_spread_bucket(_side_spread(signal, side)),
                    )
                )
            managed = _manage_position(ordered, fill_index, side, quote_price, config)
            if managed is None:
                index += 1
                continue
            exit_index, exit_snapshot, *_ = managed
            blocked_until = exit_snapshot["observed_at"] + timedelta(seconds=config.cooldown_seconds)
            index = max(exit_index + 1, _first_index_at_or_after(ordered, index + 1, blocked_until))
    return events


def summarize_adverse_selection(events: Sequence[AdverseSelectionEvent]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, ...], List[AdverseSelectionEvent]] = {}
    for event in events:
        key = (
            str(event.horizon_seconds),
            event.side,
            event.gamma_risk,
            event.model_confidence,
            event.time_to_expiry_bucket,
            event.moneyness_bucket,
            event.edge_bucket,
            event.spread_bucket,
            event.fill_assumption,
        )
        grouped.setdefault(key, []).append(event)
    rows = []
    for key, bucket_events in sorted(grouped.items()):
        rows.append(
            {
                "horizon_seconds": int(key[0]),
                "side": key[1],
                "gamma_risk": key[2],
                "model_confidence": key[3],
                "time_to_expiry_bucket": key[4],
                "moneyness_bucket": key[5],
                "edge_bucket": key[6],
                "spread_bucket": key[7],
                "fill_assumption": key[8],
                "n_events": len(bucket_events),
                "adverse_fair_ratio": _optional_bool_ratio(event.adverse_fair_move for event in bucket_events),
                "edge_disappeared_ratio": _optional_bool_ratio(event.edge_disappeared for event in bucket_events),
                "bid_below_entry_ratio": _optional_bool_ratio(event.bid_below_entry for event in bucket_events),
                "stop_loss_touched_ratio": _bool_ratio(event.stop_loss_touched for event in bucket_events),
                "avg_fair_change": _avg_optional_decimal(event.fair_change for event in bucket_events),
            }
        )
    return rows


def run_parameter_grid(
    snapshots: Sequence[Dict[str, Any]],
    base_config: ExecutionReplayConfig,
    buffers: Tuple[Decimal, ...] = (Decimal("0.02"), Decimal("0.03"), Decimal("0.05"), Decimal("0.08"), Decimal("0.10")),
    take_profits: Tuple[Decimal, ...] = (Decimal("0.01"), Decimal("0.02"), Decimal("0.03")),
    stop_losses: Tuple[Decimal, ...] = (Decimal("0.02"), Decimal("0.03"), Decimal("0.05"), Decimal("0.08")),
    cooldown_seconds_values: Tuple[int, ...] = (0, 300, 600),
    gamma_sets: Tuple[Tuple[str, ...], ...] = (("low",), ("low", "medium")),
    min_time_to_expiry_minutes_values: Tuple[Decimal, ...] = (Decimal("30"), Decimal("60"), Decimal("120")),
) -> Dict[str, Any]:
    rows = []
    for buffer in buffers:
        for take_profit in take_profits:
            for stop_loss in stop_losses:
                for cooldown_seconds in cooldown_seconds_values:
                    for gamma_set in gamma_sets:
                        for min_time in min_time_to_expiry_minutes_values:
                            config = ExecutionReplayConfig(
                                model_version=base_config.model_version,
                                min_edge=base_config.min_edge,
                                quote_buffer=buffer,
                                take_profit=take_profit,
                                stop_loss=stop_loss,
                                time_stop_minutes=base_config.time_stop_minutes,
                                cooldown_seconds=cooldown_seconds,
                                min_time_to_expiry_minutes=min_time,
                                max_spread=base_config.max_spread,
                                max_quote_wait_minutes=base_config.max_quote_wait_minutes,
                                allowed_model_confidence=base_config.allowed_model_confidence,
                                allowed_gamma_risk=gamma_set,
                                fill_assumption=base_config.fill_assumption,
                            )
                            trades = replay_maker_first(snapshots, config)
                            summary = summarize_execution_trades(trades)
                            rows.append(
                                {
                                    "buffer": str(buffer),
                                    "take_profit": str(take_profit),
                                    "stop_loss": str(stop_loss),
                                    "cooldown_seconds": cooldown_seconds,
                                    "gamma_set": "+".join(gamma_set),
                                    "min_time_to_expiry_minutes": str(min_time),
                                    **summary,
                                }
                            )
    return {
        "row_count": len(rows),
        "positive_rows": sum(1 for row in rows if row["total_realized_move"] > 0),
        "stable_regions": _parameter_stable_regions(rows),
        "top_rows": sorted(rows, key=lambda row: row["total_realized_move"], reverse=True)[:10],
        "bottom_rows": sorted(rows, key=lambda row: row["total_realized_move"])[:10],
    }


def _parameter_stable_regions(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    regions = []
    for dimension in ("buffer", "take_profit", "stop_loss", "cooldown_seconds", "gamma_set", "min_time_to_expiry_minutes"):
        values: Dict[Any, List[Dict[str, Any]]] = {}
        for row in rows:
            values.setdefault(row[dimension], []).append(row)
        for value, bucket in values.items():
            positive = [row for row in bucket if row["total_realized_move"] > 0]
            avg_total = sum(row["total_realized_move"] for row in bucket) / len(bucket)
            regions.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "row_count": len(bucket),
                    "positive_rows": len(positive),
                    "positive_ratio": len(positive) / len(bucket),
                    "avg_total_realized_move": avg_total,
                }
            )
    return sorted(regions, key=lambda row: (row["positive_ratio"], row["avg_total_realized_move"]), reverse=True)


def paper_trading_go_no_go(
    trades: Sequence[ExecutionTrade],
    snapshots: Sequence[Dict[str, Any]],
    min_complete_markets: int = 5,
) -> Dict[str, Any]:
    markets = {snapshot.get("market_slug") for snapshot in snapshots if snapshot.get("market_slug")}
    maker_trades = [trade for trade in trades if trade.mode == "maker_first"]
    maker_summary = summarize_execution_trades(maker_trades)
    reasons = []
    if len(markets) < min_complete_markets:
        reasons.append(f"needs_at_least_{min_complete_markets}_markets")
    if maker_summary["n_trades"] < 10:
        reasons.append("needs_at_least_10_maker_trades")
    if maker_summary["total_realized_move"] <= 0:
        reasons.append("maker_total_realized_not_positive")
    if maker_summary["top_trade_concentration"] > 0.35:
        reasons.append("maker_results_too_concentrated")
    return {
        "decision": "go_paper" if not reasons else "no_go",
        "reasons": reasons,
        "market_count": len(markets),
        "maker_summary": maker_summary,
    }


def _replay_position_mode(
    snapshots: Sequence[Dict[str, Any]],
    config: ExecutionReplayConfig,
    mode: str,
) -> List[ExecutionTrade]:
    grouped = _group_market_snapshots(snapshots)
    trades: List[ExecutionTrade] = []
    for market_snapshots in grouped.values():
        ordered = _ordered_snapshots(market_snapshots)
        index = 0
        blocked_until: Optional[datetime] = None
        while index < len(ordered):
            signal = ordered[index]
            observed_at = signal.get("observed_at")
            if observed_at is None:
                index += 1
                continue
            if blocked_until is not None and observed_at < blocked_until:
                index += 1
                continue
            side = signal.get("best_side", "")
            if not _eligible_entry(signal, side, config, mode):
                index += 1
                continue

            if mode == "maker_first":
                fair = _side_fair(signal, side)
                if fair is None:
                    index += 1
                    continue
                quote_price = _clamp_probability(fair - config.quote_buffer)
                fill_index = _find_maker_fill_index(ordered, index, side, quote_price, config)
                if fill_index is None:
                    index += 1
                    continue
                entry_snapshot = ordered[fill_index]
                entry_price = quote_price
                entry_time = entry_snapshot["observed_at"]
            else:
                quote_price = None
                fill_index = index
                entry_snapshot = signal
                entry_price = _entry_ask(signal, side)
                entry_time = observed_at

            if entry_price is None or entry_time is None:
                index += 1
                continue

            managed = _manage_position(ordered, fill_index, side, entry_price, config)
            if managed is None:
                index += 1
                continue
            exit_index, exit_snapshot, exit_reason, exit_price, best_move, worst_move = managed
            trades.append(
                _execution_trade_from_values(
                    mode=mode,
                    fill_assumption=config.fill_assumption if mode == "maker_first" else "immediate",
                    entry_snapshot=signal,
                    side=side,
                    entry_signal_time=observed_at,
                    entry_time=entry_time,
                    exit_time=exit_snapshot["observed_at"],
                    exit_reason=exit_reason,
                    quote_price=quote_price,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    best_available_move=best_move,
                    worst_available_move=worst_move,
                    entry_net_edge=_mode_entry_edge(signal, side, mode) or ZERO,
                )
            )
            blocked_until = exit_snapshot["observed_at"] + timedelta(seconds=config.cooldown_seconds)
            index = max(exit_index + 1, _first_index_at_or_after(ordered, index + 1, blocked_until))
    return trades


def _manage_position(
    ordered: Sequence[Dict[str, Any]],
    entry_index: int,
    side: str,
    entry_price: Decimal,
    config: ExecutionReplayConfig,
) -> Optional[Tuple[int, Dict[str, Any], str, Decimal, Decimal, Decimal]]:
    entry_time = ordered[entry_index].get("observed_at")
    if entry_time is None:
        return None
    best_move = ZERO
    worst_move = ZERO
    last_exit: Optional[Tuple[int, Dict[str, Any], str, Decimal, Decimal, Decimal]] = None
    for index in range(entry_index + 1, len(ordered)):
        snapshot = ordered[index]
        observed_at = snapshot.get("observed_at")
        if observed_at is None:
            continue
        exit_bid = _exit_bid(snapshot, side)
        if exit_bid is None:
            continue
        move = exit_bid - entry_price
        best_move = max(best_move, move)
        worst_move = min(worst_move, move)
        last_exit = (index, snapshot, "end_of_data", exit_bid, best_move, worst_move)

        forced_exit = snapshot.get("forced_exit_time")
        if forced_exit is not None and observed_at >= forced_exit:
            return index, snapshot, "forced_exit", exit_bid, best_move, worst_move
        if move >= config.take_profit:
            return index, snapshot, "take_profit", exit_bid, best_move, worst_move
        if move <= -config.stop_loss:
            return index, snapshot, "stop_loss", exit_bid, best_move, worst_move
        holding_minutes = Decimal(str((observed_at - entry_time).total_seconds() / 60))
        if holding_minutes >= config.time_stop_minutes:
            return index, snapshot, "time_stop", exit_bid, best_move, worst_move
    return last_exit


def _find_maker_fill_index(
    ordered: Sequence[Dict[str, Any]],
    signal_index: int,
    side: str,
    quote_price: Decimal,
    config: ExecutionReplayConfig,
) -> Optional[int]:
    signal_time = ordered[signal_index].get("observed_at")
    if signal_time is None:
        return None
    max_wait_until = signal_time + timedelta(minutes=float(config.max_quote_wait_minutes))
    start_index = signal_index if config.fill_assumption == "optimistic" else signal_index + 1
    for index in range(start_index, len(ordered)):
        snapshot = ordered[index]
        observed_at = snapshot.get("observed_at")
        if observed_at is None or observed_at > max_wait_until:
            return None
        ask = _entry_ask(snapshot, side)
        if ask is None or ask > quote_price:
            continue
        if config.fill_assumption != "strict":
            return index
        next_index = index + 1
        if next_index < len(ordered):
            next_ask = _entry_ask(ordered[next_index], side)
            next_time = ordered[next_index].get("observed_at")
            if next_time is not None and next_time <= max_wait_until and next_ask is not None and next_ask <= quote_price:
                return next_index
    return None


def _eligible_entry(
    snapshot: Dict[str, Any],
    side: str,
    config: ExecutionReplayConfig,
    mode: str,
) -> bool:
    if snapshot.get("market_classification") != "tradable":
        return False
    if side not in ("UP", "DOWN"):
        return False
    if not _model_allowed(snapshot, config):
        return False
    if snapshot.get("model_confidence", "") not in config.allowed_model_confidence:
        return False
    if snapshot.get("gamma_risk", "") not in config.allowed_gamma_risk:
        return False
    entry_edge = _mode_entry_edge(snapshot, side, mode)
    if entry_edge is None or entry_edge < config.min_edge:
        return False
    if _minutes_to_forced_exit(snapshot) < config.min_time_to_expiry_minutes:
        return False
    spread = _side_spread(snapshot, side)
    return spread is not None and spread <= config.max_spread


def _mode_entry_edge(snapshot: Dict[str, Any], side: str, mode: str) -> Optional[Decimal]:
    if mode == "maker_first":
        if side == "UP":
            return snapshot.get("maker_edge_up")
        if side == "DOWN":
            return snapshot.get("maker_edge_down")
        return None
    return _entry_edge(snapshot, side)


def _execution_trade_from_values(
    mode: str,
    fill_assumption: str,
    entry_snapshot: Dict[str, Any],
    side: str,
    entry_signal_time: datetime,
    entry_time: datetime,
    exit_time: datetime,
    exit_reason: str,
    quote_price: Optional[Decimal],
    entry_price: Decimal,
    exit_price: Decimal,
    best_available_move: Decimal,
    worst_available_move: Decimal,
    entry_net_edge: Decimal,
) -> ExecutionTrade:
    holding_minutes = Decimal(str((exit_time - entry_time).total_seconds() / 60))
    return ExecutionTrade(
        mode=mode,
        fill_assumption=fill_assumption,
        market_slug=entry_snapshot.get("market_slug", ""),
        signal_window_id=entry_snapshot.get("signal_window_id", ""),
        side=side,
        model_version=entry_snapshot.get("model_version", ""),
        entry_signal_time=entry_signal_time,
        entry_time=entry_time,
        exit_time=exit_time,
        exit_reason=exit_reason,
        quote_price=quote_price,
        entry_price=entry_price,
        exit_price=exit_price,
        realized_move=exit_price - entry_price,
        best_available_move=best_available_move,
        worst_available_move=worst_available_move,
        holding_minutes=holding_minutes,
        entry_net_edge=entry_net_edge,
        entry_fair=_side_fair(entry_snapshot, side),
        gamma_risk=entry_snapshot.get("gamma_risk", ""),
        model_confidence=entry_snapshot.get("model_confidence", ""),
        time_to_expiry_bucket=_time_to_expiry_bucket(entry_snapshot),
        moneyness_bucket=_moneyness_bucket(entry_snapshot),
        edge_bucket=_edge_bucket(entry_net_edge),
        spread_bucket=_spread_bucket(_side_spread(entry_snapshot, side)),
    )


def _group_market_snapshots(snapshots: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.get("market_slug", ""), []).append(snapshot)
    return grouped


def _ordered_snapshots(snapshots: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        snapshots,
        key=lambda item: (item.get("observed_at") or datetime.min.replace(tzinfo=UTC), item.get("signal_window_id", "")),
    )


def _first_snapshot_at_or_after(
    snapshots: Sequence[Dict[str, Any]],
    start_index: int,
    target_time: datetime,
) -> Optional[Dict[str, Any]]:
    for index in range(start_index, len(snapshots)):
        observed_at = snapshots[index].get("observed_at")
        if observed_at is not None and observed_at >= target_time:
            return snapshots[index]
    return None


def _snapshots_until(
    snapshots: Sequence[Dict[str, Any]],
    start_index: int,
    end_time: datetime,
) -> List[Dict[str, Any]]:
    values = []
    for index in range(start_index, len(snapshots)):
        observed_at = snapshots[index].get("observed_at")
        if observed_at is None:
            continue
        if observed_at > end_time:
            break
        values.append(snapshots[index])
    return values


def _first_index_at_or_after(
    snapshots: Sequence[Dict[str, Any]],
    start_index: int,
    target_time: datetime,
) -> int:
    for index in range(start_index, len(snapshots)):
        observed_at = snapshots[index].get("observed_at")
        if observed_at is not None and observed_at >= target_time:
            return index
    return len(snapshots)


def _model_allowed(snapshot: Dict[str, Any], config: ExecutionReplayConfig) -> bool:
    if not config.model_version:
        return True
    return snapshot.get("model_version", "") == config.model_version


def _side_fair(snapshot: Optional[Dict[str, Any]], side: str) -> Optional[Decimal]:
    if snapshot is None:
        return None
    if side == "UP":
        fair = snapshot.get("fair_value_up")
        return fair if fair is not None else snapshot.get("binance_signal_value")
    if side == "DOWN":
        fair = snapshot.get("fair_value_down")
        if fair is not None:
            return fair
        signal = snapshot.get("binance_signal_value")
        return ONE - signal if signal is not None else None
    return None


def _side_spread(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    ask = _entry_ask(snapshot, side)
    bid = _exit_bid(snapshot, side)
    if ask is None or bid is None:
        return None
    return max(ask - bid, ZERO)


def _minutes_to_forced_exit(snapshot: Dict[str, Any]) -> Decimal:
    observed_at = snapshot.get("observed_at")
    forced_exit = snapshot.get("forced_exit_time")
    if observed_at is None or forced_exit is None:
        return Decimal("999999")
    return Decimal(str((forced_exit - observed_at).total_seconds() / 60))


def _time_to_expiry_bucket(snapshot: Dict[str, Any]) -> str:
    minutes = _minutes_to_forced_exit(snapshot)
    if minutes < Decimal("60"):
        return "<1h"
    if minutes < Decimal("180"):
        return "1-3h"
    if minutes < Decimal("360"):
        return "3-6h"
    return ">6h"


def _moneyness_bucket(snapshot: Dict[str, Any]) -> str:
    spot = snapshot.get("current_spot_price")
    reference = snapshot.get("reference_price")
    if spot is None or reference in (None, ZERO):
        return "unknown"
    distance = abs((spot - reference) / reference)
    if distance < Decimal("0.001"):
        return "at-strike"
    if distance < Decimal("0.005"):
        return "near"
    return "far"


def _edge_bucket(edge: Decimal) -> str:
    if edge < Decimal("0.02"):
        return "<2c"
    if edge < Decimal("0.03"):
        return "2-3c"
    if edge < Decimal("0.05"):
        return "3-5c"
    if edge < Decimal("0.10"):
        return "5-10c"
    return ">=10c"


def _spread_bucket(spread: Optional[Decimal]) -> str:
    if spread is None:
        return "unknown"
    if spread < Decimal("0.01"):
        return "<1c"
    if spread < Decimal("0.03"):
        return "1-3c"
    if spread < Decimal("0.05"):
        return "3-5c"
    return ">=5c"


def _settlement_outcome(snapshot: Dict[str, Any]) -> str:
    payload = snapshot.get("payload", {})
    for key in ("settlement_outcome", "resolution", "outcome"):
        value = payload.get(key)
        if isinstance(value, str) and value.upper() in ("UP", "DOWN"):
            return value.upper()
    return "unknown"


def _settlement_source(snapshot: Dict[str, Any]) -> str:
    return "payload" if _settlement_outcome(snapshot) != "unknown" else "unavailable"


def _diagnostic_coverage(diagnostics: Sequence[FutureDiagnostics]) -> Dict[str, Any]:
    if not diagnostics:
        return {"with_30s": 0, "with_2m": 0, "with_5m": 0}
    return {
        "with_30s": sum(1 for item in diagnostics if item.edge_after_30s is not None),
        "with_2m": sum(1 for item in diagnostics if item.edge_after_2m is not None),
        "with_5m": sum(1 for item in diagnostics if item.edge_after_5m is not None),
    }


def _max_decimal(values: Iterable[Optional[Decimal]]) -> Optional[Decimal]:
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def _min_decimal(values: Iterable[Optional[Decimal]]) -> Optional[Decimal]:
    filtered = [value for value in values if value is not None]
    return min(filtered) if filtered else None


def _avg_optional_decimal(values: Iterable[Optional[Decimal]]) -> Optional[float]:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return float(sum(filtered, ZERO) / Decimal(str(len(filtered))))


def _bool_ratio(values: Iterable[bool]) -> float:
    collected = list(values)
    if not collected:
        return 0.0
    return sum(1 for value in collected if value) / len(collected)


def _optional_bool_ratio(values: Iterable[Optional[bool]]) -> Optional[float]:
    collected = [value for value in values if value is not None]
    if not collected:
        return None
    return sum(1 for value in collected if value) / len(collected)


def _decimal_difference(left: Optional[Decimal], right: Optional[Decimal]) -> Optional[Decimal]:
    if left is None or right is None:
        return None
    return left - right


def _clamp_probability(value: Decimal) -> Decimal:
    return min(max(value, ZERO), ONE)


def _serializable_trade(trade: ExecutionTrade) -> Dict[str, Any]:
    payload = asdict(trade)
    for key, value in list(payload.items()):
        if isinstance(value, Decimal):
            payload[key] = str(value)
        elif isinstance(value, datetime):
            payload[key] = value.isoformat()
    return payload


def _serializable_diagnostic(diagnostic: FutureDiagnostics) -> Dict[str, Any]:
    payload = asdict(diagnostic)
    for key, value in list(payload.items()):
        if isinstance(value, Decimal):
            payload[key] = str(value)
        elif isinstance(value, datetime):
            payload[key] = value.isoformat()
    return payload


def execution_diagnostics_as_dicts(diagnostics: Sequence[FutureDiagnostics]) -> List[Dict[str, Any]]:
    return [_serializable_diagnostic(diagnostic) for diagnostic in diagnostics]
