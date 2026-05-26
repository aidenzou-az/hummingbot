import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional


ZERO = Decimal("0")
ONE = Decimal("1")
YEAR_MINUTES = Decimal("525600")


@dataclass(frozen=True)
class CallSpreadDigitalEstimate:
    status: str
    probability: Optional[Decimal]
    reason: str
    lower_strike: Optional[Decimal] = None
    upper_strike: Optional[Decimal] = None
    lower_call_price: Optional[Decimal] = None
    upper_call_price: Optional[Decimal] = None
    horizon_mismatch_minutes: Optional[Decimal] = None

    def as_payload(self) -> Dict[str, Any]:
        return {
            "smile_call_spread_status": self.status,
            "smile_call_spread_probability": self.probability if self.probability is not None else "",
            "smile_call_spread_reason": self.reason,
            "smile_call_spread_lower_strike": self.lower_strike if self.lower_strike is not None else "",
            "smile_call_spread_upper_strike": self.upper_strike if self.upper_strike is not None else "",
            "smile_call_spread_lower_call_price": self.lower_call_price if self.lower_call_price is not None else "",
            "smile_call_spread_upper_call_price": self.upper_call_price if self.upper_call_price is not None else "",
            "option_chain_horizon_mismatch_minutes": self.horizon_mismatch_minutes if self.horizon_mismatch_minutes is not None else "",
        }


@dataclass(frozen=True)
class HorizonSmileSigmaEstimate:
    status: str
    sigma: Optional[Decimal]
    reason: str
    lower_strike: Optional[Decimal] = None
    upper_strike: Optional[Decimal] = None
    lower_iv: Optional[Decimal] = None
    upper_iv: Optional[Decimal] = None
    strikes_used: int = 0
    skew_per_1pct: Optional[Decimal] = None

    def as_payload(self) -> Dict[str, Any]:
        return {
            "horizon_smile_status": self.status,
            "horizon_smile_sigma": self.sigma if self.sigma is not None else "",
            "horizon_smile_reason": self.reason,
            "horizon_smile_lower_strike": self.lower_strike if self.lower_strike is not None else "",
            "horizon_smile_upper_strike": self.upper_strike if self.upper_strike is not None else "",
            "horizon_smile_lower_iv": self.lower_iv if self.lower_iv is not None else "",
            "horizon_smile_upper_iv": self.upper_iv if self.upper_iv is not None else "",
            "horizon_smile_strikes_used": self.strikes_used,
            "horizon_smile_skew_per_1pct": self.skew_per_1pct if self.skew_per_1pct is not None else "",
        }


def estimate_horizon_smile_sigma(
    option_chain_rows: Iterable[Dict[str, Any]],
    reference_price: Decimal,
) -> HorizonSmileSigmaEstimate:
    if reference_price <= ZERO:
        return HorizonSmileSigmaEstimate("invalid_reference_price", None, "reference price must be positive")
    ivs_by_strike: Dict[Decimal, List[Decimal]] = {}
    for row in option_chain_rows:
        if not isinstance(row, dict):
            continue
        strike = _safe_decimal(row.get("strike"))
        mark_iv = _safe_decimal(row.get("mark_iv"))
        if strike is None or mark_iv is None or strike <= ZERO or mark_iv <= ZERO:
            continue
        if mark_iv > Decimal("5"):
            continue
        ivs_by_strike.setdefault(strike, []).append(mark_iv)
    if not ivs_by_strike:
        return HorizonSmileSigmaEstimate("missing_iv_rows", None, "chain slice has no positive mark IV rows")

    iv_by_strike = {
        strike: sum(values, ZERO) / Decimal(str(len(values)))
        for strike, values in ivs_by_strike.items()
    }
    strikes = sorted(iv_by_strike)
    lower_strikes = [strike for strike in strikes if strike <= reference_price]
    upper_strikes = [strike for strike in strikes if strike >= reference_price]
    if not lower_strikes or not upper_strikes:
        return HorizonSmileSigmaEstimate(
            "missing_bracketing_iv",
            None,
            "requires IV strikes on both sides of reference price",
            strikes_used=len(strikes),
        )
    lower_strike = max(lower_strikes)
    upper_strike = min(upper_strikes)
    lower_iv = iv_by_strike[lower_strike]
    upper_iv = iv_by_strike[upper_strike]
    if lower_iv <= ZERO or upper_iv <= ZERO:
        return HorizonSmileSigmaEstimate("invalid_bracketing_iv", None, "bracketing IV values must be positive", strikes_used=len(strikes))
    if lower_strike == upper_strike:
        sigma = lower_iv
        skew_per_1pct = ZERO
    else:
        weight = (reference_price - lower_strike) / (upper_strike - lower_strike)
        weight = min(ONE, max(ZERO, weight))
        variance = (lower_iv * lower_iv) + ((upper_iv * upper_iv) - (lower_iv * lower_iv)) * weight
        if variance <= ZERO:
            return HorizonSmileSigmaEstimate("invalid_interpolated_variance", None, "interpolated variance must be positive", strikes_used=len(strikes))
        sigma = Decimal(str(math.sqrt(float(variance))))
        strike_pct_width = (upper_strike - lower_strike) / reference_price
        skew_per_1pct = ((upper_iv - lower_iv) / strike_pct_width) / Decimal("100") if strike_pct_width > ZERO else ZERO
    return HorizonSmileSigmaEstimate(
        "ok",
        sigma,
        "local_variance_interpolation",
        lower_strike,
        upper_strike,
        lower_iv,
        upper_iv,
        len(strikes),
        skew_per_1pct,
    )


