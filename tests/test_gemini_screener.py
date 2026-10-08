import unittest

from gemini_screener import GeminiScreenerError, validate_chart_cues, validate_gemini_screen, validate_research_comparison, validate_research_shortlist


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

    def test_shortlist_rejects_symbol_outside_screen(self):
        payload = {"candidates": [{"symbol": "OUTSIDE", "screen_evidence": "P/E is shown in the supplied screen.", "counterpoint": "ROE is missing.", "next_step": "Open the chart."}]}
        with self.assertRaises(GeminiScreenerError):
            validate_research_shortlist(payload, {"RELIANCE", "TCS"})

    def test_comparison_requires_every_selected_symbol(self):
        payload = {
            "commonalities": ["Both appear in the supplied screen."],
            "differences": ["Their displayed day moves differ."],
            "data_gaps": ["No earnings estimate is supplied."],
            "checks_by_symbol": [{"symbol": "TCS", "checks": ["Open the chart."]}],
        }
        with self.assertRaises(GeminiScreenerError):
            validate_research_comparison(payload, {"TCS", "RELIANCE"})

    def test_rejects_recommendation_like_research_output(self):
        with self.assertRaises(GeminiScreenerError):
            validate_chart_cues({"observations": ["Buy this stock."], "confirmation_checks": ["Check volume."], "limitations": ["EOD data only."]})


if __name__ == "__main__":
    unittest.main()
