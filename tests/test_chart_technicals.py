import unittest

import pandas as pd

from chart_technicals import add_technicals, technical_summary


class ChartTechnicalTests(unittest.TestCase):
    def test_indicators_are_available_with_sufficient_history(self):
        history = pd.DataFrame({"close": range(100, 320)})
        summary = technical_summary(add_technicals(history))
        self.assertEqual(summary["rsi14"], 100.0)
        self.assertEqual(summary["sma20"], 309.5)
        self.assertEqual(summary["sma50"], 294.5)
        self.assertEqual(summary["sma200"], 219.5)
        self.assertIsNotNone(summary["return_1m"])

    def test_long_indicators_are_unavailable_for_short_history(self):
        summary = technical_summary(add_technicals(pd.DataFrame({"close": range(100, 110)})))
        self.assertIsNone(summary["sma20"])
        self.assertIsNone(summary["return_1m"])