def build_option_chain_slice(
    marks: Iterable[Dict[str, Any]],
    option_metadata: Dict[str, Dict[str, Any]],
    tickers_by_symbol: Dict[str, Dict[str, Any]],
    selected_expiry: Optional[datetime],
    reference_price: Decimal,
    current_spot_price: Decimal,
    observed_at: datetime,
    strikes_each_side: int = 3,
) -> Dict[str, Any]:
    if selected_expiry is None:
        return {
            "source": "binance_eapi_mark_ticker",
            "status": "missing_selected_expiry",
            "expiry": "",
            "rows": [],
        }
    selected_expiry = _to_utc(selected_expiry)
    candidate_rows: List[Dict[str, Any]] = []
    for mark in marks:
        if not isinstance(mark, dict):
            continue
        symbol = str(mark.get("symbol", ""))
        metadata = option_metadata.get(symbol)
        if metadata is None or metadata.get("underlying") != "BTCUSDT":
            continue
        expiry = _parse_expiry(metadata.get("expiryDate"))
        if expiry != selected_expiry:
            continue
        strike = _safe_decimal(metadata.get("strikePrice"))
        side = str(metadata.get("side", ""))
        if strike is None or side not in {"CALL", "PUT"}:
            continue
        ticker = tickers_by_symbol.get(symbol, {})
        candidate_rows.append(
            {
                "symbol": symbol,
                "expiry": selected_expiry.isoformat(),
                "strike": strike,
                "side": side,
                "mark_price": _safe_decimal(mark.get("markPrice")),
                "bid_price": _safe_decimal(ticker.get("bidPrice")),
                "ask_price": _safe_decimal(ticker.get("askPrice")),
                "mark_iv": _safe_decimal(mark.get("markIV")),
                "bid_iv": _safe_decimal(mark.get("bidIV")),
                "ask_iv": _safe_decimal(mark.get("askIV")),
                "delta": _safe_decimal(mark.get("delta")),
                "underlying_price": current_spot_price,
                "risk_free_rate": _safe_decimal(mark.get("riskFreeInterest")),
                "volume": _safe_decimal(ticker.get("volume")),
                "amount": _safe_decimal(ticker.get("amount")),
                "open_interest": _safe_decimal(ticker.get("openInterest")),
                "source_time": observed_at.isoformat(),
            }
        )
    strikes = sorted({row["strike"] for row in candidate_rows})
    lower = [strike for strike in strikes if strike < reference_price][-strikes_each_side:]
    upper = [strike for strike in strikes if strike >= reference_price][:strikes_each_side]
    selected_strikes = set(lower + upper)
    rows = [
        row
        for row in candidate_rows
        if row["strike"] in selected_strikes
    ]
    rows.sort(key=lambda row: (row["strike"], row["side"]))
    return {
        "source": "binance_eapi_mark_ticker",
        "status": "ok" if rows else "empty_slice",
        "expiry": selected_expiry.isoformat(),
        "rows": rows,
    }


