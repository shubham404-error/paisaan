import unittest
from unittest.mock import patch

from refresh_control import RefreshGate


class RefreshGateTests(unittest.TestCase):
    @patch("refresh_control.monotonic", side_effect=[100.0, 100.0, 115.0, 131.0, 131.0])
    def test_refresh_is_throttled_for_the_cooldown_window(self, _clock):
        gate = RefreshGate(cooldown_seconds=30)
        self.assertEqual(gate.request(), (True, 0))
        self.assertEqual(gate.request(), (False, 15))
        self.assertEqual(gate.request(), (True, 0))
