import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import Field

from hummingbot.core.data_type.common import MarketDict
from hummingbot.strategy_v2.controllers import ControllerBase, ControllerConfigBase
from hummingbot.strategy_v2.models.executor_actions import ExecutorAction
from controllers.generic.probability_gap_sampling import (
    ProbabilityGapSnapshotStore,
    choose_snapshot_reason,
    replay_tradable_windows,
    summarize_replays,
)
from controllers.generic.probability_gap_forward import (
    estimate_forward_basis,
    parse_millisecond_time,
)
from controllers.generic.probability_gap_option_chain import (
    build_option_chain_slice,
    estimate_call_spread_digital,
)
from controllers.generic.probability_gap_scanner_utils import (
    BinanceSignal,
    ET,
    build_binance_iv_digital_signal,
    build_daily_market_slug,
    calculate_probability_gap,
    evaluate_overlap_window,
    overlap_reason_blocks_sampling,
    parse_polymarket_daily_market,
    safe_decimal,
)

if TYPE_CHECKING:
    import aiohttp


BINANCE_OPTIONS_MARK_URL = "https://eapi.binance.com/eapi/v1/mark"
BINANCE_OPTIONS_EXCHANGE_INFO_URL = "https://eapi.binance.com/eapi/v1/exchangeInfo"
BINANCE_OPTIONS_TICKER_URL = "https://eapi.binance.com/eapi/v1/ticker"
BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_SPOT_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_USDT_PERP_PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_COIN_DELIVERY_PREMIUM_INDEX_URL = "https://dapi.binance.com/dapi/v1/premiumIndex"
BINANCE_COIN_DELIVERY_EXCHANGE_INFO_URL = "https://dapi.binance.com/dapi/v1/exchangeInfo"
POLYMARKET_GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"

ZERO = Decimal("0")


def format_dataframe_for_status(df: pd.DataFrame) -> str:
    try:
        from hummingbot.client.ui.interface_utils import format_df_for_printout

        return format_df_for_printout(df, table_format="psql")
    except ModuleNotFoundError:
        return df.to_string(index=False)


class ProbabilityGapScannerConfig(ControllerConfigBase):
    controller_type: str = "generic"
    controller_name: str = "probability_gap_scanner"
    refresh_interval: int = Field(default=60)
    tradable_refresh_interval: int = Field(default=10)
    near_exit_refresh_interval: int = Field(default=3)
    near_exit_window_minutes: int = Field(default=30)
    market_days_ahead: int = Field(default=1)
    max_display_rows: int = Field(default=10)
    estimated_cost_buffer: Decimal = Field(default=Decimal("0.005"))
    polymarket_taker_fee_rate: Decimal = Field(default=Decimal("0.072"))
    polymarket_maker_fee_rate: Decimal = Field(default=Decimal("0"))
    allow_low_confidence_trading: bool = Field(default=False)
    allow_high_gamma_trading: bool = Field(default=False)
    min_net_edge: Decimal = Field(default=Decimal("0.01"))
    min_minutes_before_settlement: Decimal = Field(default=Decimal("15"))
    max_minutes_before_settlement: Decimal = Field(default=Decimal("720"))
    snapshot_db_path: str = Field(default=".yxg/data/probability_gap_samples.sqlite")

    def update_markets(self, markets: MarketDict) -> MarketDict:
        return markets


