from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from controllers.generic.probability_gap_option_chain import (
    build_option_chain_slice,
    estimate_call_spread_digital,
    estimate_horizon_smile_sigma,
)


class ProbabilityGapOptionChainTest(TestCase):
    def test_build_option_chain_slice_keeps_reference_near_call_put_rows(self):
        expiry = datetime(2026, 5, 9, 16, 0, tzinfo=UTC)
        expiry_ms = int(expiry.timestamp() * 1000)
        marks = []
        metadata = {}
        tickers = {}
        for strike in (97000, 98000, 99000, 100000, 101000, 102000, 103000, 104000):
            for side, suffix in (("CALL", "C"), ("PUT", "P")):
                symbol = f"BTC-260509-{strike}-{suffix}"
                marks.append({
                    "symbol": symbol,
                    "markPrice": str(max(Decimal("1"), Decimal("104000") - Decimal(strike)) / Decimal("100")),
                    "markIV": "0.50",
                    "delta": "0.50",
                    "riskFreeInterest": "0.01",
                })
                metadata[symbol] = {
                    "symbol": symbol,
                    "side": side,
                    "strikePrice": str(strike),
                    "expiryDate": expiry_ms,
                    "underlying": "BTCUSDT",
                }
                tickers[symbol] = {"bidPrice": "10", "askPrice": "11", "volume": "2", "amount": "20"}

        result = build_option_chain_slice(
            marks=marks,
            option_metadata=metadata,
            tickers_by_symbol=tickers,
            selected_expiry=expiry,
            reference_price=Decimal("100500"),
            current_spot_price=Decimal("100700"),
            observed_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        )

        self.assertEqual("ok", result["status"])
        self.assertEqual(12, len(result["rows"]))
        self.assertEqual({Decimal("98000"), Decimal("99000"), Decimal("100000"), Decimal("101000"), Decimal("102000"), Decimal("103000")}, {row["strike"] for row in result["rows"]})

    def test_call_spread_digital_rejects_horizon_mismatch(self):
        observed_at = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
        option_expiry = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
        market_end = datetime(2026, 5, 9, 16, 0, tzinfo=UTC)

        estimate = estimate_call_spread_digital(
            option_chain_slice={
                "expiry": option_expiry.isoformat(),
                "rows": [
                    {"side": "CALL", "strike": Decimal("99000"), "mark_price": Decimal("20"), "risk_free_rate": Decimal("0")},
                    {"side": "CALL", "strike": Decimal("101000"), "mark_price": Decimal("10"), "risk_free_rate": Decimal("0")},
                ],
            },
            reference_price=Decimal("100000"),
            market_end_time=market_end,
            observed_at=observed_at,
        )

        self.assertEqual("horizon_mismatch", estimate.status)
        self.assertIsNone(estimate.probability)
        self.assertEqual(Decimal("480"), estimate.horizon_mismatch_minutes)

    def test_call_spread_digital_computes_bounded_probability_when_aligned(self):
        observed_at = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
        option_expiry = observed_at + timedelta(hours=4)

        estimate = estimate_call_spread_digital(
            option_chain_slice={
                "expiry": option_expiry.isoformat(),
                "rows": [
                    {"side": "CALL", "strike": Decimal("99000"), "mark_price": Decimal("20"), "risk_free_rate": Decimal("0")},
                    {"side": "CALL", "strike": Decimal("101000"), "mark_price": Decimal("10"), "risk_free_rate": Decimal("0")},
                ],
            },
            reference_price=Decimal("100000"),
            market_end_time=option_expiry,
            observed_at=observed_at,
        )

        self.assertEqual("ok", estimate.status)
        self.assertEqual(Decimal("0.005"), estimate.probability)

    def test_horizon_smile_sigma_interpolates_local_variance(self):
        estimate = estimate_horizon_smile_sigma(
            option_chain_rows=[
                {"side": "CALL", "strike": Decimal("99"), "mark_iv": Decimal("0.30")},
                {"side": "PUT", "strike": Decimal("99"), "mark_iv": Decimal("0.34")},
                {"side": "CALL", "strike": Decimal("101"), "mark_iv": Decimal("0.40")},
                {"side": "PUT", "strike": Decimal("101"), "mark_iv": Decimal("0.44")},
            ],
            reference_price=Decimal("100"),
        )

        self.assertEqual("ok", estimate.status)
        self.assertEqual(Decimal("99"), estimate.lower_strike)
        self.assertEqual(Decimal("101"), estimate.upper_strike)
        self.assertGreater(estimate.sigma, Decimal("0.36"))
        self.assertLess(estimate.sigma, Decimal("0.38"))
        self.assertEqual(2, estimate.strikes_used)

    def test_horizon_smile_sigma_blocks_missing_bracket(self):
        estimate = estimate_horizon_smile_sigma(
            option_chain_rows=[
                {"side": "CALL", "strike": Decimal("99"), "mark_iv": Decimal("0.30")},
            ],
            reference_price=Decimal("100"),
        )

        self.assertEqual("missing_bracketing_iv", estimate.status)
        self.assertIsNone(estimate.sigma)
