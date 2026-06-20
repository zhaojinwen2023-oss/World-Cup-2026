from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from build_champion_predictions import canonical_team, is_finished, tournament_teams
from build_team_strength_ratings import is_eligible_match


ROOT = Path(__file__).resolve().parents[1]
OVERRIDABLE_COLUMNS = ("fifa_rank", "elo", "attack_strength", "defense_strength", "form_score")


def parse_time(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True, errors="coerce")


def normalized_result_rows(history: dict, app_data: dict) -> list[dict]:
    rows = []
    for match in history.get("matches") or []:
        if not is_eligible_match(match):
            continue
        home = canonical_team(match.get("home_team"))
        away = canonical_team(match.get("away_team"))
        if not home or not away:
            continue
        rows.append({
            "date": parse_time(match.get("date")),
            "home_team": home,
            "away_team": away,
            "home_score": int(match.get("home_score", 0)),
            "away_score": int(match.get("away_score", 0)),
            "competition": str(match.get("competition") or ""),
            "current_world_cup": False,
        })
    for match in app_data.get("matches") or []:
        if not is_finished(match):
            continue
        home = canonical_team(match.get("home_team"))
        away = canonical_team(match.get("away_team"))
        if not home or not away:
            continue
        rows.append({
            "date": parse_time(match.get("kickoff_utc")),
            "home_team": home,
            "away_team": away,
            "home_score": int(match.get("home_score", 0)),
            "away_score": int(match.get("away_score", 0)),
            "competition": "FIFA World Cup 2026",
            "current_world_cup": True,
        })
    return [row for row in rows if not pd.isna(row["date"])]


def team_results(team: str, rows: list[dict]) -> list[dict]:
    results = []
    for row in rows:
        if row["home_team"] == team:
            goals_for, goals_against = row["home_score"], row["away_score"]
        elif row["away_team"] == team:
            goals_for, goals_against = row["away_score"], row["home_score"]
        else:
            continue
        points = 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0
        results.append({**row, "goals_for": goals_for, "goals_against": goals_against, "points": points})
    return sorted(results, key=lambda item: item["date"])[-20:]


def weighted_average(values: np.ndarray, weights: np.ndarray, fallback: float) -> float:
    total = float(weights.sum())
    return float(np.dot(values, weights) / total) if total > 0 else fallback


def read_overrides(path: Path | None) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame(columns=("team", *OVERRIDABLE_COLUMNS)).set_index("team")
    frame = pd.read_csv(path)
    if "team" not in frame.columns:
        raise ValueError(f"手动指标文件缺少 team 列: {path}")
    frame["team"] = frame["team"].map(canonical_team)
    return frame.set_index("team")


def build_team_features(history: dict, ratings: dict, app_data: dict, overrides_path: Path | None = None) -> pd.DataFrame:
    rows = normalized_result_rows(history, app_data)
    teams = tournament_teams(app_data.get("matches") or [])
    rating_details = ratings.get("details") or {}
    rating_scores = ratings.get("teams") or {}
    if not teams:
        raise ValueError("无法从 app_data.json 识别世界杯参赛队")
    if not rows:
        raise ValueError("没有可用于球队指标计算的历史赛果")

    average_goals = sum(row["home_score"] + row["away_score"] for row in rows) / (len(rows) * 2)
    as_of = max(row["date"] for row in rows)
    overrides = read_overrides(overrides_path)
    output = []
    for team in teams:
        recent = team_results(team, rows)
        if recent:
            ages = np.array([(as_of - row["date"]).total_seconds() / 86400 for row in recent], dtype=float)
            weights = np.power(0.5, np.maximum(ages, 0) / 180.0)
            weights *= np.array([1.2 if row["current_world_cup"] else 1.0 for row in recent], dtype=float)
            goals_for = np.array([row["goals_for"] for row in recent], dtype=float)
            goals_against = np.array([row["goals_against"] for row in recent], dtype=float)
            points = np.array([row["points"] for row in recent], dtype=float)
            weighted_for = weighted_average(goals_for, weights, average_goals)
            weighted_against = weighted_average(goals_against, weights, average_goals)
            form_score = weighted_average(points / 3.0, weights, 0.5)
        else:
            weights = np.array([], dtype=float)
            weighted_for = weighted_against = average_goals
            form_score = 0.5
        shrinkage = 5.0
        effective_matches = float(weights.sum())
        attack_strength = (weighted_for * effective_matches + average_goals * shrinkage) / ((effective_matches + shrinkage) * average_goals)
        defense_strength = (weighted_against * effective_matches + average_goals * shrinkage) / ((effective_matches + shrinkage) * average_goals)
        details = rating_details.get(team) or {}
        elo = float(details.get("elo") or (1500 + (float(rating_scores.get(team, 75)) - 75) * 10))
        wins = sum(row["points"] == 3 for row in recent)
        draws = sum(row["points"] == 1 for row in recent)
        losses = sum(row["points"] == 0 for row in recent)
        item = {
            "team": team,
            "fifa_rank": np.nan,
            "elo": round(elo, 1),
            "strength_score": int(round(float(rating_scores.get(team, 75)))),
            "last20_played": len(recent),
            "last20_wins": wins,
            "last20_draws": draws,
            "last20_losses": losses,
            "last20_goals_for": sum(row["goals_for"] for row in recent),
            "last20_goals_against": sum(row["goals_against"] for row in recent),
            "attack_strength": round(float(np.clip(attack_strength, 0.55, 1.65)), 4),
            "defense_strength": round(float(np.clip(defense_strength, 0.55, 1.65)), 4),
            "form_score": round(float(np.clip(form_score, 0.0, 1.0)), 4),
            "data_as_of": as_of.isoformat(),
        }
        if team in overrides.index:
            override = overrides.loc[team]
            if isinstance(override, pd.DataFrame):
                override = override.iloc[-1]
            for column in OVERRIDABLE_COLUMNS:
                if column in override and pd.notna(override[column]):
                    item[column] = float(override[column])
        output.append(item)
    return pd.DataFrame(output).sort_values("team").reset_index(drop=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_feature_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
