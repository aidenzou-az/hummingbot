import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
ONE = Decimal("1")
ZERO = Decimal("0")
BITCOIN_PATTERN = re.compile(r"\b(bitcoin|btc)\b", re.IGNORECASE)
DAILY_QUESTION_PATTERN = re.compile(r"^Bitcoin Up or Down on (?P<month>[A-Za-z]+) (?P<day>\d{1,2})\?$")
DAILY_SLUG_PATTERN = re.compile(
    r"^bitcoin-up-or-down-on-(?P<month>[a-z]+)-(?P<day>\d{1,2})-(?P<year>\d{4})$"
)


@dataclass(frozen=True)
class PolymarketDailyMarket:
    condition_id: str
    slug: str
    question: str
    market_date: date
    end_time: datetime
    reference_time: datetime
    up_token_id: str
    down_token_id: str
    description: str
    resolution_source: str
    up_best_bid: Decimal
    up_best_ask: Decimal
    up_mid: Decimal
    down_mid: Decimal
    liquidity_clob: Decimal


@dataclass(frozen=True)
class BinanceSignal:
    signal_value: Decimal
    signal_kind: str
    signal_timestamp: datetime
    overlap_penalty: Decimal
    minutes_to_settlement: Decimal
    minutes_to_signal_expiry: Decimal
    tradable: bool
    classification_reason: str
    selected_option_expiry: Optional[datetime] = None
    model_version: str = ""
    fair_value_up: Optional[Decimal] = None
    fair_value_down: Optional[Decimal] = None
    option_iv: Optional[Decimal] = None
    tau_years: Optional[Decimal] = None
    d2: Optional[Decimal] = None
    prob_delta: Optional[Decimal] = None
    gamma_risk: str = ""
    model_confidence: str = ""
    risk_free_rate: Optional[Decimal] = None
    expiry_mismatch_minutes: Optional[Decimal] = None
    lower_strike: Optional[Decimal] = None
    lower_delta: Optional[Decimal] = None
    lower_iv: Optional[Decimal] = None
    upper_strike: Optional[Decimal] = None
    upper_delta: Optional[Decimal] = None
    upper_iv: Optional[Decimal] = None
    interpolated_option_delta: Optional[Decimal] = None
    interpolated_option_iv: Optional[Decimal] = None


@dataclass(frozen=True)
class ProbabilityGap:
    binance_signal: Decimal
    polymarket_up_best_ask: Decimal
    polymarket_down_best_ask: Decimal
    polymarket_mid: Decimal
    gross_edge_up: Decimal
    gross_edge_down: Decimal
    estimated_cost: Decimal
    taker_fee_rate: Decimal
    taker_fee_up: Decimal
    taker_fee_down: Decimal
    maker_edge_up: Decimal
    maker_edge_down: Decimal
    taker_edge_up: Decimal
    taker_edge_down: Decimal
    net_edge_up: Decimal
    net_edge_down: Decimal
    depth_score: Decimal
    best_side: str
    best_net_edge: Decimal


def parse_json_list_field(raw_value: Any) -> List[Any]:
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return []
    return []


def safe_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_daily_market_slug(market_date: date) -> str:
    return f"bitcoin-up-or-down-on-{market_date.strftime('%B').lower()}-{market_date.day}-{market_date.year}"


def resolution_references_binance_btcusdt(market: Dict[str, Any]) -> bool:
    source_text = " ".join(
        filter(
            None,
            [
                str(market.get("description", "")),
                str(market.get("resolutionSource", "")),
            ],
        )
    ).lower()
    return "binance" in source_text and any(token in source_text for token in ("btcusdt", "btc/usdt", "btc_usdt"))


def _parse_market_date(question: str, slug: str) -> Optional[date]:
    question_match = DAILY_QUESTION_PATTERN.match(question.strip())
    slug_match = DAILY_SLUG_PATTERN.match(slug.strip())
    if question_match is None or slug_match is None:
        return None

    question_month = question_match.group("month").lower()
    question_day = int(question_match.group("day"))
    slug_month = slug_match.group("month").lower()
    slug_day = int(slug_match.group("day"))
    year = int(slug_match.group("year"))
    if question_month != slug_month or question_day != slug_day:
        return None

    try:
        return datetime.strptime(f"{slug_month.title()} {slug_day} {year}", "%B %d %Y").date()
    except ValueError:
        return None


