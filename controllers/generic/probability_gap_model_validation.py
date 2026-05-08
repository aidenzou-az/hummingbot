import json
import math
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from controllers.generic.probability_gap_sampling import ONE, ZERO, _entry_ask, _exit_bid


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
POLYMARKET_GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
DEFAULT_SETTLEMENT_CACHE_PATH = ".yxg/data/probability_gap_settlements.json"
EPSILON = Decimal("1e-9")


@dataclass(frozen=True)
class SettlementLabel:
    market_slug: str
    outcome: Optional[str]
    source: str
    confidence: str
    resolved_at: Optional[datetime]
    reason: str


def fetch_gamma_markets_by_slug(
    slugs: Iterable[str],
    timeout_seconds: int = 20,
    retry_count: int = 3,
    backoff_seconds: float = 0.5,
) -> Dict[str, Dict[str, Any]]:
    markets: Dict[str, Dict[str, Any]] = {}
    for slug in sorted(set(slugs)):
        url = f"{POLYMARKET_GAMMA_MARKETS_URL}?{urllib.parse.urlencode({'slug': slug})}"
        payload, _ = _urlopen_json_with_retry(url, timeout_seconds, retry_count, backoff_seconds)
        if payload is None:
            continue
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            markets[slug] = payload[0]
    return markets


def build_settlement_labels(
    snapshots: Sequence[Dict[str, Any]],
    official_markets_by_slug: Optional[Dict[str, Dict[str, Any]]] = None,
    binance_settlements_by_slug: Optional[Dict[str, Dict[str, Any]]] = None,
    proxy_window_seconds: int = 60,
) -> Dict[str, SettlementLabel]:
    official_markets_by_slug = official_markets_by_slug or {}
    binance_settlements_by_slug = binance_settlements_by_slug or {}
    labels = {}
    for market_slug, market_snapshots in _group_market_snapshots(snapshots).items():
        official = extract_official_settlement(market_slug, official_markets_by_slug.get(market_slug))
        if official.source != "unavailable":
            labels[market_slug] = official
            continue
        binance_rule = extract_binance_rule_settlement(market_slug, binance_settlements_by_slug.get(market_slug))
        if binance_rule.source != "unavailable":
            labels[market_slug] = binance_rule
            continue
        labels[market_slug] = infer_proxy_settlement(market_slug, market_snapshots, proxy_window_seconds)
    return labels


def extract_official_settlement(market_slug: str, market: Optional[Dict[str, Any]]) -> SettlementLabel:
    if not market:
        return SettlementLabel(market_slug, None, "unavailable", "none", None, "missing_official_market")

    for field in ("resolvedOutcome", "winningOutcome", "winner", "finalAnswer"):
        outcome = _normalize_outcome(market.get(field))
        if outcome is not None:
            return SettlementLabel(market_slug, outcome, f"official_gamma_{field}", "high", _parse_resolved_at(market), "explicit_outcome_field")

    closed = bool(market.get("closed") or market.get("archived"))
    outcomes = [str(item).upper() for item in _parse_json_list_field(market.get("outcomes"))]
    outcome_prices = [_safe_decimal(item) for item in _parse_json_list_field(market.get("outcomePrices"))]
    if closed and outcomes == ["UP", "DOWN"] and len(outcome_prices) == 2:
        up_price, down_price = outcome_prices
        if up_price is not None and down_price is not None:
            if up_price >= Decimal("0.99") and down_price <= Decimal("0.01"):
                return SettlementLabel(market_slug, "UP", "official_gamma_prices", "high", _parse_resolved_at(market), "closed_binary_prices")
            if down_price >= Decimal("0.99") and up_price <= Decimal("0.01"):
                return SettlementLabel(market_slug, "DOWN", "official_gamma_prices", "high", _parse_resolved_at(market), "closed_binary_prices")

    return SettlementLabel(market_slug, None, "unavailable", "none", _parse_resolved_at(market), "no_official_outcome_field")


