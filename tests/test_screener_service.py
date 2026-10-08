import unittest

import pandas as pd

from screener_service import filter_fundamentals, parse_fundamental_query


class ScreenerServiceTests(unittest.TestCase):
    def test_parses_plain_english_fundamental_rules(self):
        rules = parse_fundamental_query("PE under 25 and ROE above 15% and market cap over 50000 crore")
        self.assertEqual([(rule.field, rule.operator, rule.value) for rule in rules], [("pe", "<", 25.0), ("roe", ">", 15.0), ("market_cap_cr", ">", 50000.0)])

    def test_filters_fundamentals_and_excludes_missing_values(self):
        frame = pd.DataFrame({"Symbol": ["A", "B", "C"], "pe": [20, 30, None], "roe": [18, 18, 25]})
        result = filter_fundamentals(frame, parse_fundamental_query("PE under 25 and ROE above 15"))
        self.assertEqual(result["Symbol"].tolist(), ["A"])

    def test_rejects_unstructured_query(self):
        with self.assertRaises(ValueError):
            parse_fundamental_query("find quality stocks")


if __name__ == "__main__":
    unittest.main()
