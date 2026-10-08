import unittest

from watchlist_service import MAX_WATCHLIST_ITEMS, WatchlistError, add_to_watchlist, create_watchlist, default_watchlists, normalize_watchlists, remove_from_watchlist


class WatchlistServiceTests(unittest.TestCase):
    def test_creates_adds_and_removes_items(self):
        state = create_watchlist(default_watchlists(), "Banks")
        state = add_to_watchlist(state, "Banks", ["HDFCBANK", "SBIN"], {"HDFCBANK", "SBIN"})
        self.assertEqual(state["lists"]["Banks"], ["HDFCBANK", "SBIN"])
        self.assertEqual(remove_from_watchlist(state, "Banks", ["SBIN"])["lists"]["Banks"], ["HDFCBANK"])

    def test_enforces_item_limit(self):
        symbols = [f"S{index}" for index in range(MAX_WATCHLIST_ITEMS + 1)]
        with self.assertRaises(WatchlistError):
            add_to_watchlist({"active": "A", "lists": {"A": []}}, "A", symbols, set(symbols))

    def test_import_drops_symbols_outside_current_universe(self):
        state = normalize_watchlists({"active": "A", "lists": {"A": ["TCS", "OLD", "TCS"]}}, {"TCS"})
        self.assertEqual(state["lists"]["A"], ["TCS"])


if __name__ == "__main__":
    unittest.main()
