from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from resolve_knockout import assign_third_sources, resolve_third_source  # noqa: E402


def third(group: str, team: str, rank: int) -> dict:
    return {
        "group": group,
        "team": team,
        "played": 3,
        "best_third_rank": rank,
        "best_third_qualified": True,
    }


class ResolveKnockoutTests(unittest.TestCase):
    def test_third_place_assignment_does_not_reuse_team(self) -> None:
        slots = {
            (74, "away"): ("A", "B", "C", "D", "F"),
            (77, "away"): ("C", "D", "F", "G", "H"),
        }
        thirds = [
            third("F", "Sweden", 1),
            third("C", "Morocco", 2),
        ]

        assignment = assign_third_sources(thirds, slots)

        teams = [row["team"] for row in assignment.values()]
        self.assertEqual(len(assignment), len(slots))
        self.assertEqual(len(set(teams)), len(teams))
        self.assertIn("Sweden", teams)

    def test_third_place_source_stays_pending_without_complete_assignment(self) -> None:
        team, resolved = resolve_third_source("3rd Group C/D/F/G/H")

        self.assertEqual(team, "待定：C/D/F/G/H组第三之一")
        self.assertFalse(resolved)


if __name__ == "__main__":
    unittest.main()
