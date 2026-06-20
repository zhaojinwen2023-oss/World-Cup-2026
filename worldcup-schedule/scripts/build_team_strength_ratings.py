from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INITIAL_ELO = 1500.0
K_FACTOR = 32.0
HALF_LIFE_DAYS = 365.0
MAJOR_TOURNAMENTS = (
    "world cup",
    "euro championship",
    "european championship",
    "copa america",
    "africa cup of nations",
    "asian cup",
    "gold cup",
    "ofc nations cup",
)
EXCLUDED_COMPETITIONS = (
    "african nations championship",
    "arab cup",
    "olympic",
    "u17",
    "u20",
    "u21",
    "u23",
)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def parse_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"比赛时间缺少时区: {value}")
    return parsed


def competition_weight(name: str, round_name: str = "") -> tuple[float, str]:
    text = f"{name} {round_name}".lower()
    if "friendl" in text:
        return 0.35, "友谊赛"
    if "nations league" in text:
        return 0.75, "国家联赛"
    if any(word in text for word in ("qualif", "preliminary")):
        return 0.85, "大赛预选赛"
    if any(name_part in text for name_part in MAJOR_TOURNAMENTS):
        return 1.0, "国际大赛正赛"
    return 0.65, "其他国际赛事"


def is_eligible_match(match: dict) -> bool:
    competition = str(match.get("competition") or "").lower()
    return not any(excluded in competition for excluded in EXCLUDED_COMPETITIONS)


def recency_weight(match_time: datetime, as_of: datetime, half_life_days: float = HALF_LIFE_DAYS) -> float:
    age_days = max(0.0, (as_of - match_time).total_seconds() / 86400)
    return 0.5 ** (age_days / half_life_days)


def expected_score(team_elo: float, opponent_elo: float) -> float:
    return 1.0 / (1.0 + 10 ** ((opponent_elo - team_elo) / 400.0))


def actual_scores(home_score: int, away_score: int) -> tuple[float, float]:
    if home_score > away_score:
        return 1.0, 0.0
    if away_score > home_score:
        return 0.0, 1.0
    return 0.5, 0.5


def goal_margin_multiplier(home_score: int, away_score: int) -> float:
    margin = abs(home_score - away_score)
    return 1.0 + min(max(margin - 1, 0), 3) * 0.15


def calculate_ratings(history: dict) -> dict:
    input_matches = sorted(history.get("matches") or [], key=lambda row: (row.get("date", ""), row.get("fixture_id", 0)))
    matches = [match for match in input_matches if is_eligible_match(match)]
    target_teams = set((history.get("team_ids") or {}).keys())
    if not matches or not target_teams:
        raise ValueError("历史赛果或目标球队为空")
    as_of = datetime.fromisoformat(f"{history['window']['end']}T23:59:59+00:00")
    ratings: defaultdict[str, float] = defaultdict(lambda: INITIAL_ELO)
    stats: defaultdict[str, dict] = defaultdict(lambda: {"played": 0, "won": 0, "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0, "weighted_matches": 0.0})

    for match in matches:
        home = str(match.get("home_team") or "").strip()
        away = str(match.get("away_team") or "").strip()
        if not home or not away:
            continue
        home_goals = int(match["home_score"])
        away_goals = int(match["away_score"])
        home_actual, away_actual = actual_scores(home_goals, away_goals)
        match_time = parse_datetime(match["date"])
        tournament_weight, category = competition_weight(str(match.get("competition") or ""), str(match.get("round") or ""))
        time_weight = recency_weight(match_time, as_of)
        effective_k = K_FACTOR * tournament_weight * time_weight * goal_margin_multiplier(home_goals, away_goals)
        home_expected = expected_score(ratings[home], ratings[away])
        delta = effective_k * (home_actual - home_expected)
        ratings[home] += delta
        ratings[away] -= delta

        for team, goals_for, goals_against, actual in (
            (home, home_goals, away_goals, home_actual),
            (away, away_goals, home_goals, away_actual),
        ):
            row = stats[team]
            row["played"] += 1
            row["won"] += actual == 1.0
            row["drawn"] += actual == 0.5
            row["lost"] += actual == 0.0
            row["goals_for"] += goals_for
            row["goals_against"] += goals_against
            row["weighted_matches"] += tournament_weight * time_weight
            row.setdefault("competition_categories", defaultdict(int))[category] += 1

    details = {}
    strength_scores = {}
    for team in sorted(target_teams):
        strength_score = round(clamp(75 + (ratings[team] - INITIAL_ELO) / 10, 45, 95))
        row = dict(stats[team])
        categories = row.pop("competition_categories", {})
        row["weighted_matches"] = round(float(row["weighted_matches"]), 2)
        row["goal_difference"] = row["goals_for"] - row["goals_against"]
        details[team] = {
            "strength_score": strength_score,
            "elo": round(ratings[team], 1),
            **row,
            "competition_categories": dict(sorted(categories.items())),
        }
        strength_scores[team] = strength_score

    return {
        "version": "historical-elo-v1",
        "as_of": history["window"]["end"],
        "source_label": "过去24个月国际比赛时间衰减 Elo",
        "note": "由可追溯历史赛果自动计算；本届世界杯比赛由每日预测模型另行更新，避免重复计权。",
        "methodology": {
            "initial_elo": INITIAL_ELO,
            "k_factor": K_FACTOR,
            "recency_half_life_days": HALF_LIFE_DAYS,
            "competition_weights": {"国际大赛正赛": 1.0, "大赛预选赛": 0.85, "国家联赛": 0.75, "其他国际赛事": 0.65, "友谊赛": 0.35},
            "normalization": "固定标尺：Elo 1500对应75分，每增加100 Elo增加10分，限制在45-95分",
            "excluded_competitions": list(EXCLUDED_COMPETITIONS),
        },
        "source": {
            "provider": history.get("source", ""),
            "path": "data/historical_results.json",
            "window": history.get("window", {}),
            "input_match_count": len(input_matches),
            "match_count": len(matches),
            "excluded_match_count": len(input_matches) - len(matches),
        },
        "teams": strength_scores,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="根据过去24个月国家队赛果生成时间衰减 Elo 实力评分。")
    parser.add_argument("--history", type=Path, default=ROOT / "data" / "historical_results.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "team_strength_ratings.json")
    args = parser.parse_args()

    history = json.loads(args.history.read_text(encoding="utf-8"))
    payload = calculate_ratings(history)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成客观实力评分: {args.output} ({len(payload['teams'])} 支球队，{payload['source']['match_count']} 场历史比赛)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