def fetch_binance_rule_settlements(
    snapshots: Sequence[Dict[str, Any]],
    timeout_seconds: int = 20,
    now: Optional[datetime] = None,
    cache_path: Optional[str] = DEFAULT_SETTLEMENT_CACHE_PATH,
    retry_count: int = 3,
    backoff_seconds: float = 0.5,
) -> Dict[str, Dict[str, Any]]:
    cached_settlements = load_settlement_cache(cache_path) if cache_path else {}
    settlements: Dict[str, Dict[str, Any]] = {
        slug: settlement
        for slug, settlement in cached_settlements.items()
        if slug in _group_market_snapshots(snapshots)
    }
    cache_changed = False
    now = now or datetime.now(tz=UTC)
    for market_slug, market_snapshots in _group_market_snapshots(snapshots).items():
        if market_slug in settlements and _normalize_outcome(settlements[market_slug].get("outcome")) is not None:
            continue
        rule_input = _binance_rule_input(market_snapshots)
        if rule_input is None:
            continue
        reference_price, settlement_time = rule_input
        if settlement_time > now:
            continue
        settlement_close, fetch_error = fetch_binance_1m_close_result(
            settlement_time,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            backoff_seconds=backoff_seconds,
        )
        if settlement_close is None:
            settlements[market_slug] = {
                "outcome": None,
                "reference_price": str(reference_price),
                "settlement_time": settlement_time.isoformat(),
                "fetch_error": fetch_error or "missing_binance_kline_close",
            }
            continue
        settlements[market_slug] = {
            "outcome": "UP" if settlement_close > reference_price else "DOWN",
            "reference_price": str(reference_price),
            "settlement_close": str(settlement_close),
            "settlement_time": settlement_time.isoformat(),
            "tie_rule": "DOWN_ON_TIE",
        }
        cached_settlements[market_slug] = settlements[market_slug]
        cache_changed = True
    if cache_path and cache_changed:
        save_settlement_cache(cache_path, cached_settlements)
    return settlements


def fetch_binance_1m_close(
    settlement_time: datetime,
    timeout_seconds: int = 20,
    retry_count: int = 3,
    backoff_seconds: float = 0.5,
) -> Optional[Decimal]:
    close, _ = fetch_binance_1m_close_result(settlement_time, timeout_seconds, retry_count, backoff_seconds)
    return close


def fetch_binance_1m_close_result(
    settlement_time: datetime,
    timeout_seconds: int = 20,
    retry_count: int = 3,
    backoff_seconds: float = 0.5,
) -> Tuple[Optional[Decimal], Optional[str]]:
    settlement_time = _ensure_utc(settlement_time)
    start_ms = int(settlement_time.timestamp() * 1000)
    params = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "startTime": start_ms,
        "endTime": start_ms + 60_000,
        "limit": 1,
    }
    url = f"{BINANCE_SPOT_KLINES_URL}?{urllib.parse.urlencode(params)}"
    payload, error = _urlopen_json_with_retry(url, timeout_seconds, retry_count, backoff_seconds)
    if payload is None:
        return None, error
    if not isinstance(payload, list) or not payload:
        return None, "empty_binance_kline_response"
    first_kline = payload[0]
    if not isinstance(first_kline, list) or len(first_kline) < 5:
        return None, "malformed_binance_kline_response"
    close = _safe_decimal(first_kline[4])
    if close is None:
        return None, "invalid_binance_kline_close"
    return close, None