class ProbabilityGapScanner(ControllerBase):
    def __init__(self, config: ProbabilityGapScannerConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config
        self._http_session = None
        self._last_refresh_timestamp = 0.0
        self._last_recorded_by_slug: Dict[str, Dict[str, Any]] = {}
        self._reference_close_cache: Dict[str, Decimal] = {}
        self._snapshot_store = ProbabilityGapSnapshotStore(self._resolve_snapshot_db_path())

    def _resolve_snapshot_db_path(self) -> str:
        configured = Path(self.config.snapshot_db_path)
        if configured.is_absolute():
            return str(configured)
        return str((Path.cwd() / configured).resolve())

    async def _ensure_session(self):
        import aiohttp

        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    async def _request_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                session = await self._ensure_session()
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    return await response.json()
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2 ** attempt))
        if last_error is not None:
            raise last_error
        raise RuntimeError("request_failed_without_exception")

    def _candidate_market_slugs(self) -> List[str]:
        now_et = datetime.fromtimestamp(self.market_data_provider.time(), tz=UTC).astimezone(ET)
        base_date = now_et.date()
        return [build_daily_market_slug(base_date + timedelta(days=offset)) for offset in range(self.config.market_days_ahead + 1)]

    async def _fetch_polymarket_markets(self) -> List[Dict[str, Any]]:
        slug_tasks = [
            self._request_json(
                POLYMARKET_GAMMA_MARKETS_URL,
                params={"slug": slug},
            )
            for slug in self._candidate_market_slugs()
        ]
        responses = await asyncio.gather(*slug_tasks)
        raw_markets: List[Dict[str, Any]] = []
        for response in responses:
            if isinstance(response, list):
                raw_markets.extend(item for item in response if isinstance(item, dict))
        return raw_markets

    async def _fetch_option_market_data(self) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        marks_response, exchange_info_response, ticker_response = await asyncio.gather(
            self._request_json(BINANCE_OPTIONS_MARK_URL),
            self._request_json(BINANCE_OPTIONS_EXCHANGE_INFO_URL),
            self._request_json(BINANCE_OPTIONS_TICKER_URL),
        )
        marks = [item for item in marks_response if isinstance(item, dict)] if isinstance(marks_response, list) else []
        tickers_by_symbol = {
            str(item.get("symbol", "")): item
            for item in ticker_response
            if isinstance(item, dict) and item.get("symbol")
        } if isinstance(ticker_response, list) else {}
        option_metadata: Dict[str, Dict[str, Any]] = {}
        if isinstance(exchange_info_response, dict):
            raw_symbols = exchange_info_response.get("optionSymbols")
            if isinstance(raw_symbols, list):
                option_metadata = {
                    str(item.get("symbol", "")): item
                    for item in raw_symbols
                    if isinstance(item, dict) and item.get("symbol")
                }
        return marks, option_metadata, tickers_by_symbol

    def _select_latest_option_signal(
        self,
        target_date: datetime,
        reference_price: Decimal,
        marks: List[Dict[str, Any]],
        option_metadata: Dict[str, Dict[str, Any]],
    ) -> Tuple[
        Optional[Decimal],
        Optional[datetime],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
        Optional[Decimal],
    ]:
        expiry_candidates = []
        for raw_mark in marks:
            symbol = str(raw_mark.get("symbol", ""))
            metadata = option_metadata.get(symbol)
            if metadata is None:
                continue
            delta = safe_decimal(raw_mark.get("delta"))
            mark_iv = safe_decimal(raw_mark.get("markIV"))
            risk_free_rate = safe_decimal(raw_mark.get("riskFreeInterest"))
            underlying = str(metadata.get("underlying", ""))
            side = str(metadata.get("side", ""))
            if underlying != "BTCUSDT" or side != "CALL":
                continue
            expiry_ms = metadata.get("expiryDate")
            if mark_iv is None or mark_iv <= ZERO or expiry_ms is None:
                continue
            strike = safe_decimal(metadata.get("strikePrice"))
            if strike is None:
                continue
            try:
                expiry_time = datetime.fromtimestamp(int(expiry_ms) / 1000, tz=UTC)
            except (TypeError, ValueError, OSError):
                continue
            expiry_candidates.append(
                (
                    abs((expiry_time - target_date).total_seconds()),
                    expiry_time,
                    strike,
                    delta,
                    mark_iv,
                    risk_free_rate,
                )
            )
        if not expiry_candidates:
            return None, None, None, None, None, None, None, None, None, None
        _, selected_expiry, _, _, _, _ = min(expiry_candidates, key=lambda item: item[0])
        same_expiry = [
            (strike, delta, mark_iv, risk_free_rate)
            for _, expiry_time, strike, delta, mark_iv, risk_free_rate in expiry_candidates
            if expiry_time == selected_expiry
        ]
        lowers = [(strike, delta, mark_iv, risk_free_rate) for strike, delta, mark_iv, risk_free_rate in same_expiry if strike <= reference_price]
        uppers = [(strike, delta, mark_iv, risk_free_rate) for strike, delta, mark_iv, risk_free_rate in same_expiry if strike >= reference_price]
        lower = max(lowers, key=lambda item: item[0]) if lowers else None
        upper = min(uppers, key=lambda item: item[0]) if uppers else None
        if lower is not None and upper is not None:
            lower_strike, lower_delta, lower_iv, lower_rf = lower
            upper_strike, upper_delta, upper_iv, upper_rf = upper
            if upper_strike == lower_strike:
                return lower_delta, lower_iv, selected_expiry, lower_strike, lower_delta, lower_iv, upper_strike, upper_delta, upper_iv, lower_rf
            weight = (reference_price - lower_strike) / (upper_strike - lower_strike)
            interpolated_delta = None
            if lower_delta is not None and upper_delta is not None:
                interpolated_delta = lower_delta + (upper_delta - lower_delta) * weight
            interpolated_iv = lower_iv + (upper_iv - lower_iv) * weight
            risk_free_rate = lower_rf if lower_rf is not None else upper_rf
            return interpolated_delta, interpolated_iv, selected_expiry, lower_strike, lower_delta, lower_iv, upper_strike, upper_delta, upper_iv, risk_free_rate
        if lower is not None:
            return lower[1], lower[2], selected_expiry, lower[0], lower[1], lower[2], None, None, None, lower[3]
        if upper is not None:
            return upper[1], upper[2], selected_expiry, None, None, None, upper[0], upper[1], upper[2], upper[3]
        return None, None, None, None, None, None, None, None, None, None

    async def _fetch_binance_reference_close(self, reference_time: datetime) -> Optional[Decimal]:
        cache_key = reference_time.astimezone(UTC).isoformat()
        if cache_key in self._reference_close_cache:
            return self._reference_close_cache[cache_key]
        start_ms = int(reference_time.timestamp() * 1000)
        response = await self._request_json(
            BINANCE_SPOT_KLINES_URL,
            params={
                "symbol": "BTCUSDT",
                "interval": "1m",
                "startTime": str(start_ms),
                "endTime": str(start_ms + 60_000),
                "limit": "1",
            },
        )
        if not isinstance(response, list) or len(response) == 0 or not isinstance(response[0], list) or len(response[0]) < 5:
            return None
        close = safe_decimal(response[0][4])
        if close is not None:
            self._reference_close_cache[cache_key] = close
        return close

    async def _fetch_current_spot_price(self) -> Optional[Decimal]:
        response = await self._request_json(
            BINANCE_SPOT_TICKER_URL,
            params={"symbol": "BTCUSDT"},
        )
        return safe_decimal(response.get("price")) if isinstance(response, dict) else None

    async def _fetch_forward_market_data(self) -> Dict[str, Any]:
        perp_response, delivery_response, delivery_exchange_response = await asyncio.gather(
            self._request_json(BINANCE_USDT_PERP_PREMIUM_INDEX_URL, params={"symbol": "BTCUSDT"}),
            self._request_json(BINANCE_COIN_DELIVERY_PREMIUM_INDEX_URL),
            self._request_json(BINANCE_COIN_DELIVERY_EXCHANGE_INFO_URL),
            return_exceptions=True,
        )
        perp: Dict[str, Any] = perp_response if isinstance(perp_response, dict) else {}
        raw_delivery = delivery_response if isinstance(delivery_response, list) else []
        delivery_dates_by_symbol: Dict[str, datetime] = {}
        if isinstance(delivery_exchange_response, dict):
            for symbol_info in delivery_exchange_response.get("symbols", []):
                if not isinstance(symbol_info, dict):
                    continue
                symbol = str(symbol_info.get("symbol", ""))
                if not symbol.startswith("BTCUSD_"):
                    continue
                delivery_time = parse_millisecond_time(symbol_info.get("deliveryDate"))
                if delivery_time is not None:
                    delivery_dates_by_symbol[symbol] = delivery_time
        delivery_candidates = []
        for item in raw_delivery:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", ""))
            if not symbol.startswith("BTCUSD_"):
                continue
            delivery_time = (
                parse_millisecond_time(item.get("deliveryTime") or item.get("deliveryDate"))
                or delivery_dates_by_symbol.get(symbol)
            )
            price = safe_decimal(item.get("markPrice") or item.get("indexPrice"))
            if delivery_time is None or price is None:
                continue
            delivery_candidates.append(
                {
                    "symbol": symbol,
                    "delivery_time": delivery_time,
                    "price": price,
                }
            )
        return {
            "perp_mark_price": safe_decimal(perp.get("markPrice")),
            "perp_index_price": safe_decimal(perp.get("indexPrice")),
            "perp_last_funding_rate": safe_decimal(perp.get("lastFundingRate")),
            "perp_next_funding_time": parse_millisecond_time(perp.get("nextFundingTime")),
            "delivery_candidates": delivery_candidates,
        }

    async def update_processed_data(self):
        now_ts = self.market_data_provider.time()
        if self.processed_data and now_ts - self._last_refresh_timestamp < self._current_refresh_interval(now_ts):
            return
        self._last_refresh_timestamp = now_ts
        now = datetime.fromtimestamp(now_ts, tz=UTC)

        try:
            polymarket_raw_markets, current_spot_price, option_market_data, forward_market_data = await asyncio.gather(
                self._fetch_polymarket_markets(),
                self._fetch_current_spot_price(),
                self._fetch_option_market_data(),
                self._fetch_forward_market_data(),
            )
            option_marks, option_metadata, tickers_by_symbol = option_market_data

            if current_spot_price is None:
                raise ValueError("missing_current_spot_price")

            opportunities: List[Dict[str, Any]] = []
            observations: List[Dict[str, Any]] = []
            rejected_markets: List[Dict[str, Any]] = []

            for raw_market in polymarket_raw_markets:
                market, rejection_reason = parse_polymarket_daily_market(raw_market)
                if market is None:
                    rejected_markets.append(
                        {
                            "question": raw_market.get("question", ""),
                            "slug": raw_market.get("slug", ""),
                            "rejection_reason": rejection_reason,
                        }
                    )
                    continue

                trading_window_rejection_reason = evaluate_overlap_window(
                    market=market,
                    now=now,
                    min_minutes_before_settlement=self.config.min_minutes_before_settlement,
                    max_minutes_before_settlement=self.config.max_minutes_before_settlement,
                )
                if overlap_reason_blocks_sampling(trading_window_rejection_reason):
                    rejected_markets.append(
                        {
                            "question": market.question,
                            "slug": market.slug,
                            "rejection_reason": trading_window_rejection_reason,
                        }
                    )
                    continue

                reference_price = await self._fetch_binance_reference_close(market.reference_time)
                if reference_price is None:
                    rejected_markets.append(
                        {
                            "question": market.question,
                            "slug": market.slug,
                            "rejection_reason": "reference_price_not_fixed",
                        }
                    )
                    continue

                forward_basis = estimate_forward_basis(
                    now=now,
                    market_end_time=market.end_time,
                    spot_price=current_spot_price,
                    perp_mark_price=forward_market_data.get("perp_mark_price"),
                    perp_index_price=forward_market_data.get("perp_index_price"),
                    perp_last_funding_rate=forward_market_data.get("perp_last_funding_rate"),
                    perp_next_funding_time=forward_market_data.get("perp_next_funding_time"),
                    delivery_candidates=forward_market_data.get("delivery_candidates", []),
                )

                (
                    latest_option_delta,
                    latest_option_iv,
                    latest_option_expiry,
                    lower_strike,
                    lower_delta,
                    lower_iv,
                    upper_strike,
                    upper_delta,
                    upper_iv,
                    risk_free_rate,
                ) = self._select_latest_option_signal(
                    target_date=market.end_time,
                    reference_price=reference_price,
                    marks=option_marks,
                    option_metadata=option_metadata,
                )
                binance_signal, rejection_reason = build_binance_iv_digital_signal(
                    now=now,
                    market=market,
                    reference_price=reference_price,
                    current_spot_price=current_spot_price,
                    option_iv=latest_option_iv,
                    option_expiry=latest_option_expiry,
                    lower_strike=lower_strike,
                    lower_delta=lower_delta,
                    lower_iv=lower_iv,
                    upper_strike=upper_strike,
                    upper_delta=upper_delta,
                    upper_iv=upper_iv,
                    interpolated_option_delta=latest_option_delta,
                    risk_free_rate=risk_free_rate,
                )
                if binance_signal is None:
                    rejected_markets.append(
                        {
                            "question": market.question,
                            "slug": market.slug,
                            "rejection_reason": rejection_reason,
                        }
                    )
                    continue

                option_chain_slice = build_option_chain_slice(
                    marks=option_marks,
                    option_metadata=option_metadata,
                    tickers_by_symbol=tickers_by_symbol,
                    selected_expiry=latest_option_expiry,
                    reference_price=reference_price,
                    current_spot_price=current_spot_price,
                    observed_at=now,
                )
                call_spread_estimate = estimate_call_spread_digital(
                    option_chain_slice=option_chain_slice,
                    reference_price=reference_price,
                    market_end_time=market.end_time,
                    observed_at=now,
                )

                forced_exit_time = min(
                    latest_option_expiry if latest_option_expiry is not None else market.end_time,
                    market.end_time - timedelta(minutes=float(self.config.min_minutes_before_settlement)),
                )
                gap = calculate_probability_gap(
                    market=market,
                    binance_signal=binance_signal.signal_value,
                    estimated_cost_buffer=self.config.estimated_cost_buffer,
                    polymarket_taker_fee_rate=self.config.polymarket_taker_fee_rate,
                    polymarket_maker_fee_rate=self.config.polymarket_maker_fee_rate,
                )
                is_tradable = binance_signal.tradable
                classification_reason = binance_signal.classification_reason
                if trading_window_rejection_reason is not None:
                    is_tradable = False
                    classification_reason = trading_window_rejection_reason
                if binance_signal.model_confidence == "low" and not self.config.allow_low_confidence_trading:
                    is_tradable = False
                    classification_reason = "low_model_confidence"
                if binance_signal.gamma_risk == "high" and not self.config.allow_high_gamma_trading:
                    is_tradable = False
                    classification_reason = "high_gamma_risk"
                entry = {
                    "question": market.question,
                    "slug": market.slug,
                    "market_end_time": market.end_time.isoformat(),
                    "reference_time": market.reference_time.isoformat(),
                    "reference_price": reference_price,
                    "current_spot_price": current_spot_price,
                    **forward_basis.as_payload(),
                    "binance_signal_kind": binance_signal.signal_kind,
                    "binance_signal_value": gap.binance_signal,
                    "model_version": binance_signal.model_version,
                    "fair_value_up": binance_signal.fair_value_up if binance_signal.fair_value_up is not None else gap.binance_signal,
                    "fair_value_down": binance_signal.fair_value_down if binance_signal.fair_value_down is not None else Decimal("1") - gap.binance_signal,
                    "option_iv": binance_signal.option_iv if binance_signal.option_iv is not None else "",
                    "interpolated_option_iv": binance_signal.interpolated_option_iv if binance_signal.interpolated_option_iv is not None else "",
                    "tau_years": binance_signal.tau_years if binance_signal.tau_years is not None else "",
                    "d2": binance_signal.d2 if binance_signal.d2 is not None else "",
                    "prob_delta": binance_signal.prob_delta if binance_signal.prob_delta is not None else "",
                    "gamma_risk": binance_signal.gamma_risk,
                    "model_confidence": binance_signal.model_confidence,
                    "risk_free_rate": binance_signal.risk_free_rate if binance_signal.risk_free_rate is not None else "",
                    "expiry_mismatch_minutes": binance_signal.expiry_mismatch_minutes if binance_signal.expiry_mismatch_minutes is not None else "",
                    "binance_overlap_penalty": binance_signal.overlap_penalty,
                    "minutes_to_settlement": binance_signal.minutes_to_settlement,
                    "minutes_to_signal_expiry": binance_signal.minutes_to_signal_expiry,
                    "selected_option_expiry": latest_option_expiry.isoformat() if latest_option_expiry is not None else "",
                    "option_chain_slice": option_chain_slice.get("rows", []),
                    "option_chain_slice_count": len(option_chain_slice.get("rows", [])),
                    "option_chain_slice_source": option_chain_slice.get("source", ""),
                    "option_chain_slice_expiry": option_chain_slice.get("expiry", ""),
                    **call_spread_estimate.as_payload(),
                    "lower_strike": lower_strike if lower_strike is not None else "",
                    "lower_delta": lower_delta if lower_delta is not None else "",
                    "lower_iv": lower_iv if lower_iv is not None else "",
                    "upper_strike": upper_strike if upper_strike is not None else "",
                    "upper_delta": upper_delta if upper_delta is not None else "",
                    "upper_iv": upper_iv if upper_iv is not None else "",
                    "interpolated_option_delta": latest_option_delta if latest_option_delta is not None else "",
                    "overlap_window_end_time": forced_exit_time.isoformat(),
                    "forced_exit_time": forced_exit_time.isoformat(),
                    "polymarket_up_best_bid": market.up_best_bid,
                    "polymarket_up_best_ask": gap.polymarket_up_best_ask,
                    "polymarket_down_best_bid": ZERO if gap.polymarket_up_best_ask >= Decimal("1") else Decimal("1") - gap.polymarket_up_best_ask,
                    "polymarket_down_best_ask": gap.polymarket_down_best_ask,
                    "polymarket_mid": gap.polymarket_mid,
                    "gross_edge_up": gap.gross_edge_up,
                    "gross_edge_down": gap.gross_edge_down,
                    "estimated_cost": gap.estimated_cost,
                    "polymarket_taker_fee_rate": gap.taker_fee_rate,
                    "polymarket_taker_fee_up": gap.taker_fee_up,
                    "polymarket_taker_fee_down": gap.taker_fee_down,
                    "maker_edge_up": gap.maker_edge_up,
                    "maker_edge_down": gap.maker_edge_down,
                    "taker_edge_up": gap.taker_edge_up,
                    "taker_edge_down": gap.taker_edge_down,
                    "net_edge_up": gap.net_edge_up,
                    "net_edge_down": gap.net_edge_down,
                    "depth_score": gap.depth_score,
                    "alignment_confidence": Decimal("1") - binance_signal.overlap_penalty,
                    "rejection_reason": "",
                    "best_side": gap.best_side,
                    "best_net_edge": gap.best_net_edge,
                    "market_classification": "tradable" if is_tradable else "observable",
                    "classification_reason": classification_reason,
                }
                if is_tradable:
                    opportunities.append(entry)
                else:
                    observations.append(entry)

            ranked_opportunities = sorted(
                opportunities,
                key=lambda item: (item["best_net_edge"], item["alignment_confidence"], item["depth_score"]),
                reverse=True,
            )
            ranked_observations = sorted(
                observations,
                key=lambda item: (item["best_net_edge"], item["alignment_confidence"], item["depth_score"]),
                reverse=True,
            )
            selected_opportunities = [
                item for item in ranked_opportunities if item["best_net_edge"] >= self.config.min_net_edge
            ]

            self.processed_data = {
                "opportunities": selected_opportunities,
                "all_ranked_opportunities": ranked_opportunities,
                "observations": ranked_observations,
                "rejected_markets": rejected_markets,
                "last_update_time": datetime.now(tz=UTC).isoformat(),
                "refresh_interval": self._current_refresh_interval(now_ts),
                "total_polymarket_markets": len(polymarket_raw_markets),
                "target_slugs": self._candidate_market_slugs(),
            }
            self._persist_current_snapshots(now)
        except Exception as e:
            self.logger().error(f"Error updating probability gap scanner data: {e}", exc_info=True)
            self.processed_data = {
                "opportunities": [],
                "all_ranked_opportunities": [],
                "observations": [],
                "rejected_markets": [],
                "last_update_time": datetime.now(tz=UTC).isoformat(),
                "refresh_interval": self._current_refresh_interval(now_ts),
                "error": str(e),
            }

    def _current_refresh_interval(self, now_ts: float) -> int:
        opportunities = self.processed_data.get("all_ranked_opportunities", []) if self.processed_data else []
        if not opportunities:
            return self.config.refresh_interval
        now = datetime.fromtimestamp(now_ts, tz=UTC)
        forced_exit_candidates = [
            datetime.fromisoformat(item["forced_exit_time"].replace("Z", "+00:00"))
            for item in opportunities
            if item.get("forced_exit_time")
        ]
        if not forced_exit_candidates:
            return self.config.tradable_refresh_interval
        nearest_exit = min(forced_exit_candidates)
        minutes_to_exit = (nearest_exit - now).total_seconds() / 60
        if minutes_to_exit <= self.config.near_exit_window_minutes:
            return self.config.near_exit_refresh_interval
        return self.config.tradable_refresh_interval

    def _persist_current_snapshots(self, observed_at: datetime):
        snapshots_to_record: List[Dict[str, Any]] = []
        for item in self.processed_data.get("all_ranked_opportunities", []):
            snapshots_to_record.extend(self._build_snapshot_records(item, observed_at, "tradable"))
        for item in self.processed_data.get("observations", []):
            snapshots_to_record.extend(self._build_snapshot_records(item, observed_at, "observable"))
        for item in self.processed_data.get("rejected_markets", []):
            snapshots_to_record.extend(self._build_snapshot_records(item, observed_at, "rejected"))
        if snapshots_to_record:
            self._snapshot_store.record_snapshots(snapshots_to_record)

    def _build_snapshot_records(self, item: Dict[str, Any], observed_at: datetime, classification: str) -> List[Dict[str, Any]]:
        slug = item.get("slug", "")
        current_snapshot = {
            "observed_at": observed_at.isoformat(),
            "market_slug": slug,
            "signal_window_id": self._signal_window_id(item, classification),
            "market_classification": classification,
            "classification_reason": item.get("classification_reason", item.get("rejection_reason", "")),
            "best_side": item.get("best_side", ""),
            "best_net_edge": item.get("best_net_edge", ""),
            "net_edge_up": item.get("net_edge_up", ""),
            "net_edge_down": item.get("net_edge_down", ""),
            "binance_signal_value": item.get("binance_signal_value", ""),
            "binance_signal_kind": item.get("binance_signal_kind", ""),
            "model_version": item.get("model_version", ""),
            "fair_value_up": item.get("fair_value_up", ""),
            "fair_value_down": item.get("fair_value_down", ""),
            "option_iv": item.get("option_iv", ""),
            "tau_years": item.get("tau_years", ""),
            "d2": item.get("d2", ""),
            "prob_delta": item.get("prob_delta", ""),
            "gamma_risk": item.get("gamma_risk", ""),
            "model_confidence": item.get("model_confidence", ""),
            "risk_free_rate": item.get("risk_free_rate", ""),
            "expiry_mismatch_minutes": item.get("expiry_mismatch_minutes", ""),
            "lower_iv": item.get("lower_iv", ""),
            "upper_iv": item.get("upper_iv", ""),
            "interpolated_option_iv": item.get("interpolated_option_iv", ""),
            "polymarket_taker_fee_rate": item.get("polymarket_taker_fee_rate", ""),
            "polymarket_taker_fee_up": item.get("polymarket_taker_fee_up", ""),
            "polymarket_taker_fee_down": item.get("polymarket_taker_fee_down", ""),
            "maker_edge_up": item.get("maker_edge_up", ""),
            "maker_edge_down": item.get("maker_edge_down", ""),
            "taker_edge_up": item.get("taker_edge_up", ""),
            "taker_edge_down": item.get("taker_edge_down", ""),
            "current_spot_price": item.get("current_spot_price", ""),
            "reference_price": item.get("reference_price", ""),
            "forward_source": item.get("forward_source", ""),
            "estimated_forward_price": item.get("estimated_forward_price", ""),
            "basis_annualized": item.get("basis_annualized", ""),
            "perp_mark_price": item.get("perp_mark_price", ""),
            "perp_index_price": item.get("perp_index_price", ""),
            "perp_last_funding_rate": item.get("perp_last_funding_rate", ""),
            "perp_next_funding_time": item.get("perp_next_funding_time", ""),
            "delivery_symbol": item.get("delivery_symbol", ""),
            "delivery_price": item.get("delivery_price", ""),
            "forward_basis_reason": item.get("forward_basis_reason", ""),
            "option_chain_slice": item.get("option_chain_slice", []),
            "option_chain_slice_count": item.get("option_chain_slice_count", ""),
            "option_chain_slice_source": item.get("option_chain_slice_source", ""),
            "option_chain_slice_expiry": item.get("option_chain_slice_expiry", ""),
            "option_chain_horizon_mismatch_minutes": item.get("option_chain_horizon_mismatch_minutes", ""),
            "smile_call_spread_probability": item.get("smile_call_spread_probability", ""),
            "smile_call_spread_status": item.get("smile_call_spread_status", ""),
            "smile_call_spread_reason": item.get("smile_call_spread_reason", ""),
            "up_best_bid": item.get("polymarket_up_best_bid", ""),
            "up_best_ask": item.get("polymarket_up_best_ask", ""),
            "down_best_bid": item.get("polymarket_down_best_bid", ""),
            "down_best_ask": item.get("polymarket_down_best_ask", ""),
            "selected_option_expiry": item.get("selected_option_expiry", ""),
            "forced_exit_time": item.get("forced_exit_time", ""),
        }
        previous_snapshot = self._last_recorded_by_slug.get(slug)
        reason = choose_snapshot_reason(
            current_snapshot=current_snapshot,
            previous_snapshot=previous_snapshot,
            now=observed_at,
            baseline_interval_seconds=self.config.refresh_interval,
            tradable_interval_seconds=self.config.tradable_refresh_interval,
            near_exit_interval_seconds=self.config.near_exit_refresh_interval,
            near_exit_window_minutes=self.config.near_exit_window_minutes,
            min_net_edge=self.config.min_net_edge,
        )
        if reason is None:
            return []
        self._last_recorded_by_slug[slug] = current_snapshot
        return [
            {
                **current_snapshot,
                "snapshot_reason": reason,
                "payload": item,
            }
        ]

    def _signal_window_id(self, item: Dict[str, Any], classification: str) -> str:
        slug = item.get("slug", "unknown")
        if classification == "rejected":
            return f"{slug}:rejected:{item.get('rejection_reason', '')}"
        return f"{slug}:{item.get('best_side', '')}:{item.get('forced_exit_time', '')}"

    def determine_executor_actions(self) -> List[ExecutorAction]:
        return []

    def _format_market_table(self, markets: List[Dict[str, Any]]) -> Optional[str]:
        if len(markets) == 0:
            return None
        rows = []
        for item in markets[: self.config.max_display_rows]:
            rows.append(
                {
                    "class": item["market_classification"],
                    "side": item["best_side"],
                    "signal": float(item["binance_signal_value"]),
                    "kind": item["binance_signal_kind"],
                    "model": item.get("model_version", ""),
                    "iv": float(item["option_iv"]) if item.get("option_iv", "") != "" else None,
                    "tau": float(item["tau_years"]) if item.get("tau_years", "") != "" else None,
                    "gamma": item.get("gamma_risk", ""),
                    "expiry": item["selected_option_expiry"][:16] if item["selected_option_expiry"] else "",
                    "lo_k": float(item["lower_strike"]) if item["lower_strike"] != "" else None,
                    "lo_iv": float(item["lower_iv"]) if item.get("lower_iv", "") != "" else None,
                    "hi_k": float(item["upper_strike"]) if item["upper_strike"] != "" else None,
                    "hi_iv": float(item["upper_iv"]) if item.get("upper_iv", "") != "" else None,
                    "fwd_src": item.get("forward_source", ""),
                    "basis": float(item["basis_annualized"]) if item.get("basis_annualized", "") != "" else None,
                    "chain": item.get("option_chain_slice_count", 0),
                    "smile": item.get("smile_call_spread_status", ""),
                    "penalty": float(item["binance_overlap_penalty"]),
                    "up_ask": float(item["polymarket_up_best_ask"]),
                    "down_ask": float(item["polymarket_down_best_ask"]),
                    "taker_up": float(item.get("taker_edge_up", item["net_edge_up"])),
                    "taker_down": float(item.get("taker_edge_down", item["net_edge_down"])),
                    "maker_up": float(item.get("maker_edge_up", item["net_edge_up"])),
                    "maker_down": float(item.get("maker_edge_down", item["net_edge_down"])),
                    "exit_at": item["forced_exit_time"][11:16] if item["forced_exit_time"] else "",
                    "reason": item["classification_reason"],
                    "slug": item["slug"],
                }
            )
        return format_dataframe_for_status(pd.DataFrame(rows))

    def _format_rejections_table(self, rejected_markets: List[Dict[str, Any]]) -> Optional[str]:
        if len(rejected_markets) == 0:
            return None
        summary_rows = (
            pd.DataFrame(rejected_markets)
            .groupby("rejection_reason", dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["count", "rejection_reason"], ascending=[False, True])
        )
        return format_dataframe_for_status(summary_rows.head(self.config.max_display_rows))

    def to_format_status(self) -> List[str]:
        lines = ["", "PROBABILITY GAP SCANNER", "=" * 80]
        if not self.processed_data:
            lines.append("Scanner has not produced data yet.")
            return lines

        lines.append(f"Last update: {self.processed_data.get('last_update_time', 'N/A')}")
        lines.append(f"Refresh interval: {self.config.refresh_interval}s")
        lines.append(f"Target slugs: {', '.join(self.processed_data.get('target_slugs', []))}")
        lines.append(f"Polymarket markets fetched: {self.processed_data.get('total_polymarket_markets', 0)}")
        lines.append(f"Snapshot rows: {self._snapshot_store.count_snapshots()}")

        if self.processed_data.get("error"):
            lines.append(f"Error: {self.processed_data['error']}")
            return lines

        opportunities = self.processed_data.get("opportunities", [])
        observations = self.processed_data.get("observations", [])
        rejected_markets = self.processed_data.get("rejected_markets", [])
        lines.append(f"Qualified opportunities: {len(opportunities)}")
        lines.append(f"Observable but not tradable: {len(observations)}")
        lines.append(f"Rejected markets: {len(rejected_markets)}")

        opportunities_table = self._format_market_table(opportunities)
        if opportunities_table is not None:
            lines.extend(["", "Top opportunities:", opportunities_table])
        else:
            lines.extend(["", "Top opportunities:", "No opportunities met the current net-edge threshold."])

        observations_table = self._format_market_table(observations)
        if observations_table is not None:
            lines.extend(["", "Observable markets:", observations_table])

        rejections_table = self._format_rejections_table(rejected_markets)
        if rejections_table is not None:
            lines.extend(["", "Rejection summary:", rejections_table])

        replay_summary = summarize_replays(
            replay_tradable_windows(
                self._snapshot_store.list_snapshots(),
                min_net_edge=self.config.min_net_edge,
            )
        )
        lines.extend(
            [
                "",
                "Replay summary:",
                f"windows={replay_summary['n_replays']} positive_ratio={replay_summary['positive_ratio']:.2f} "
                f"avg_realized_move={replay_summary['avg_realized_move']:.4f} "
                f"avg_best_move={replay_summary['avg_best_available_move']:.4f}",
            ]
        )

        return lines

    def get_custom_info(self) -> Dict[str, Any]:
        opportunities = self.processed_data.get("opportunities", []) if self.processed_data else []
        top_edge = max((item["best_net_edge"] for item in opportunities), default=ZERO)
        replay_summary = summarize_replays(
            replay_tradable_windows(
                self._snapshot_store.list_snapshots(),
                min_net_edge=self.config.min_net_edge,
            )
        )
        return {
            "n_opportunities": len(opportunities),
            "n_observations": len(self.processed_data.get("observations", [])) if self.processed_data else 0,
            "n_rejections": len(self.processed_data.get("rejected_markets", [])) if self.processed_data else 0,
            "top_net_edge": float(top_edge),
            "top_forced_exit_time": opportunities[0]["forced_exit_time"] if opportunities else "",
            "snapshot_db_path": self._resolve_snapshot_db_path(),
            "n_snapshots": self._snapshot_store.count_snapshots(),
            "n_replays": replay_summary["n_replays"],
            "replay_positive_ratio": replay_summary["positive_ratio"],
        }

    async def stop(self):
        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
        super().stop()
