from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_champion_predictions import build_predictions, should_update  # noqa: E402


BEIJING = ZoneInfo("Asia/Shanghai")


def match(
    match_id: int,
    home: str,
    away: str,
    *,
    stage: str = "Group Stage",
    status: str = "scheduled",
    home_score: int | str = "",
    away_score: int | str = "",
    winner: str = "",
    loser: str = "",
) -> dict:
    return {
        "match_id": match_id,
        "stage": stage,
        "home_team": home,
        "away_team": away,
        "status": status,
        "is_finished": status == "finished",
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
        "loser": loser,
        "kickoff_utc": f"2026-06-{10 + match_id:02d}T18:00:00Z",
    }


class ChampionPredictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seed = {
            "version": "test-v1",
            "as_of": "2026-06-01",
            "source_label": "测试实力种子",
            "teams": {"Alpha": 90, "Bravo": 84, "Charlie": 78, "Delta": 72},
        }
        self.base_matches = [
            match(1, "Alpha", "Bravo"),
            match(2, "Charlie", "Delta"),
        ]
        self.generated_at = datetime(2026, 6, 20, 14, 0, tzinfo=BEIJING)

    def app_data(self, matches: list[dict], standings: list[dict] | None = None) -> dict:
        return {
            "generated_at": "2026-06-20T06:00:00Z",
            "live_last_updated": "2026-06-20T05:58:00Z",
            "matches": matches,
            "standings": standings or [],
        }

    def test_probabilities_sum_to_one_hundred(self) -> None:
        payload = build_predictions(self.app_data(self.base_matches), self.seed, self.generated_at, top_count=3)

        total = sum(row["champion_probability"] for row in payload["teams"]) + payload["other_probability"]
        self.assertEqual(total, 100.0)
        self.assertEqual(payload["teams"][0]["team"], "Alpha")
        self.assertEqual(payload["status"], "model")

    def test_latest_results_change_form_and_probability(self) -> None:
        finished = [
            match(1, "Alpha", "Bravo", status="finished", home_score=3, away_score=0, winner="Alpha", loser="Bravo"),
            match(2, "Charlie", "Delta"),
        ]
        payload = build_predictions(self.app_data(finished), self.seed, self.generated_at, top_count=4)
        by_team = {row["team"]: row for row in payload["teams"]}

        self.assertGreater(by_team["Alpha"]["form_score"], by_team["Bravo"]["form_score"])
        self.assertGreater(by_team["Alpha"]["champion_probability"], by_team["Bravo"]["champion_probability"])
        self.assertIn("1胜0平0负", by_team["Alpha"]["summary"])

    def test_knockout_loser_has_zero_probability(self) -> None:
        matches = self.base_matches + [
            match(3, "Alpha", "Bravo", stage="Round of 32", status="finished", home_score=1, away_score=0, winner="Alpha", loser="Bravo")
        ]
        payload = build_predictions(self.app_data(matches), self.seed, self.generated_at, top_count=4)
        by_team = {row["team"]: row for row in payload["teams"]}

        self.assertEqual(by_team["Bravo"]["champion_probability"], 0.0)
        self.assertGreater(by_team["Alpha"]["path_score"], 50)

    def test_daily_gate_updates_once_after_fourteen(self) -> None:
        previous = {"status": "model", "generated_at": "2026-06-19T14:05:00+08:00"}
        before = datetime(2026, 6, 20, 13, 59, tzinfo=BEIJING)
        after = datetime(2026, 6, 20, 14, 1, tzinfo=BEIJING)

        self.assertFalse(should_update(previous, before, 14, False)[0])
        self.assertTrue(should_update(previous, after, 14, False)[0])
        today = {"status": "model", "generated_at": "2026-06-20T14:00:00+08:00"}
        self.assertFalse(should_update(today, after, 14, False)[0])
        self.assertTrue(should_update(today, before, 14, True)[0])


if __name__ == "__main__":
    unittest.main()