def extract_binance_rule_settlement(
    market_slug: str,
    settlement: Optional[Dict[str, Any]],
) -> SettlementLabel:
    if not settlement:
        return SettlementLabel(market_slug, None, "unavailable", "none", None, "missing_binance_rule_settlement")
    outcome = _normalize_outcome(settlement.get("outcome"))
    if outcome is None:
        fetch_error = settlement.get("fetch_error")
        if fetch_error:
            return SettlementLabel(
                market_slug,
                None,
                "binance_rule_fetch_failed",
                "none",
                _parse_datetime(settlement.get("settlement_time")),
                str(fetch_error),
            )
        return SettlementLabel(market_slug, None, "unavailable", "none", None, "invalid_binance_rule_outcome")
    resolved_at = _parse_datetime(settlement.get("settlement_time"))
    reference_price = settlement.get("reference_price")
    settlement_close = settlement.get("settlement_close")
    return SettlementLabel(
        market_slug,
        outcome,
        "binance_rule_1m_close",
        "high",
        resolved_at,
        f"btc_1d_rule_settlement_close={settlement_close};reference_price={reference_price};tie_rule=DOWN_ON_TIE",
    )


def load_settlement_cache(cache_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not cache_path:
        return {}
    path = Path(cache_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("settlements"), dict):
        return {
            str(slug): settlement
            for slug, settlement in payload["settlements"].items()
            if isinstance(settlement, dict)
        }
    if isinstance(payload, dict):
        return {
            str(slug): settlement
            for slug, settlement in payload.items()
            if isinstance(settlement, dict)
        }
    return {}


def save_settlement_cache(cache_path: str, settlements: Dict[str, Dict[str, Any]]) -> None:
    path = Path(cache_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(tz=UTC).isoformat(),
        "settlements": dict(sorted(settlements.items())),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def infer_proxy_settlement(
    market_slug: str,
    market_snapshots: Sequence[Dict[str, Any]],
    proxy_window_seconds: int = 60,
) -> SettlementLabel:
    candidates = [
        snapshot for snapshot in market_snapshots
        if snapshot.get("observed_at") is not None and _snapshot_market_end_time(snapshot) is not None
    ]
    if not candidates:
        return SettlementLabel(market_slug, None, "unavailable", "none", None, "missing_market_end_or_observed_at")
    closest = min(
        candidates,
        key=lambda snapshot: abs((snapshot["observed_at"] - _snapshot_market_end_time(snapshot)).total_seconds()),
    )
    market_end_time = _snapshot_market_end_time(closest)
    seconds_from_end = abs((closest["observed_at"] - market_end_time).total_seconds())
    if seconds_from_end > proxy_window_seconds:
        return SettlementLabel(market_slug, None, "unavailable", "none", closest.get("observed_at"), "no_snapshot_near_market_end")
    spot = closest.get("current_spot_price")
    reference = closest.get("reference_price")
    if spot is None or reference is None:
        return SettlementLabel(market_slug, None, "unavailable", "none", closest.get("observed_at"), "missing_spot_or_reference")
    outcome = "UP" if spot > reference else "DOWN"
    confidence = "medium" if seconds_from_end <= 60 else "low"
    return SettlementLabel(
        market_slug,
        outcome,
        "proxy_near_market_end",
        confidence,
        closest.get("observed_at"),
        f"spot_reference_proxy_seconds_from_market_end={seconds_from_end:.3f}",
    )


def run_model_validation(
    snapshots: Sequence[Dict[str, Any]],
    official_markets_by_slug: Optional[Dict[str, Dict[str, Any]]] = None,
    binance_settlements_by_slug: Optional[Dict[str, Dict[str, Any]]] = None,
    proxy_window_seconds: int = 60,
) -> Dict[str, Any]:
    labels = build_settlement_labels(
        snapshots,
        official_markets_by_slug=official_markets_by_slug,
        binance_settlements_by_slug=binance_settlements_by_slug,
        proxy_window_seconds=proxy_window_seconds,
    )
    entries = build_model_validation_entries(snapshots, labels)
    by_source = {}
    for source in sorted({label.source for label in labels.values()}):
        source_entries = [entry for entry in entries if entry["settlement_source"] == source]
        by_source[source] = {
            "n_entries": len(source_entries),
            "calibration": calibration_report(source_entries),
            "a_edge_truth_table": truth_table(source_entries, "a_edge"),
            "a_residual_truth_table": truth_table(source_entries, "a_residual"),
            "closeout_vs_settlement": closeout_vs_settlement_report(source_entries),
        }
    return {
        "settlement_coverage": settlement_coverage(labels),
        "settlement_labels": {slug: _serializable_label(label) for slug, label in sorted(labels.items())},
        "entries_count": len(entries),
        "by_source": by_source,
    }


def build_model_validation_entries(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
) -> List[Dict[str, Any]]:
    grouped = _group_market_snapshots(snapshots)
    entries: List[Dict[str, Any]] = []
    for market_slug, market_snapshots in grouped.items():
        label = labels.get(market_slug)
        if label is None or label.outcome is None:
            continue
        ordered = sorted(market_snapshots, key=lambda item: (item.get("observed_at"), item.get("signal_window_id", "")))
        for index, snapshot in enumerate(ordered):
            if snapshot.get("market_classification") != "tradable":
                continue
            side = snapshot.get("best_side", "")
            if side not in ("UP", "DOWN"):
                continue
            ask = _entry_ask(snapshot, side)
            fair = _side_fair(snapshot, side)
            mid = _side_mid(snapshot, side)
            if ask is None or fair is None or mid is None:
                continue
            settlement_price = ONE if side == label.outcome else ZERO
            entries.append(
                {
                    "market_slug": market_slug,
                    "observed_at": snapshot.get("observed_at"),
                    "side": side,
                    "outcome": label.outcome,
                    "settlement_source": label.source,
                    "settlement_confidence": label.confidence,
                    "fair_up": snapshot.get("fair_value_up"),
                    "side_fair": fair,
                    "entry_ask": ask,
                    "side_mid": mid,
                    "a_edge": fair - ask,
                    "a_residual": fair - mid,
                    "settlement_pnl": settlement_price - ask,
                    "settlement_win": side == label.outcome,
                    "ret_5m": _future_return(ordered, index, side, ask, 300),
                    "ret_20m": _future_return(ordered, index, side, ask, 1200),
                    "gamma_risk": snapshot.get("gamma_risk", ""),
                    "model_confidence": snapshot.get("model_confidence", ""),
                    "time_to_expiry_bucket": _time_to_expiry_bucket(snapshot),
                    "spread_bucket": _spread_bucket(_side_spread(snapshot, side)),
                }
            )
    return entries


def calibration_report(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    values = [
        (entry.get("fair_up"), ONE if entry["outcome"] == "UP" else ZERO)
        for entry in entries
        if entry.get("fair_up") is not None
    ]
    if not values:
        return {"n": 0, "brier": None, "log_loss": None, "buckets": []}
    brier = sum(((prob - actual) ** 2 for prob, actual in values), ZERO) / Decimal(str(len(values)))
    log_loss = sum((_log_loss(prob, actual) for prob, actual in values), ZERO) / Decimal(str(len(values)))
    buckets: Dict[str, List[Tuple[Decimal, Decimal]]] = defaultdict(list)
    for prob, actual in values:
        buckets[_probability_bucket(prob)].append((prob, actual))
    return {
        "n": len(values),
        "brier": float(brier),
        "log_loss": float(log_loss),
        "buckets": [
            {
                "bucket": bucket,
                "n": len(bucket_values),
                "avg_probability": float(sum((prob for prob, _ in bucket_values), ZERO) / Decimal(str(len(bucket_values)))),
                "actual_up_rate": float(sum((actual for _, actual in bucket_values), ZERO) / Decimal(str(len(bucket_values)))),
            }
            for bucket, bucket_values in sorted(buckets.items())
        ],
    }


def truth_table(entries: Sequence[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    buckets: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        value = entry.get(field)
        if value is None:
            continue
        key = (
            _edge_bucket(value),
            entry.get("gamma_risk", ""),
            entry.get("time_to_expiry_bucket", ""),
            entry.get("model_confidence", ""),
        )
        buckets[key].append(entry)
    rows = []
    for (bucket, gamma, time_to_expiry, confidence), bucket_entries in sorted(buckets.items()):
        settlement_pnls = [entry["settlement_pnl"] for entry in bucket_entries]
        rows.append(
            {
                "bucket": bucket,
                "gamma_risk": gamma,
                "time_to_expiry_bucket": time_to_expiry,
                "model_confidence": confidence,
                "n": len(bucket_entries),
                "avg_signal": float(sum((entry[field] for entry in bucket_entries), ZERO) / Decimal(str(len(bucket_entries)))),
                "avg_settlement_pnl": float(sum(settlement_pnls, ZERO) / Decimal(str(len(settlement_pnls)))),
                "settlement_win_rate": sum(1 for entry in bucket_entries if entry["settlement_win"]) / len(bucket_entries),
                "positive_pnl_rate": sum(1 for pnl in settlement_pnls if pnl > ZERO) / len(settlement_pnls),
            }
        )
    return rows


def closeout_vs_settlement_report(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    report = {}
    for field in ("ret_5m", "ret_20m"):
        values = [
            (entry[field], entry["settlement_pnl"])
            for entry in entries
            if entry.get(field) is not None
        ]
        if not values:
            report[field] = {"n": 0, "avg_closeout": None, "avg_settlement": None, "same_sign_rate": None}
            continue
        report[field] = {
            "n": len(values),
            "avg_closeout": float(sum((closeout for closeout, _ in values), ZERO) / Decimal(str(len(values)))),
            "avg_settlement": float(sum((settlement for _, settlement in values), ZERO) / Decimal(str(len(values)))),
            "same_sign_rate": sum(1 for closeout, settlement in values if _same_sign(closeout, settlement)) / len(values),
        }
    return report


def settlement_coverage(labels: Dict[str, SettlementLabel]) -> Dict[str, Any]:
    counts: Dict[str, int] = defaultdict(int)
    for label in labels.values():
        counts[label.source] += 1
    return {
        "markets": len(labels),
        "by_source": dict(sorted(counts.items())),
        "official_markets": sum(count for source, count in counts.items() if source.startswith("official")),
        "binance_rule_markets": sum(count for source, count in counts.items() if source.startswith("binance_rule")),
        "proxy_markets": sum(count for source, count in counts.items() if source.startswith("proxy")),
        "unavailable_markets": counts.get("unavailable", 0),
    }


def _future_return(ordered: Sequence[Dict[str, Any]], index: int, side: str, entry_price: Decimal, horizon_seconds: int) -> Optional[Decimal]:
    observed_at = ordered[index].get("observed_at")
    if observed_at is None:
        return None
    target = observed_at.timestamp() + horizon_seconds
    for future in ordered[index + 1:]:
        future_time = future.get("observed_at")
        if future_time is not None and future_time.timestamp() >= target:
            bid = _exit_bid(future, side)
            return bid - entry_price if bid is not None else None
    return None


def _side_fair(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    if side == "UP":
        return snapshot.get("fair_value_up")
    if side == "DOWN":
        return snapshot.get("fair_value_down")
    return None


def _side_mid(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    up_bid = snapshot.get("up_best_bid")
    up_ask = snapshot.get("up_best_ask")
    if up_bid is None or up_ask is None:
        return None
    up_mid = (up_bid + up_ask) / Decimal("2")
    return up_mid if side == "UP" else ONE - up_mid


def _side_spread(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    ask = _entry_ask(snapshot, side)
    bid = _exit_bid(snapshot, side)
    if ask is None or bid is None:
        return None
    return max(ask - bid, ZERO)


def _time_to_expiry_bucket(snapshot: Dict[str, Any]) -> str:
    observed_at = snapshot.get("observed_at")
    market_end = _snapshot_market_end_time(snapshot)
    if observed_at is None or market_end is None:
        return "unknown"
    minutes = Decimal(str((market_end - observed_at).total_seconds() / 60))
    if minutes < Decimal("60"):
        return "<1h"
    if minutes < Decimal("180"):
        return "1-3h"
    if minutes < Decimal("360"):
        return "3-6h"
    return ">6h"


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


def _edge_bucket(edge: Decimal) -> str:
    if edge < ZERO:
        return "<0"
    if edge < Decimal("0.02"):
        return "0-2c"
    if edge < Decimal("0.03"):
        return "2-3c"
    if edge < Decimal("0.05"):
        return "3-5c"
    if edge < Decimal("0.08"):
        return "5-8c"
    if edge < Decimal("0.10"):
        return "8-10c"
    return ">=10c"


def _probability_bucket(probability: Decimal) -> str:
    index = int(max(0, min(9, math.floor(float(probability) * 10))))
    return f"{index * 10}-{(index + 1) * 10}%"


def _log_loss(probability: Decimal, actual: Decimal) -> Decimal:
    p = min(max(probability, EPSILON), ONE - EPSILON)
    value = -(actual * Decimal(str(math.log(float(p)))) + (ONE - actual) * Decimal(str(math.log(float(ONE - p)))))
    return value


def _same_sign(left: Decimal, right: Decimal) -> bool:
    if left == ZERO and right == ZERO:
        return True
    return (left > ZERO and right > ZERO) or (left < ZERO and right < ZERO)


def _parse_resolved_at(market: Dict[str, Any]) -> Optional[datetime]:
    for field in ("resolvedAt", "closedTime", "endDate", "endDateIso"):
        raw_value = market.get(field)
        if isinstance(raw_value, str):
            parsed = _parse_datetime(raw_value)
            if parsed is not None:
                return parsed
    return None


def _urlopen_json_with_retry(
    url: str,
    timeout_seconds: int,
    retry_count: int,
    backoff_seconds: float,
) -> Tuple[Optional[Any], Optional[str]]:
    last_error: Optional[str] = None
    attempts = max(1, retry_count)
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.load(response), None
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts - 1:
                time.sleep(backoff_seconds * (2 ** attempt))
    return None, last_error


def _parse_json_list_field(raw_value: Any) -> List[Any]:
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, str):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []
    return []


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _normalize_outcome(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized in ("UP", "YES", "TRUE"):
        return "UP"
    if normalized in ("DOWN", "NO", "FALSE"):
        return "DOWN"
    return None


def _group_market_snapshots(snapshots: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.get("market_slug", "")].append(snapshot)
    return grouped


def _binance_rule_input(market_snapshots: Sequence[Dict[str, Any]]) -> Optional[Tuple[Decimal, datetime]]:
    candidates = sorted(
        market_snapshots,
        key=lambda item: item.get("observed_at") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    for snapshot in candidates:
        reference_price = _safe_decimal(snapshot.get("reference_price"))
        if reference_price is None:
            reference_price = _safe_decimal((snapshot.get("payload") or {}).get("reference_price"))
        settlement_time = _snapshot_market_end_time(snapshot)
        if reference_price is not None and settlement_time is not None:
            return reference_price, settlement_time
    return None


def _snapshot_market_end_time(snapshot: Dict[str, Any]) -> Optional[datetime]:
    payload = snapshot.get("payload") or {}
    if isinstance(payload, dict):
        parsed = _parse_datetime(payload.get("market_end_time"))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(raw_value: Any) -> Optional[datetime]:
    if not isinstance(raw_value, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _ensure_utc(parsed)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _serializable_label(label: SettlementLabel) -> Dict[str, Any]:
    payload = asdict(label)
    if label.resolved_at is not None:
        payload["resolved_at"] = label.resolved_at.isoformat()
    return payload
