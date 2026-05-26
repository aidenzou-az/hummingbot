import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


ZERO = Decimal("0")
ONE = Decimal("1")


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _serialize_payload(payload: Dict[str, Any]) -> str:
    def convert(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: convert(inner_value) for key, inner_value in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    return json.dumps(convert(payload), sort_keys=True)


@dataclass(frozen=True)
class ReplayTrade:
    market_slug: str
    signal_window_id: str
    side: str
    entry_time: datetime
    exit_time: datetime
    exit_reason: str
    entry_price: Decimal
    exit_price: Decimal
    realized_move: Decimal
    best_available_move: Decimal
    worst_available_move: Decimal
    holding_minutes: Decimal
    entry_net_edge: Decimal
    final_net_edge: Decimal


class ProbabilityGapSnapshotStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS probability_gap_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at TEXT NOT NULL,
                    market_slug TEXT NOT NULL,
                    signal_window_id TEXT NOT NULL,
                    market_classification TEXT NOT NULL,
                    classification_reason TEXT NOT NULL,
                    best_side TEXT,
                    best_net_edge TEXT,
                    net_edge_up TEXT,
                    net_edge_down TEXT,
                    binance_signal_value TEXT,
                    binance_signal_kind TEXT,
                    model_version TEXT,
                    fair_value_up TEXT,
                    fair_value_down TEXT,
                    option_iv TEXT,
                    tau_years TEXT,
                    d2 TEXT,
                    prob_delta TEXT,
                    gamma_risk TEXT,
                    model_confidence TEXT,
                    risk_free_rate TEXT,
                    expiry_mismatch_minutes TEXT,
                    lower_iv TEXT,
                    upper_iv TEXT,
                    interpolated_option_iv TEXT,
                    polymarket_taker_fee_rate TEXT,
                    polymarket_taker_fee_up TEXT,
                    polymarket_taker_fee_down TEXT,
                    maker_edge_up TEXT,
                    maker_edge_down TEXT,
                    taker_edge_up TEXT,
                    taker_edge_down TEXT,
                    current_spot_price TEXT,
                    reference_price TEXT,
                    forward_source TEXT,
                    estimated_forward_price TEXT,
                    basis_annualized TEXT,
                    perp_mark_price TEXT,
                    perp_index_price TEXT,
                    perp_last_funding_rate TEXT,
                    perp_next_funding_time TEXT,
                    delivery_symbol TEXT,
                    delivery_price TEXT,
                    forward_basis_reason TEXT,
                    option_chain_slice_json TEXT,
                    option_chain_slice_count TEXT,
                    option_chain_slice_source TEXT,
                    option_chain_slice_expiry TEXT,
                    option_chain_horizon_mismatch_minutes TEXT,
                    smile_call_spread_probability TEXT,
                    smile_call_spread_status TEXT,
                    smile_call_spread_reason TEXT,
                    up_best_bid TEXT,
                    up_best_ask TEXT,
                    down_best_bid TEXT,
                    down_best_ask TEXT,
                    selected_option_expiry TEXT,
                    forced_exit_time TEXT,
                    snapshot_reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(probability_gap_snapshots)").fetchall()
            }
            for column_name in [
                "model_version",
                "fair_value_up",
                "fair_value_down",
                "option_iv",
                "tau_years",
                "d2",
                "prob_delta",
                "gamma_risk",
                "model_confidence",
                "risk_free_rate",
                "expiry_mismatch_minutes",
                "lower_iv",
                "upper_iv",
                "interpolated_option_iv",
                "polymarket_taker_fee_rate",
                "polymarket_taker_fee_up",
                "polymarket_taker_fee_down",
                "maker_edge_up",
                "maker_edge_down",
                "taker_edge_up",
                "taker_edge_down",
                "forward_source",
                "estimated_forward_price",
                "basis_annualized",
                "perp_mark_price",
                "perp_index_price",
                "perp_last_funding_rate",
                "perp_next_funding_time",
                "delivery_symbol",
                "delivery_price",
                "forward_basis_reason",
                "option_chain_slice_json",
                "option_chain_slice_count",
                "option_chain_slice_source",
                "option_chain_slice_expiry",
                "option_chain_horizon_mismatch_minutes",
                "smile_call_spread_probability",
                "smile_call_spread_status",
                "smile_call_spread_reason",
            ]:
                if column_name not in existing_columns:
                    connection.execute(f"ALTER TABLE probability_gap_snapshots ADD COLUMN {column_name} TEXT")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_probability_gap_snapshots_slug_time
                ON probability_gap_snapshots (market_slug, observed_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_probability_gap_snapshots_signal_window
                ON probability_gap_snapshots (signal_window_id, observed_at)
                """
            )

    def record_snapshots(self, snapshots: Sequence[Dict[str, Any]]):
        if not snapshots:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO probability_gap_snapshots (
                    observed_at,
                    market_slug,
                    signal_window_id,
                    market_classification,
                    classification_reason,
                    best_side,
                    best_net_edge,
                    net_edge_up,
                    net_edge_down,
                    binance_signal_value,
                    binance_signal_kind,
                    model_version,
                    fair_value_up,
                    fair_value_down,
                    option_iv,
                    tau_years,
                    d2,
                    prob_delta,
                    gamma_risk,
                    model_confidence,
                    risk_free_rate,
                    expiry_mismatch_minutes,
                    lower_iv,
                    upper_iv,
                    interpolated_option_iv,
                    polymarket_taker_fee_rate,
                    polymarket_taker_fee_up,
                    polymarket_taker_fee_down,
                    maker_edge_up,
                    maker_edge_down,
                    taker_edge_up,
                    taker_edge_down,
                    current_spot_price,
                    reference_price,
                    forward_source,
                    estimated_forward_price,
                    basis_annualized,
                    perp_mark_price,
                    perp_index_price,
                    perp_last_funding_rate,
                    perp_next_funding_time,
                    delivery_symbol,
                    delivery_price,
                    forward_basis_reason,
                    option_chain_slice_json,
                    option_chain_slice_count,
                    option_chain_slice_source,
                    option_chain_slice_expiry,
                    option_chain_horizon_mismatch_minutes,
                    smile_call_spread_probability,
                    smile_call_spread_status,
                    smile_call_spread_reason,
                    up_best_bid,
                    up_best_ask,
                    down_best_bid,
                    down_best_ask,
                    selected_option_expiry,
                    forced_exit_time,
                    snapshot_reason,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot["observed_at"],
                        snapshot["market_slug"],
                        snapshot["signal_window_id"],
                        snapshot["market_classification"],
                        snapshot["classification_reason"],
                        snapshot.get("best_side", ""),
                        str(snapshot.get("best_net_edge", "")),
                        str(snapshot.get("net_edge_up", "")),
                        str(snapshot.get("net_edge_down", "")),
                        str(snapshot.get("binance_signal_value", "")),
                        snapshot.get("binance_signal_kind", ""),
                        snapshot.get("model_version", ""),
                        str(snapshot.get("fair_value_up", "")),
                        str(snapshot.get("fair_value_down", "")),
                        str(snapshot.get("option_iv", "")),
                        str(snapshot.get("tau_years", "")),
                        str(snapshot.get("d2", "")),
                        str(snapshot.get("prob_delta", "")),
                        snapshot.get("gamma_risk", ""),
                        snapshot.get("model_confidence", ""),
                        str(snapshot.get("risk_free_rate", "")),
                        str(snapshot.get("expiry_mismatch_minutes", "")),
                        str(snapshot.get("lower_iv", "")),
                        str(snapshot.get("upper_iv", "")),
                        str(snapshot.get("interpolated_option_iv", "")),
                        str(snapshot.get("polymarket_taker_fee_rate", "")),
                        str(snapshot.get("polymarket_taker_fee_up", "")),
                        str(snapshot.get("polymarket_taker_fee_down", "")),
                        str(snapshot.get("maker_edge_up", "")),
                        str(snapshot.get("maker_edge_down", "")),
                        str(snapshot.get("taker_edge_up", "")),
                        str(snapshot.get("taker_edge_down", "")),
                        str(snapshot.get("current_spot_price", "")),
                        str(snapshot.get("reference_price", "")),
                        snapshot.get("forward_source", ""),
                        str(snapshot.get("estimated_forward_price", "")),
                        str(snapshot.get("basis_annualized", "")),
                        str(snapshot.get("perp_mark_price", "")),
                        str(snapshot.get("perp_index_price", "")),
                        str(snapshot.get("perp_last_funding_rate", "")),
                        snapshot.get("perp_next_funding_time", ""),
                        snapshot.get("delivery_symbol", ""),
                        str(snapshot.get("delivery_price", "")),
                        snapshot.get("forward_basis_reason", ""),
                        _serialize_payload(snapshot.get("option_chain_slice", [])),
                        str(snapshot.get("option_chain_slice_count", "")),
                        snapshot.get("option_chain_slice_source", ""),
                        snapshot.get("option_chain_slice_expiry", ""),
                        str(snapshot.get("option_chain_horizon_mismatch_minutes", "")),
                        str(snapshot.get("smile_call_spread_probability", "")),
                        snapshot.get("smile_call_spread_status", ""),
                        snapshot.get("smile_call_spread_reason", ""),
                        str(snapshot.get("up_best_bid", "")),
                        str(snapshot.get("up_best_ask", "")),
                        str(snapshot.get("down_best_bid", "")),
                        str(snapshot.get("down_best_ask", "")),
                        snapshot.get("selected_option_expiry", ""),
                        snapshot.get("forced_exit_time", ""),
                        snapshot["snapshot_reason"],
                        _serialize_payload(snapshot["payload"]),
                    )
                    for snapshot in snapshots
                ],
            )

    def count_snapshots(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM probability_gap_snapshots").fetchone()
            return int(row["count"]) if row is not None else 0

    def list_snapshots(self, market_slug: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM probability_gap_snapshots"
        params: Tuple[Any, ...] = ()
        if market_slug is not None:
            query += " WHERE market_slug = ?"
            params = (market_slug,)
        query += " ORDER BY observed_at ASC, id ASC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        snapshots = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            snapshots.append(
                {
                    "observed_at": _parse_iso(row["observed_at"]),
                    "market_slug": row["market_slug"],
                    "signal_window_id": row["signal_window_id"],
                    "market_classification": row["market_classification"],
                    "classification_reason": row["classification_reason"],
                    "best_side": row["best_side"],
                    "best_net_edge": _safe_decimal(row["best_net_edge"]) or ZERO,
                    "net_edge_up": _safe_decimal(row["net_edge_up"]) or ZERO,
                    "net_edge_down": _safe_decimal(row["net_edge_down"]) or ZERO,
                    "binance_signal_value": _safe_decimal(row["binance_signal_value"]) or ZERO,
                    "binance_signal_kind": row["binance_signal_kind"],
                    "model_version": row["model_version"] if "model_version" in row.keys() else "",
                    "fair_value_up": _safe_decimal(row["fair_value_up"]) if "fair_value_up" in row.keys() else None,
                    "fair_value_down": _safe_decimal(row["fair_value_down"]) if "fair_value_down" in row.keys() else None,
                    "option_iv": _safe_decimal(row["option_iv"]) if "option_iv" in row.keys() else None,
                    "tau_years": _safe_decimal(row["tau_years"]) if "tau_years" in row.keys() else None,
                    "d2": _safe_decimal(row["d2"]) if "d2" in row.keys() else None,
                    "prob_delta": _safe_decimal(row["prob_delta"]) if "prob_delta" in row.keys() else None,
                    "gamma_risk": row["gamma_risk"] if "gamma_risk" in row.keys() else "",
                    "model_confidence": row["model_confidence"] if "model_confidence" in row.keys() else "",
                    "risk_free_rate": _safe_decimal(row["risk_free_rate"]) if "risk_free_rate" in row.keys() else None,
                    "expiry_mismatch_minutes": _safe_decimal(row["expiry_mismatch_minutes"]) if "expiry_mismatch_minutes" in row.keys() else None,
                    "lower_iv": _safe_decimal(row["lower_iv"]) if "lower_iv" in row.keys() else None,
                    "upper_iv": _safe_decimal(row["upper_iv"]) if "upper_iv" in row.keys() else None,
                    "interpolated_option_iv": _safe_decimal(row["interpolated_option_iv"]) if "interpolated_option_iv" in row.keys() else None,
                    "polymarket_taker_fee_rate": _safe_decimal(row["polymarket_taker_fee_rate"]) if "polymarket_taker_fee_rate" in row.keys() else None,
                    "polymarket_taker_fee_up": _safe_decimal(row["polymarket_taker_fee_up"]) if "polymarket_taker_fee_up" in row.keys() else None,
                    "polymarket_taker_fee_down": _safe_decimal(row["polymarket_taker_fee_down"]) if "polymarket_taker_fee_down" in row.keys() else None,
                    "maker_edge_up": _safe_decimal(row["maker_edge_up"]) if "maker_edge_up" in row.keys() else None,
                    "maker_edge_down": _safe_decimal(row["maker_edge_down"]) if "maker_edge_down" in row.keys() else None,
                    "taker_edge_up": _safe_decimal(row["taker_edge_up"]) if "taker_edge_up" in row.keys() else None,
                    "taker_edge_down": _safe_decimal(row["taker_edge_down"]) if "taker_edge_down" in row.keys() else None,
                    "current_spot_price": _safe_decimal(row["current_spot_price"]),
                    "reference_price": _safe_decimal(row["reference_price"]),
                    "forward_source": row["forward_source"] if "forward_source" in row.keys() else "",
                    "estimated_forward_price": _safe_decimal(row["estimated_forward_price"]) if "estimated_forward_price" in row.keys() else None,
                    "basis_annualized": _safe_decimal(row["basis_annualized"]) if "basis_annualized" in row.keys() else None,
                    "perp_mark_price": _safe_decimal(row["perp_mark_price"]) if "perp_mark_price" in row.keys() else None,
                    "perp_index_price": _safe_decimal(row["perp_index_price"]) if "perp_index_price" in row.keys() else None,
                    "perp_last_funding_rate": _safe_decimal(row["perp_last_funding_rate"]) if "perp_last_funding_rate" in row.keys() else None,
                    "perp_next_funding_time": _parse_iso(row["perp_next_funding_time"]) if "perp_next_funding_time" in row.keys() else None,
                    "delivery_symbol": row["delivery_symbol"] if "delivery_symbol" in row.keys() else "",
                    "delivery_price": _safe_decimal(row["delivery_price"]) if "delivery_price" in row.keys() else None,
                    "forward_basis_reason": row["forward_basis_reason"] if "forward_basis_reason" in row.keys() else "",
                    "option_chain_slice": json.loads(row["option_chain_slice_json"]) if "option_chain_slice_json" in row.keys() and row["option_chain_slice_json"] else [],
                    "option_chain_slice_count": int(row["option_chain_slice_count"]) if "option_chain_slice_count" in row.keys() and row["option_chain_slice_count"] not in (None, "") else 0,
                    "option_chain_slice_source": row["option_chain_slice_source"] if "option_chain_slice_source" in row.keys() else "",
                    "option_chain_slice_expiry": _parse_iso(row["option_chain_slice_expiry"]) if "option_chain_slice_expiry" in row.keys() else None,
                    "option_chain_horizon_mismatch_minutes": _safe_decimal(row["option_chain_horizon_mismatch_minutes"]) if "option_chain_horizon_mismatch_minutes" in row.keys() else None,
                    "smile_call_spread_probability": _safe_decimal(row["smile_call_spread_probability"]) if "smile_call_spread_probability" in row.keys() else None,
                    "smile_call_spread_status": row["smile_call_spread_status"] if "smile_call_spread_status" in row.keys() else "",
                    "smile_call_spread_reason": row["smile_call_spread_reason"] if "smile_call_spread_reason" in row.keys() else "",
                    "up_best_bid": _safe_decimal(row["up_best_bid"]),
                    "up_best_ask": _safe_decimal(row["up_best_ask"]),
                    "down_best_bid": _safe_decimal(row["down_best_bid"]),
                    "down_best_ask": _safe_decimal(row["down_best_ask"]),
                    "selected_option_expiry": _parse_iso(row["selected_option_expiry"]),
                    "forced_exit_time": _parse_iso(row["forced_exit_time"]),
                    "payload": payload,
                }
            )
        return snapshots


def choose_snapshot_reason(
    current_snapshot: Dict[str, Any],
    previous_snapshot: Optional[Dict[str, Any]],
    now: datetime,
    baseline_interval_seconds: int,
    tradable_interval_seconds: int,
    near_exit_interval_seconds: int,
    near_exit_window_minutes: int,
    min_net_edge: Decimal,
) -> Optional[str]:
    if previous_snapshot is None:
        return "initial_capture"

    previous_time = _parse_iso(previous_snapshot["observed_at"])
    if previous_time is None:
        return "initial_capture"

    elapsed_seconds = (now - previous_time).total_seconds()
    current_classification = current_snapshot["market_classification"]
    previous_classification = previous_snapshot["market_classification"]
    if current_classification != previous_classification:
        return "state_change"

    if current_snapshot["classification_reason"] != previous_snapshot["classification_reason"]:
        return "state_change"

    if current_classification == "rejected":
        return None

    if current_snapshot.get("best_side", "") != previous_snapshot.get("best_side", ""):
        return "side_flip"

    current_best_edge = _safe_decimal(current_snapshot.get("best_net_edge")) or ZERO
    previous_best_edge = _safe_decimal(previous_snapshot.get("best_net_edge")) or ZERO
    current_above = current_best_edge >= min_net_edge
    previous_above = previous_best_edge >= min_net_edge
    if current_above != previous_above:
        return "edge_threshold_cross"

    forced_exit = _parse_iso(current_snapshot.get("forced_exit_time"))
    if forced_exit is not None:
        minutes_to_exit = Decimal(str((forced_exit - now).total_seconds() / 60))
        if minutes_to_exit <= Decimal(str(near_exit_window_minutes)):
            if elapsed_seconds >= near_exit_interval_seconds:
                return "near_exit_interval"
            return None

    target_interval = baseline_interval_seconds
    if current_classification == "tradable":
        target_interval = tradable_interval_seconds
    if elapsed_seconds >= target_interval:
        return f"{current_classification}_interval"
    return None


def replay_tradable_windows(snapshots: Sequence[Dict[str, Any]], min_net_edge: Decimal) -> List[ReplayTrade]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot["market_slug"], []).append(snapshot)

    trades: List[ReplayTrade] = []
    for market_slug, market_snapshots in grouped.items():
        ordered = sorted(
            market_snapshots,
            key=lambda item: (item["observed_at"], item["signal_window_id"]),
        )
        active_trade: Optional[Dict[str, Any]] = None
        for snapshot in ordered:
            observed_at = snapshot["observed_at"]
            if observed_at is None:
                continue
            classification = snapshot["market_classification"]
            if active_trade is None:
                if classification != "tradable":
                    continue
                side = snapshot.get("best_side", "")
                entry_edge = _entry_edge(snapshot, side)
                if entry_edge is None or entry_edge < min_net_edge:
                    continue
                entry_ask = _entry_ask(snapshot, side)
                if entry_ask is None:
                    continue
                active_trade = {
                    "market_slug": market_slug,
                    "signal_window_id": snapshot["signal_window_id"],
                    "side": side,
                    "entry_time": observed_at,
                    "entry_price": entry_ask,
                    "entry_net_edge": entry_edge,
                    "best_move": ZERO,
                    "worst_move": ZERO,
                }
                continue

            exit_bid = _exit_bid(snapshot, active_trade["side"])
            if exit_bid is None:
                continue

            move = exit_bid - active_trade["entry_price"]
            active_trade["best_move"] = max(active_trade["best_move"], move)
            active_trade["worst_move"] = min(active_trade["worst_move"], move)

            final_edge = _entry_edge(snapshot, active_trade["side"]) or ZERO
            exit_reason = None
            forced_exit_time = snapshot.get("forced_exit_time")
            if forced_exit_time is not None and observed_at >= forced_exit_time:
                exit_reason = "forced_exit"
            elif classification != "tradable":
                exit_reason = "classification_change"
            elif snapshot.get("best_side", "") != active_trade["side"]:
                exit_reason = "side_flip"
            elif final_edge <= min_net_edge:
                exit_reason = "edge_decay"

            if exit_reason is None:
                continue

            holding_minutes = Decimal(str((observed_at - active_trade["entry_time"]).total_seconds() / 60))
            trades.append(
                ReplayTrade(
                    market_slug=market_slug,
                    signal_window_id=active_trade["signal_window_id"],
                    side=active_trade["side"],
                    entry_time=active_trade["entry_time"],
                    exit_time=observed_at,
                    exit_reason=exit_reason,
                    entry_price=active_trade["entry_price"],
                    exit_price=exit_bid,
                    realized_move=move,
                    best_available_move=active_trade["best_move"],
                    worst_available_move=active_trade["worst_move"],
                    holding_minutes=holding_minutes,
                    entry_net_edge=active_trade["entry_net_edge"],
                    final_net_edge=final_edge,
                )
            )
            active_trade = None

    return trades


def summarize_replays(replays: Sequence[ReplayTrade]) -> Dict[str, Any]:
    if not replays:
        return {
            "n_replays": 0,
            "positive_ratio": 0.0,
            "avg_realized_move": 0.0,
            "avg_best_available_move": 0.0,
            "avg_holding_minutes": 0.0,
        }
    realized_total = sum((trade.realized_move for trade in replays), ZERO)
    best_total = sum((trade.best_available_move for trade in replays), ZERO)
    holding_total = sum((trade.holding_minutes for trade in replays), ZERO)
    positive = sum(1 for trade in replays if trade.realized_move > ZERO)
    count = Decimal(str(len(replays)))
    return {
        "n_replays": len(replays),
        "positive_ratio": float(Decimal(str(positive)) / count),
        "avg_realized_move": float(realized_total / count),
        "avg_best_available_move": float(best_total / count),
        "avg_holding_minutes": float(holding_total / count),
    }


def _entry_ask(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    if side == "UP":
        return snapshot.get("up_best_ask")
    if side == "DOWN":
        return _complementary_down_ask(snapshot)
    return None


def _entry_edge(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    if side == "UP":
        return snapshot.get("taker_edge_up") or snapshot.get("net_edge_up")
    if side == "DOWN":
        return snapshot.get("taker_edge_down") or snapshot.get("net_edge_down")
    return None


def _exit_bid(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    if side == "UP":
        return snapshot.get("up_best_bid")
    if side == "DOWN":
        return _complementary_down_bid(snapshot)
    return None


def _complementary_down_ask(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    up_best_bid = snapshot.get("up_best_bid")
    if up_best_bid is not None:
        return max(ONE - up_best_bid, ZERO)
    return snapshot.get("down_best_ask")


def _complementary_down_bid(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    up_best_ask = snapshot.get("up_best_ask")
    if up_best_ask is not None:
        return max(ONE - up_best_ask, ZERO)
    return snapshot.get("down_best_bid")
