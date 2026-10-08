import base64
import json
import unittest
import zlib

from watchlist_service import MAX_WATCHLIST_ITEMS, WatchlistError, add_to_watchlist, create_watchlist, decode_shared_watchlist, default_watchlists, encode_shared_watchlist, import_shared_watchlist, normalize_watchlists, remove_from_watchlist


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

    def test_shared_watchlist_round_trip_keeps_name_and_symbols(self):
        payload = encode_shared_watchlist("Bank research", ["HDFCBANK", "SBIN"])
        self.assertEqual(decode_shared_watchlist(payload, {"HDFCBANK", "SBIN"}), ("Bank research", ["HDFCBANK", "SBIN"]))

    def test_shared_watchlist_rejects_bad_or_unsupported_payloads(self):
        with self.assertRaises(WatchlistError):
            decode_shared_watchlist("not-a-payload", {"TCS"})
        unsupported = base64.urlsafe_b64encode(zlib.compress(json.dumps({"v": 99, "n": "A", "s": ["TCS"]}).encode("utf-8"))).decode("ascii").rstrip("=")
        with self.assertRaises(WatchlistError):
            decode_shared_watchlist(unsupported, {"TCS"})

    def test_shared_import_discards_unknown_symbols_and_uses_unique_name(self):
        payload = encode_shared_watchlist("Banks", ["HDFCBANK", "OLD", "SBIN"])
        state = {"active": "Banks (shared)", "lists": {"Banks (shared)": ["TCS"]}}
        imported = import_shared_watchlist(state, payload, {"HDFCBANK", "SBIN", "TCS"})
        self.assertEqual(imported["active"], "Banks (shared) (2)")
        self.assertEqual(imported["lists"]["Banks (shared) (2)"], ["HDFCBANK", "SBIN"])


if __name__ == "__main__":
    unittest.main()
