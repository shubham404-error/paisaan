import unittest

from universe_taxonomy import deterministic_scope, taxonomy_records


class UniverseTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.records = taxonomy_records([
            {"Symbol": "HDFCBANK", "Company": "HDFC Bank Ltd.", "Industry": "Financial Services"},
            {"Symbol": "FEDERALBNK", "Company": "Federal Bank Ltd.", "Industry": "Financial Services"},
            {"Symbol": "SBIN", "Company": "State Bank of India", "Industry": "Financial Services"},
            {"Symbol": "INFY", "Company": "Infosys Ltd.", "Industry": "Information Technology"},
        ])

    def test_private_bank_scope_is_complete_and_deterministic(self):
        symbols, label = deterministic_scope("private banks with PE below 15", self.records)
        self.assertEqual(symbols, ["HDFCBANK", "FEDERALBNK"])
        self.assertEqual(label, "private bank")

    def test_industry_scope_is_available_without_company_guessing(self):
        symbols, label = deterministic_scope("technology companies with PE below 25", self.records)
        self.assertEqual(symbols, ["INFY"])
        self.assertEqual(label, "information technology")


if __name__ == "__main__":
    unittest.main()
