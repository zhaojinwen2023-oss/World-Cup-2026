from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

try:
    from scipy.stats import poisson as scipy_poisson
except ImportError:  # pragma: no cover - GitHub Actions installs scipy; local fallback remains deterministic.
    scipy_poisson = None


HOST_COUNTRIES = {"Mexico": "Mexico", "Canada": "Canada", "USA": "United States"}


@dataclass(frozen=True)
class ExpectedGoals:
    home: float
    away: float


class MatchPredictionModel:
    def __init__(self, features: pd.DataFrame, base_goals: float = 1.28, max_goals: int = 8):
        self.features = features.set_index("team").to_dict("index")
        self.base_goals = base_goals
        self.max_goals = max_goals

    def rating(self, team: str) -> float:
        row = self.features[team]
        elo = float(row["elo"])
        fifa_rank = row.get("fifa_rank")
        if fifa_rank is None or pd.isna(fifa_rank):
            return elo
        fifa_equivalent = 1800 - min(max(float(fifa_rank), 1), 210) * 7.0
        return elo * 0.85 + fifa_equivalent * 0.15

    def expected_goals(self, home: str, away: str, country: str = "", neutral: bool = True) -> ExpectedGoals:
        home_row = self.features[home]
        away_row = self.features[away]
        rating_difference = self.rating(home) - self.rating(away)
        home_rating_factor = math.exp(rating_difference / 900.0)
        away_rating_factor = math.exp(-rating_difference / 900.0)
        home_form = 0.9 + float(home_row["form_score"]) * 0.2
        away_form = 0.9 + float(away_row["form_score"]) * 0.2
        home_lambda = self.base_goals * float(home_row["attack_strength"]) * float(away_row["defense_strength"]) * home_rating_factor * home_form
        away_lambda = self.base_goals * float(away_row["attack_strength"]) * float(home_row["defense_strength"]) * away_rating_factor * away_form

        host_team = HOST_COUNTRIES.get(country)
        if host_team == home:
            home_lambda *= 1.12
            away_lambda *= 0.96
        elif host_team == away:
            away_lambda *= 1.12
            home_lambda *= 0.96
        elif not neutral:
            home_lambda *= 1.07
        return ExpectedGoals(round(float(np.clip(home_lambda, 0.2, 3.8)), 4), round(float(np.clip(away_lambda, 0.2, 3.8)), 4))

    def poisson_probabilities(self, expected: float) -> np.ndarray:
        goals = np.arange(self.max_goals + 1)
        if scipy_poisson is not None:
            probabilities = scipy_poisson.pmf(goals, expected)
        else:
            probabilities = np.array([math.exp(-expected) * expected**goal / math.factorial(goal) for goal in goals])
        probabilities[-1] += max(0.0, 1.0 - float(probabilities.sum()))
        return probabilities / probabilities.sum()

    def score_matrix(self, home: str, away: str, country: str = "", neutral: bool = True) -> tuple[ExpectedGoals, np.ndarray]:
        expected = self.expected_goals(home, away, country, neutral)
        matrix = np.outer(self.poisson_probabilities(expected.home), self.poisson_probabilities(expected.away))
        return expected, matrix / matrix.sum()

    def predict(self, home: str, away: str, country: str = "", neutral: bool = True) -> dict:
        expected, matrix = self.score_matrix(home, away, country, neutral)
        home_win = float(np.tril(matrix, -1).sum())
        draw = float(np.trace(matrix))
        away_win = float(np.triu(matrix, 1).sum())
        most_likely = np.unravel_index(int(matrix.argmax()), matrix.shape)
        return {
            "home_team": home,
            "away_team": away,
            "expected_home_goals": round(expected.home, 2),
            "expected_away_goals": round(expected.away, 2),
            "home_win_probability": round(home_win * 100, 1),
            "draw_probability": round(draw * 100, 1),
            "away_win_probability": round(away_win * 100, 1),
            "most_likely_score": f"{most_likely[0]}-{most_likely[1]}",
        }

    def score_distribution(self, home: str, away: str, country: str = "") -> np.ndarray:
        return self.score_matrix(home, away, country)[1].reshape(-1)

    def home_advancement_probability(self, home: str, away: str, country: str = "") -> float:
        prediction = self.predict(home, away, country)
        draw = prediction["draw_probability"] / 100
        home_win = prediction["home_win_probability"] / 100
        penalty_edge = 1.0 / (1.0 + math.exp(-(self.rating(home) - self.rating(away)) / 500.0))
        return float(np.clip(home_win + draw * penalty_edge, 0.01, 0.99))

    def sample_knockout_winner(self, home: str, away: str, rng: np.random.Generator, country: str = "") -> tuple[str, str]:
        if rng.random() < self.home_advancement_probability(home, away, country):
            return home, away
        return away, home
