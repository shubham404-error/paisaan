import unittest
from unittest.mock import patch

import pandas as pd

from yahoo_chart_service import YahooChartError, calculate_indicators, download_daily_history, load_with_last_valid, market_chart, normalize_history, yahoo_symbol


def valid_yahoo_frame(rows: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=rows, freq="B")
    raw_close = [float(value) for value in range(100, 100 + rows)]
    return pd.DataFrame({
        "Open": [value - 0.5 for value in raw_close],
        "High": [value + 1.5 for value in raw_close],
        "Low": [value - 1.5 for value in raw_close],
        "Close": raw_close,
        "Adj Close": [value * 0.5 for value in raw_close],
        "Volume": [1_000_000] * rows,
    }, index=dates)


class YahooChartServiceTests(unittest.TestCase):
    def test_nse_symbol_normalization(self):
        self.assertEqual(yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(yahoo_symbol("RELIANCE.NS"), "RELIANCE.NS")
        self.assertEqual(yahoo_symbol("^NSEI"), "^NSEI")
        with self.assertRaises(ValueError):
            yahoo_symbol("RELIANCE.BO")

    def test_adjusted_ohlc_and_indicator_contract(self):
        history = normalize_history(valid_yahoo_frame(), "RELIANCE.NS")
        self.assertEqual(history.loc[0, "RawClose"], 100)
        self.assertEqual(history.loc[0, "Close"], 50)
        self.assertEqual(history.loc[0, "High"], 50.75)
        indicators = calculate_indicators(history)
        required = {"EMA9", "EMA21", "SMA20", "SMA50", "SMA200", "EMA255", "RSI14", "VolumeSMA20", "Cross9_21", "Cross20_50", "Cross50_200"}
        self.assertTrue(required.issubset(indicators.columns))
        rsi = indicators["RSI14"].dropna()
        self.assertTrue(rsi.between(0, 100).all())

    def test_cross_flags_only_mark_transition_bar(self):
        close = list(range(200, 80, -1)) + list(range(81, 261))
        raw = valid_yahoo_frame(len(close))
        raw["Close"] = close
        raw["Adj Close"] = close
        raw["Open"] = [value - 0.5 for value in close]
        raw["High"] = [value + 1.5 for value in close]
        raw["Low"] = [value - 1.5 for value in close]
        indicators = calculate_indicators(normalize_history(raw, "RELIANCE.NS"))
        pairs = {"Cross9_21": ("EMA9", "EMA21"), "Cross20_50": ("SMA20", "SMA50"), "Cross50_200": ("SMA50", "SMA200")}
        for flag, (fast, slow) in pairs.items():
            for index in indicators.index[indicators[flag]]:
                self.assertGreater(indicators.loc[index, fast], indicators.loc[index, slow])
                self.assertLessEqual(indicators.loc[index - 1, fast], indicators.loc[index - 1, slow])

    def test_empty_missing_and_contradictory_data_are_rejected(self):
        with self.assertRaises(YahooChartError):
            normalize_history(pd.DataFrame(), "RELIANCE.NS")
        with self.assertRaises(YahooChartError):
            normalize_history(valid_yahoo_frame().drop(columns="Adj Close"), "RELIANCE.NS")
        contradictory = valid_yahoo_frame(1)
        contradictory["High"] = 1
        with self.assertRaises(YahooChartError):
            normalize_history(contradictory, "RELIANCE.NS")

    def test_provider_failure_and_last_valid_chart(self):
        with patch("yfinance.download", side_effect=RuntimeError("offline")):
            with self.assertRaises(YahooChartError):
                download_daily_history("RELIANCE.NS")
        last_valid = calculate_indicators(normalize_history(valid_yahoo_frame(30), "RELIANCE.NS"))
        restored, stale = load_with_last_valid(lambda: (_ for _ in ()).throw(YahooChartError("offline")), last_valid)
        self.assertTrue(stale)
        self.assertTrue(restored.equals(last_valid))

    def test_chart_has_three_panels_with_missing_optional_overlay(self):
        indicators = calculate_indicators(normalize_history(valid_yahoo_frame(), "RELIANCE.NS"))
        figure = market_chart(indicators.drop(columns="EMA255"), "RELIANCE.NS", ["EMA9", "EMA255"], days=180, rsi_lines=[(30, "RSI 30"), (70, "RSI 70")])
        self.assertIn("yaxis", figure.layout)
        self.assertIn("yaxis2", figure.layout)
        self.assertIn("yaxis3", figure.layout)
        self.assertEqual(figure.layout.yaxis3.range, (0, 100))


if __name__ == "__main__":
    unittest.main()
