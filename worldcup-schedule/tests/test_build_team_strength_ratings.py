from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_team_strength_ratings import calculate_ratings, competition_weight, recency_weight  # noqa: E402


def historical_match(
    fixture_id: int,
    date: str,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    competition: str = "FIFA World Cup Qualification",
) -> dict:
    return {
        "fixture_id": fixture_id,
        "date": date,
        "competition": competition,
        "round": "Group Stage",
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
    }


class TeamStrengthRatingTests(unittest.TestCase):
    def test_recent_competitive_results_produce_higher_rating(self) -> None:
        history = {
            "source": "test",
            "window": {"start": "2024-06-10", "end": "2026-06-10", "days": 730},
            "team_ids": {"Alpha": 1, "Bravo": 2, "Charlie": 3},
            "matches": [
                historical_match(1, "2025-09-01T18:00:00+00:00", "Alpha", "Bravo", 2, 0),
                historical_match(2, "2026-03-01T18:00:00+00:00", "Alpha", "Charlie", 3, 1),
                historical_match(3, "2026-05-01T18:00:00+00:00", "Bravo", "Charlie", 1, 0),
            ],
        }

        payload = calculate_ratings(history)

        self.assertGreater(payload["details"]["Alpha"]["elo"], payload["details"]["Bravo"]["elo"])
        self.assertGreater(payload["teams"]["Alpha"], payload["teams"]["Charlie"])
        self.assertEqual(payload["source"]["match_count"], 3)
        self.assertEqual(payload["details"]["Alpha"]["played"], 2)

    def test_match_weights_are_explicit_and_time_decayed(self) -> None:
        self.assertEqual(competition_weight("International Friendlies")[0], 0.35)
        self.assertEqual(competition_weight("FIFA World Cup")[0], 1.0)
        as_of = datetime.fromisoformat("2026-06-10T23:59:59+00:00")
        recent = recency_weight(datetime.fromisoformat("2026-05-10T18:00:00+00:00"), as_of)
        old = recency_weight(datetime.fromisoformat("2024-06-10T18:00:00+00:00"), as_of)
        self.assertGreater(recent, old)

    def test_strength_scores_are_bounded(self) -> None:
        history = {
            "source": "test",
            "window": {"start": "2024-06-10", "end": "2026-06-10", "days": 730},
            "team_ids": {"Alpha": 1, "Bravo": 2},
            "matches": [historical_match(1, "2026-05-01T18:00:00+00:00", "Alpha", "Bravo", 8, 0)],
        }

        payload = calculate_ratings(history)

        self.assertTrue(all(45 <= score <= 95 for score in payload["teams"].values()))

    def test_non_senior_competitions_are_excluded(self) -> None:
        history = {
            "source": "test",
            "window": {"start": "2024-06-10", "end": "2026-06-10", "days": 730},
            "team_ids": {"Alpha": 1, "Bravo": 2},
            "matches": [
                historical_match(1, "2026-04-01T18:00:00+00:00", "Alpha", "Bravo", 1, 0),
                historical_match(2, "2026-05-01T18:00:00+00:00", "Alpha", "Bravo", 8, 0, "African Nations Championship"),
            ],
        }

        payload = calculate_ratings(history)

        self.assertEqual(payload["source"]["input_match_count"], 2)
        self.assertEqual(payload["source"]["match_count"], 1)
        self.assertEqual(payload["source"]["excluded_match_count"], 1)


if __name__ == "__main__":
    unittest.main()