def parse_polymarket_daily_market(market: Dict[str, Any]) -> Tuple[Optional[PolymarketDailyMarket], Optional[str]]:
    question = str(market.get("question", ""))
    slug = str(market.get("slug", ""))
    if not BITCOIN_PATTERN.search(question):
        return None, "unsupported_underlying"

    market_date = _parse_market_date(question, slug)
    if market_date is None:
        return None, "unsupported_question_pattern"

    end_time = parse_iso_datetime(market.get("endDate"))
    if end_time is None:
        return None, "missing_end_time"

    end_time_et = end_time.astimezone(ET)
    if end_time_et.date() != market_date or end_time_et.hour != 12 or end_time_et.minute != 0:
        return None, "invalid_end_time"

    if not resolution_references_binance_btcusdt(market):
        return None, "unsupported_reference_definition"

    outcomes = [str(outcome) for outcome in parse_json_list_field(market.get("outcomes"))]
    token_ids = [str(token_id) for token_id in parse_json_list_field(market.get("clobTokenIds"))]
    if len(outcomes) != 2 or len(token_ids) != 2:
        return None, "invalid_binary_market_shape"

    normalized_outcomes = [outcome.lower() for outcome in outcomes]
    if normalized_outcomes != ["up", "down"]:
        return None, "unsupported_outcomes"

    up_best_bid = safe_decimal(market.get("bestBid"))
    up_best_ask = safe_decimal(market.get("bestAsk"))
    if up_best_bid is None or up_best_ask is None:
        return None, "missing_top_of_book"

    outcome_prices = parse_json_list_field(market.get("outcomePrices"))
    if len(outcome_prices) != 2:
        return None, "missing_mid_prices"

    up_mid = safe_decimal(outcome_prices[0])
    down_mid = safe_decimal(outcome_prices[1])
    if up_mid is None or down_mid is None:
        return None, "invalid_mid_prices"

    liquidity_clob = safe_decimal(market.get("liquidityClob")) or ZERO
    reference_time = end_time - timedelta(days=1)
    return (
        PolymarketDailyMarket(
            condition_id=str(market.get("conditionId", "")),
            slug=slug,
            question=question,
            market_date=market_date,
            end_time=end_time,
            reference_time=reference_time,
            up_token_id=token_ids[0],
            down_token_id=token_ids[1],
            description=str(market.get("description", "")),
            resolution_source=str(market.get("resolutionSource", "")),
            up_best_bid=up_best_bid,
            up_best_ask=up_best_ask,
            up_mid=up_mid,
            down_mid=down_mid,
            liquidity_clob=liquidity_clob,
        ),
        None,
    )


def evaluate_overlap_window(
    market: PolymarketDailyMarket,
    now: datetime,
    min_minutes_before_settlement: Decimal,
    max_minutes_before_settlement: Decimal,
) -> Optional[str]:
    minutes_to_settlement = Decimal(str((market.end_time - now).total_seconds() / 60))
    if minutes_to_settlement <= ZERO:
        return "market_already_settled"
    if minutes_to_settlement < min_minutes_before_settlement:
        return "inside_exit_buffer"
    if minutes_to_settlement > max_minutes_before_settlement:
        return "outside_overlap_window"
    return None


def overlap_reason_blocks_sampling(reason: Optional[str]) -> bool:
    return reason in {"market_already_settled", "inside_exit_buffer"}


def build_binance_overlap_signal(
    now: datetime,
    market: PolymarketDailyMarket,
    reference_price: Decimal,
    current_spot_price: Decimal,
    latest_option_delta: Optional[Decimal],
    latest_option_expiry: Optional[datetime],
) -> Tuple[Optional[BinanceSignal], Optional[str]]:
    minutes_to_settlement = Decimal(str((market.end_time - now).total_seconds() / 60))
    if minutes_to_settlement <= ZERO:
        return None, "market_already_settled"

    spot_distance_ratio = (current_spot_price - reference_price) / reference_price
    spot_signal = Decimal("0.5") + spot_distance_ratio * Decimal("20")
    if spot_signal < ZERO:
        spot_signal = ZERO
    if spot_signal > ONE:
        spot_signal = ONE

    if latest_option_delta is None or latest_option_expiry is None:
        return (
            BinanceSignal(
                signal_value=spot_signal,
                signal_kind="spot_only",
                signal_timestamp=now,
                overlap_penalty=ZERO,
                minutes_to_settlement=minutes_to_settlement,
                minutes_to_signal_expiry=ZERO,
                tradable=False,
                classification_reason="no_live_option_signal",
            ),
            None,
        )

    minutes_to_option_expiry = Decimal(str((latest_option_expiry - now).total_seconds() / 60))
    if minutes_to_option_expiry <= ZERO:
        return None, "binance_signal_expired"

    uncovered_minutes = abs(minutes_to_option_expiry - minutes_to_settlement)
    overlap_penalty = uncovered_minutes / Decimal("1440")

    weight = ONE - overlap_penalty
    if weight < ZERO:
        weight = ZERO
    normalized_signal = (latest_option_delta * weight) + (spot_signal * (ONE - weight))
    if normalized_signal < ZERO:
        normalized_signal = ZERO
    if normalized_signal > ONE:
        normalized_signal = ONE

    return (
            BinanceSignal(
                signal_value=normalized_signal,
                signal_kind="spot_option_blend",
                signal_timestamp=now,
                overlap_penalty=overlap_penalty,
                minutes_to_settlement=minutes_to_settlement,
                minutes_to_signal_expiry=minutes_to_option_expiry,
                tradable=True,
                classification_reason="overlap_window_live",
                selected_option_expiry=latest_option_expiry,
                interpolated_option_delta=latest_option_delta,
            ),
            None,
        )


