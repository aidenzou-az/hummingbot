import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional


ZERO = Decimal("0")
ONE = Decimal("1")
YEAR_SECONDS = Decimal("31536000")
DEFAULT_DELIVERY_MAX_DISTANCE_SECONDS = Decimal("129600")


@dataclass(frozen=True)
class ForwardBasisEstimate:
    source: str
    estimated_forward_price: Decimal
    basis_annualized: Decimal
    reason: str
    perp_mark_price: Optional[Decimal] = None
    perp_index_price: Optional[Decimal] = None
    perp_last_funding_rate: Optional[Decimal] = None
    perp_next_funding_time: Optional[datetime] = None
    delivery_symbol: str = ""
    delivery_price: Optional[Decimal] = None

    def as_payload(self) -> Dict[str, Any]:
        return {
            "forward_source": self.source,
            "estimated_forward_price": self.estimated_forward_price,
            "basis_annualized": self.basis_annualized,
            "forward_basis_reason": self.reason,
            "perp_mark_price": self.perp_mark_price if self.perp_mark_price is not None else "",
            "perp_index_price": self.perp_index_price if self.perp_index_price is not None else "",
            "perp_last_funding_rate": self.perp_last_funding_rate if self.perp_last_funding_rate is not None else "",
            "perp_next_funding_time": self.perp_next_funding_time.isoformat() if self.perp_next_funding_time is not None else "",
            "delivery_symbol": self.delivery_symbol,
            "delivery_price": self.delivery_price if self.delivery_price is not None else "",
        }


def estimate_forward_basis(
    now: datetime,
    market_end_time: datetime,
    spot_price: Decimal,
    perp_mark_price: Optional[Decimal] = None,
    perp_index_price: Optional[Decimal] = None,
    perp_last_funding_rate: Optional[Decimal] = None,
    perp_next_funding_time: Optional[datetime] = None,
    delivery_candidates: Optional[Iterable[Dict[str, Any]]] = None,
    delivery_max_distance_seconds: Decimal = DEFAULT_DELIVERY_MAX_DISTANCE_SECONDS,
) -> ForwardBasisEstimate:
    now = _to_utc(now)
    market_end_time = _to_utc(market_end_time)
    tau_seconds = Decimal(str((market_end_time - now).total_seconds()))
    if spot_price <= ZERO:
        raise ValueError("spot_price_must_be_positive")

    delivery = _select_delivery_candidate(
        market_end_time=market_end_time,
        delivery_candidates=delivery_candidates or [],
        max_distance_seconds=delivery_max_distance_seconds,
    )
    if delivery is not None:
        forward_price = delivery["price"]
        return ForwardBasisEstimate(
            source="delivery_futures",
            estimated_forward_price=forward_price,
            basis_annualized=_annualized_basis(forward_price, spot_price, tau_seconds),
            reason="delivery_futures_closest_to_market_end",
            perp_mark_price=perp_mark_price,
            perp_index_price=perp_index_price,
            perp_last_funding_rate=perp_last_funding_rate,
            perp_next_funding_time=perp_next_funding_time,
            delivery_symbol=delivery["symbol"],
            delivery_price=forward_price,
        )

    if perp_mark_price is not None and perp_mark_price > ZERO:
        return ForwardBasisEstimate(
            source="perp_mark",
            estimated_forward_price=perp_mark_price,
            basis_annualized=_annualized_basis(perp_mark_price, spot_price, tau_seconds),
            reason="perp_mark_basis_fallback",
            perp_mark_price=perp_mark_price,
            perp_index_price=perp_index_price,
            perp_last_funding_rate=perp_last_funding_rate,
            perp_next_funding_time=perp_next_funding_time,
        )

    return ForwardBasisEstimate(
        source="spot_fallback",
        estimated_forward_price=spot_price,
        basis_annualized=ZERO,
        reason="missing_delivery_and_perp_forward_inputs",
        perp_mark_price=perp_mark_price,
        perp_index_price=perp_index_price,
        perp_last_funding_rate=perp_last_funding_rate,
        perp_next_funding_time=perp_next_funding_time,
    )


def parse_millisecond_time(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)


def _select_delivery_candidate(
    market_end_time: datetime,
    delivery_candidates: Iterable[Dict[str, Any]],
    max_distance_seconds: Decimal,
) -> Optional[Dict[str, Any]]:
    candidates = []
    for candidate in delivery_candidates:
        symbol = str(candidate.get("symbol", ""))
        price = _safe_decimal(candidate.get("price"))
        delivery_time = _parse_datetime(candidate.get("delivery_time"))
        if not symbol or price is None or price <= ZERO or delivery_time is None:
            continue
        distance = Decimal(str(abs((delivery_time - market_end_time).total_seconds())))
        if distance <= max_distance_seconds:
            candidates.append({"symbol": symbol, "price": price, "distance": distance})
    if not candidates:
        return None
    return min(candidates, key=lambda item: item["distance"])


def _annualized_basis(forward_price: Decimal, spot_price: Decimal, tau_seconds: Decimal) -> Decimal:
    if forward_price <= ZERO or spot_price <= ZERO or tau_seconds <= ZERO:
        return ZERO
    return Decimal(str(math.log(float(forward_price / spot_price)))) / (tau_seconds / YEAR_SECONDS)


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return _to_utc(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _to_utc(parsed)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
