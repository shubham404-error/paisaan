import unittest
from unittest.mock import patch

from streamlit_data import fetch_history, fetch_quotes


class StreamlitDataTests(unittest.TestCase):
    def test_quotes_preserve_only_verified_constituents(self):
        constituents = [{"symbol": f"SYM{index}", "company": "Company", "industry": "Industry"} for index in range(200)]

        def quote_response(tool, arguments, endpoint):
            return {"quotes": [{"symbol": symbol, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1, "date": "2026-10-08"} for symbol in arguments["symbols"]]}

        with patch("streamlit_data.call_nse_tool", side_effect=quote_response):
            rows = fetch_quotes(constituents)
        self.assertEqual(len(rows), 200)
        self.assertEqual({row["symbol"] for row in rows}, {item["symbol"] for item in constituents})

    def test_history_merges_paginated_rows(self):
        responses = [
            {"data": [{"date": "2026-10-08", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1}], "next_end_date": "2026-07-01"},
            {"data": [{"date": "2026-07-01", "open": 98, "high": 100, "low": 97, "close": 99, "volume": 1}, {"date": "2026-10-08", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1}]},
        ]
        with patch("streamlit_data.call_nse_tool", side_effect=responses):
            rows = fetch_history("TEST", 6)
        self.assertEqual([row["date"] for row in rows], ["2026-07-01", "2026-10-08"])

    def test_history_rejects_untrusted_symbol(self):
        with self.assertRaises(ValueError):
            fetch_history("RELIANCE/../../", 3)


if __name__ == "__main__":
    unittest.main()