def normal_cdf(value: Decimal) -> Decimal:
    return Decimal(str(0.5 * (1.0 + math.erf(float(value) / math.sqrt(2.0)))))


def normal_pdf(value: Decimal) -> Decimal:
    x = float(value)
    return Decimal(str(math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)))


def calculate_digital_probability(
    current_spot_price: Decimal,
    reference_price: Decimal,
    sigma: Decimal,
    tau_years: Decimal,
    risk_free_rate: Decimal = ZERO,
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    if current_spot_price <= ZERO or reference_price <= ZERO or sigma <= ZERO or tau_years <= ZERO:
        return None, None, None

    spot = float(current_spot_price)
    strike = float(reference_price)
    vol = float(sigma)
    tau = float(tau_years)
    rate = float(risk_free_rate)
    sqrt_tau = math.sqrt(tau)
    denominator = vol * sqrt_tau
    if denominator <= 0:
        return None, None, None

    d2_float = (math.log(spot / strike) + (rate - 0.5 * vol * vol) * tau) / denominator
    p_up = Decimal(str(0.5 * (1.0 + math.erf(d2_float / math.sqrt(2.0)))))
    d2 = Decimal(str(d2_float))
    prob_delta = normal_pdf(d2) / (current_spot_price * sigma * Decimal(str(sqrt_tau)))
    if p_up < ZERO:
        p_up = ZERO
    if p_up > ONE:
        p_up = ONE
    return p_up, d2, prob_delta


def classify_gamma_risk(
    current_spot_price: Decimal,
    reference_price: Decimal,
    minutes_to_settlement: Decimal,
    prob_delta: Optional[Decimal],
) -> str:
    if current_spot_price <= ZERO or reference_price <= ZERO:
        return "unknown"
    distance_ratio = abs((current_spot_price - reference_price) / reference_price)
    if minutes_to_settlement <= Decimal("30") and distance_ratio <= Decimal("0.005"):
        return "high"
    if minutes_to_settlement <= Decimal("120") and distance_ratio <= Decimal("0.01"):
        return "medium"
    if prob_delta is not None and prob_delta >= Decimal("0.0002"):
        return "medium"
    return "low"


def build_binance_iv_digital_signal(
    now: datetime,
    market: PolymarketDailyMarket,
    reference_price: Decimal,
    current_spot_price: Decimal,
    option_iv: Optional[Decimal],
    option_expiry: Optional[datetime],
    lower_strike: Optional[Decimal] = None,
    lower_delta: Optional[Decimal] = None,
    lower_iv: Optional[Decimal] = None,
    upper_strike: Optional[Decimal] = None,
    upper_delta: Optional[Decimal] = None,
    upper_iv: Optional[Decimal] = None,
    interpolated_option_delta: Optional[Decimal] = None,
    risk_free_rate: Optional[Decimal] = None,
) -> Tuple[Optional[BinanceSignal], Optional[str]]:
    minutes_to_settlement = Decimal(str((market.end_time - now).total_seconds() / 60))
    if minutes_to_settlement <= ZERO:
        return None, "market_already_settled"
    if option_iv is None or option_expiry is None:
        return (
            BinanceSignal(
                signal_value=ZERO,
                signal_kind="iv_missing",
                signal_timestamp=now,
                overlap_penalty=ONE,
                minutes_to_settlement=minutes_to_settlement,
                minutes_to_signal_expiry=ZERO,
                tradable=False,
                classification_reason="no_live_option_iv",
                model_version="iv_digital_v1",
            ),
            None,
        )

    minutes_to_option_expiry = Decimal(str((option_expiry - now).total_seconds() / 60))
    if minutes_to_option_expiry <= ZERO:
        return None, "binance_signal_expired"

    tau_years = Decimal(str((market.end_time - now).total_seconds() / (365 * 24 * 60 * 60)))
    rf = risk_free_rate or ZERO
    p_up, d2, prob_delta = calculate_digital_probability(
        current_spot_price=current_spot_price,
        reference_price=reference_price,
        sigma=option_iv,
        tau_years=tau_years,
        risk_free_rate=rf,
    )
    if p_up is None or d2 is None:
        return None, "invalid_iv_digital_probability"

    p_down = ONE - p_up
    expiry_mismatch = minutes_to_option_expiry - minutes_to_settlement
    overlap_penalty = abs(expiry_mismatch) / Decimal("1440")
    if overlap_penalty > ONE:
        overlap_penalty = ONE
    model_confidence = "high"
    if abs(expiry_mismatch) > Decimal("720"):
        model_confidence = "low"
    elif abs(expiry_mismatch) > Decimal("120"):
        model_confidence = "medium"
    gamma_risk = classify_gamma_risk(
        current_spot_price=current_spot_price,
        reference_price=reference_price,
        minutes_to_settlement=minutes_to_settlement,
        prob_delta=prob_delta,
    )

    return (
        BinanceSignal(
            signal_value=p_up,
            signal_kind="iv_digital",
            signal_timestamp=now,
            overlap_penalty=overlap_penalty,
            minutes_to_settlement=minutes_to_settlement,
            minutes_to_signal_expiry=minutes_to_option_expiry,
            tradable=True,
            classification_reason="iv_digital_live",
            selected_option_expiry=option_expiry,
            model_version="iv_digital_v1",
            fair_value_up=p_up,
            fair_value_down=p_down,
            option_iv=option_iv,
            tau_years=tau_years,
            d2=d2,
            prob_delta=prob_delta,
            gamma_risk=gamma_risk,
            model_confidence=model_confidence,
            risk_free_rate=rf,
            expiry_mismatch_minutes=expiry_mismatch,
            lower_strike=lower_strike,
            lower_delta=lower_delta,
            lower_iv=lower_iv,
            upper_strike=upper_strike,
            upper_delta=upper_delta,
            upper_iv=upper_iv,
            interpolated_option_delta=interpolated_option_delta,
            interpolated_option_iv=option_iv,
        ),
        None,
    )


def calculate_probability_gap(
    market: PolymarketDailyMarket,
    binance_signal: Decimal,
    estimated_cost_buffer: Decimal,
    polymarket_taker_fee_rate: Decimal = Decimal("0.072"),
    polymarket_maker_fee_rate: Decimal = ZERO,
) -> ProbabilityGap:
    polymarket_up_best_ask = market.up_best_ask
    polymarket_down_best_ask = ONE - market.up_best_bid
    polymarket_mid = market.up_mid
    down_best_bid = ONE - market.up_best_ask

    up_spread = max(market.up_best_ask - market.up_best_bid, ZERO)
    down_spread = max(polymarket_down_best_ask - down_best_bid, ZERO)
    estimated_cost = max(up_spread, down_spread) / Decimal("2") + estimated_cost_buffer

    gross_edge_up = binance_signal - polymarket_up_best_ask
    gross_edge_down = (ONE - binance_signal) - polymarket_down_best_ask
    taker_fee_up = polymarket_taker_fee_rate * polymarket_up_best_ask * (ONE - polymarket_up_best_ask)
    taker_fee_down = polymarket_taker_fee_rate * polymarket_down_best_ask * (ONE - polymarket_down_best_ask)
    maker_fee_up = polymarket_maker_fee_rate * market.up_best_bid * (ONE - market.up_best_bid)
    maker_fee_down = polymarket_maker_fee_rate * down_best_bid * (ONE - down_best_bid)
    maker_edge_up = binance_signal - market.up_best_bid - maker_fee_up - estimated_cost_buffer
    maker_edge_down = (ONE - binance_signal) - down_best_bid - maker_fee_down - estimated_cost_buffer
    taker_edge_up = gross_edge_up - taker_fee_up - estimated_cost_buffer
    taker_edge_down = gross_edge_down - taker_fee_down - estimated_cost_buffer
    net_edge_up = taker_edge_up
    net_edge_down = taker_edge_down
    best_side = "UP" if net_edge_up >= net_edge_down else "DOWN"
    best_net_edge = max(net_edge_up, net_edge_down)

    return ProbabilityGap(
        binance_signal=binance_signal,
        polymarket_up_best_ask=polymarket_up_best_ask,
        polymarket_down_best_ask=polymarket_down_best_ask,
        polymarket_mid=polymarket_mid,
        gross_edge_up=gross_edge_up,
        gross_edge_down=gross_edge_down,
        estimated_cost=estimated_cost,
        taker_fee_rate=polymarket_taker_fee_rate,
        taker_fee_up=taker_fee_up,
        taker_fee_down=taker_fee_down,
        maker_edge_up=maker_edge_up,
        maker_edge_down=maker_edge_down,
        taker_edge_up=taker_edge_up,
        taker_edge_down=taker_edge_down,
        net_edge_up=net_edge_up,
        net_edge_down=net_edge_down,
        depth_score=market.liquidity_clob,
        best_side=best_side,
        best_net_edge=best_net_edge,
    )
