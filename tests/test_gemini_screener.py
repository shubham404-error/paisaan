import unittest

from gemini_screener import GeminiScreenerError, validate_gemini_screen


class GeminiScreenerTests(unittest.TestCase):
    def test_accepts_allowlisted_rules_only(self):
        rules, summary = validate_gemini_screen({"rules": [{"field": "pe", "operator": "<", "value": 25}, {"field": "roe", "operator": ">=", "value": 15}], "summary": "Value and quality screen."})
        self.assertEqual([(rule.field, rule.operator, rule.value) for rule in rules], [("pe", "<", 25.0), ("roe", ">=", 15.0)])
        self.assertEqual(summary, "Value and quality screen.")

    def test_rejects_unavailable_fields(self):
        with self.assertRaises(GeminiScreenerError):
            validate_gemini_screen({"rules": [{"field": "revenue_growth", "operator": ">", "value": 20}], "summary": "bad"})

    def test_rejects_unsafe_values(self):
        with self.assertRaises(GeminiScreenerError):
            validate_gemini_screen({"rules": [{"field": "pe", "operator": "<", "value": -1}], "summary": "bad"})


if __name__ == "__main__":
    unittest.main()
