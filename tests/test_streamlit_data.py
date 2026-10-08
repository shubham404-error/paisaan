import unittest
from unittest.mock import patch

from streamlit_data import fetch_quotes


class StreamlitDataTests(unittest.TestCase):
    def test_quotes_preserve_only_verified_constituents(self):
        constituents = [{"symbol": f"SYM{index}", "company": "Company", "industry": "Industry"} for index in range(200)]

        def quote_response(tool, arguments, endpoint):
            return {"quotes": [{"symbol": symbol, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1, "date": "2026-10-08"} for symbol in arguments["symbols"]]}

        with patch("streamlit_data.call_nse_tool", side_effect=quote_response):
            rows = fetch_quotes(constituents)
        self.assertEqual(len(rows), 200)
        self.assertEqual({row["symbol"] for row in rows}, {item["symbol"] for item in constituents})

if __name__ == "__main__":
    unittest.main()
