import unittest

from market_mood import _daily_mmi_series, mmi_zone


class MarketMoodTests(unittest.TestCase):
    def test_finds_server_rendered_daily_series(self):
        payload = {"props": {"pageProps": {"dehydratedState": {"queries": [{"state": {"data": {"periodicDailyMMI": [{"date": "2026-10-09T14:20:00.000Z", "indicator": 20.25}]}}}]}}}}
        self.assertEqual(_daily_mmi_series(payload), [{"date": "2026-10-09T14:20:00.000Z", "indicator": 20.25}])

    def test_uses_four_display_zones(self):
        self.assertEqual(mmi_zone(20)[0], "Extreme fear")
        self.assertEqual(mmi_zone(30)[0], "Fear")
        self.assertEqual(mmi_zone(50)[0], "Greed")
        self.assertEqual(mmi_zone(71)[0], "Extreme greed")


if __name__ == "__main__":
    unittest.main()
