import unittest
from unittest.mock import patch

from gemini_screener import GeminiScreenerError, ask_stock_comparison, validate_chart_cues, validate_gemini_screen, validate_research_comparison, validate_research_shortlist


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
            "decision_lenses": [{"dimension": "valuation", "symbols": ["TCS"], "takeaway": "Only TCS is covered."}],
            "data_gaps": ["No earnings estimate is supplied."],
            "research_actions": [{"symbol": "TCS", "focus": "fundamentals", "question": "Review valuation.", "reason": "A comparison needs both symbols."}],
        }
        with self.assertRaises(GeminiScreenerError):
            validate_research_comparison(payload, {"TCS", "RELIANCE"})

    def test_accepts_actionable_comparison_contract(self):
        payload = {
            "decision_lenses": [{"dimension": "valuation", "symbols": ["TCS", "RELIANCE"], "takeaway": "Compare the available P/E and P/B fields before treating the screen as a valuation thesis."}],
            "data_gaps": ["The supplied packet does not contain earnings-growth estimates."],
            "research_actions": [
                {"symbol": "TCS", "focus": "chart", "question": "Does the selected chart window show price holding above the displayed moving averages?", "reason": "Use the chart to test whether the current screen result has technical confirmation."},
                {"symbol": "RELIANCE", "focus": "disclosures", "question": "Which recent company disclosure could explain the screen result?", "reason": "The packet does not include company-specific events."},
            ],
        }
        comparison = validate_research_comparison(payload, {"TCS", "RELIANCE"})
        self.assertEqual(comparison["research_actions"][0]["focus"], "chart")

    def test_rejects_recommendation_like_research_output(self):
        with self.assertRaises(GeminiScreenerError):
            validate_chart_cues({"observations": ["Buy this stock."], "confirmation_checks": ["Check volume."], "limitations": ["EOD data only."]})

    def test_comparison_chat_uses_selected_yahoo_fact_packet(self):
        facts = {"source": "Yahoo Finance daily EOD data", "stocks": [{"symbol": "TCS", "pe": 25}, {"symbol": "RELIANCE", "pe": 20}]}
        with patch("gemini_screener._generate_text", return_value="Reliance has the lower supplied P/E; compare it with your quality priority.") as generate:
            answer = ask_stock_comparison("Which has the lower valuation?", facts, [], "test-key")
        self.assertIn("Reliance", answer)
        self.assertIn("TCS", generate.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
