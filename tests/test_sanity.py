from __future__ import annotations

import unittest

from src.battle.sim.sanity import run_sanity_checks


class SanityBatteryTest(unittest.TestCase):
    def test_all_checks_pass(self) -> None:
        checks = run_sanity_checks(games=60, seed=1)
        self.assertEqual(len(checks), 6)
        failed = [check["name"] for check in checks if not check["passed"]]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