def estimate_call_spread_digital(
    option_chain_slice: Dict[str, Any],
    reference_price: Decimal,
    market_end_time: datetime,
    observed_at: datetime,
    max_horizon_mismatch_minutes: Decimal = Decimal("60"),
) -> CallSpreadDigitalEstimate:
    rows = option_chain_slice.get("rows") or []
    calls = [
        row for row in rows
        if row.get("side") == "CALL"
        and _safe_decimal(row.get("strike")) is not None
        and _safe_decimal(row.get("mark_price")) is not None
    ]
    if len(calls) < 2:
        return CallSpreadDigitalEstimate("insufficient_call_prices", None, "requires at least two call marks")
    expiry = _parse_datetime(option_chain_slice.get("expiry"))
    if expiry is None:
        return CallSpreadDigitalEstimate("missing_option_expiry", None, "chain slice has no expiry")
    market_end_time = _to_utc(market_end_time)
    observed_at = _to_utc(observed_at)
    horizon_mismatch = Decimal(str(abs((expiry - market_end_time).total_seconds() / 60)))

    lower_rows = [
        row for row in calls
        if (_safe_decimal(row.get("strike")) or ZERO) <= reference_price
    ]
    upper_rows = [
        row for row in calls
        if (_safe_decimal(row.get("strike")) or ZERO) >= reference_price
    ]
    lower = max(lower_rows, key=lambda row: _safe_decimal(row.get("strike")) or ZERO) if lower_rows else None
    upper = min(upper_rows, key=lambda row: _safe_decimal(row.get("strike")) or ZERO) if upper_rows else None
    if lower is None or upper is None:
        return CallSpreadDigitalEstimate(
            "missing_bracketing_strikes",
            None,
            "requires call marks on both sides of reference price",
            horizon_mismatch_minutes=horizon_mismatch,
        )
    lower_strike = _safe_decimal(lower.get("strike"))
    upper_strike = _safe_decimal(upper.get("strike"))
    lower_call_price = _safe_decimal(lower.get("mark_price"))
    upper_call_price = _safe_decimal(upper.get("mark_price"))
    if lower_strike is None or upper_strike is None or lower_call_price is None or upper_call_price is None:
        return CallSpreadDigitalEstimate("invalid_call_price_data", None, "call spread fields are incomplete", horizon_mismatch_minutes=horizon_mismatch)
    if upper_strike <= lower_strike:
        return CallSpreadDigitalEstimate("duplicate_bracketing_strikes", None, "finite difference needs distinct strikes", horizon_mismatch_minutes=horizon_mismatch)
    if upper_call_price > lower_call_price:
        return CallSpreadDigitalEstimate(
            "non_monotonic_call_prices",
            None,
            "call mark prices increase with strike",
            lower_strike,
            upper_strike,
            lower_call_price,
            upper_call_price,
            horizon_mismatch,
        )
    if horizon_mismatch > max_horizon_mismatch_minutes:
        return CallSpreadDigitalEstimate(
            "horizon_mismatch",
            None,
            "option expiry is not close enough to Polymarket market end",
            lower_strike,
            upper_strike,
            lower_call_price,
            upper_call_price,
            horizon_mismatch,
        )

    tau = Decimal(str((expiry - observed_at).total_seconds() / 60)) / YEAR_MINUTES
    if tau <= ZERO:
        return CallSpreadDigitalEstimate("expired_option_slice", None, "option expiry is not after observed_at", horizon_mismatch_minutes=horizon_mismatch)
    risk_free_rate = _safe_decimal(lower.get("risk_free_rate")) or _safe_decimal(upper.get("risk_free_rate")) or ZERO
    slope = (upper_call_price - lower_call_price) / (upper_strike - lower_strike)
    discount_adjusted = -Decimal(str(math.exp(float(risk_free_rate * tau)))) * slope
    probability = min(ONE, max(ZERO, discount_adjusted))
    return CallSpreadDigitalEstimate(
        "ok",
        probability,
        "finite_difference_call_spread",
        lower_strike,
        upper_strike,
        lower_call_price,
        upper_call_price,
        horizon_mismatch,
    )


def _parse_expiry(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
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


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
