from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from schedule_utils import (
    default_live_results_path,
    default_standings_path,
    default_static_schedule_path,
    load_live_results,
    load_static_schedule,
    normalize_status,
    safe_int,
    static_away,
    static_home,
    write_json,
)


def finished_with_score(result: dict) -> bool:
    return normalize_status(result.get("status")) == "finished" and str(result.get("home_score", "")).strip() != "" and str(result.get("away_score", "")).strip() != ""


def empty_row(group: str, team: str) -> dict:
    return {
        "group": group,
        "team": team,
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "goals_for": 0,
        "goals_against": 0,
        "goal_difference": 0,
        "points": 0,
        "fair_play_points": 0,
        "rank": 0,
        "qualified_status": "unknown",
    }


def apply_match(home: dict, away: dict, home_score: int, away_score: int) -> None:
    home["played"] += 1
    away["played"] += 1
    home["goals_for"] += home_score
    home["goals_against"] += away_score
    away["goals_for"] += away_score
    away["goals_against"] += home_score
    home["goal_difference"] = home["goals_for"] - home["goals_against"]
    away["goal_difference"] = away["goals_for"] - away["goals_against"]
    if home_score > away_score:
        home["won"] += 1
        away["lost"] += 1
        home["points"] += 3
    elif away_score > home_score:
        away["won"] += 1
        home["lost"] += 1
        away["points"] += 3
    else:
        home["drawn"] += 1
        away["drawn"] += 1
        home["points"] += 1
        away["points"] += 1


def rank_rows(rows: list[dict]) -> list[dict]:
    rows.sort(
        key=lambda row: (
            -row["points"],
            -row["goal_difference"],
            -row["goals_for"],
            row["fair_play_points"],
            row["team"],
        )
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def calculate_standings(static_path: Path, live_path: Path) -> dict:
    static_rows = load_static_schedule(static_path)
    live = load_live_results(live_path)
    live_by_id = live["by_id"]
    groups: dict[str, dict[str, dict]] = defaultdict(dict)
    group_match_counts: dict[str, int] = defaultdict(int)
    group_finished_counts: dict[str, int] = defaultdict(int)

    for _, row in static_rows.iterrows():
        if row["stage"] != "Group Stage":
            continue
        group = str(row["group"]).strip().upper()
        home = static_home(row)
        away = static_away(row)
        group_match_counts[group] += 1
        groups[group].setdefault(home, empty_row(group, home))
        groups[group].setdefault(away, empty_row(group, away))
        result = live_by_id.get(safe_int(row["match_id"]), {})
        if finished_with_score(result):
            group_finished_counts[group] += 1
            apply_match(groups[group][home], groups[group][away], safe_int(result["home_score"]), safe_int(result["away_score"]))

    ranked: list[dict] = []
    third_rows: list[dict] = []
    all_group_matches_finished = bool(group_match_counts) and all(group_finished_counts[group] == total for group, total in group_match_counts.items())

    for group in sorted(groups):
        rows = rank_rows(list(groups[group].values()))
        group_complete = group_finished_counts[group] == group_match_counts[group]
        for row in rows:
            if group_complete:
                if row["rank"] <= 2:
                    row["qualified_status"] = "qualified"
                elif row["rank"] == 3:
                    row["qualified_status"] = "possible"
                else:
                    row["qualified_status"] = "eliminated"
            else:
                row["qualified_status"] = "possible"
            if row["rank"] == 3:
                third_rows.append(row)
        ranked.extend(rows)

    third_rows.sort(key=lambda row: (-row["points"], -row["goal_difference"], -row["goals_for"], row["fair_play_points"], row["team"]))
    for index, row in enumerate(third_rows, start=1):
        row["best_third_rank"] = index
        if all_group_matches_finished:
            row["qualified_status"] = "qualified" if index <= 8 else "eliminated"

    return {
        "last_updated": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "standings": ranked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate group standings from static schedule and live results.")
    parser.add_argument("--static", type=Path, default=default_static_schedule_path(), help="static_schedule.csv 路径")
    parser.add_argument("--live", type=Path, default=default_live_results_path(), help="live_results.json 路径")
    parser.add_argument("--output", type=Path, default=default_standings_path(), help="standings.json 输出路径")
    args = parser.parse_args()
    payload = calculate_standings(args.static, args.live)
    write_json(args.output, payload)
    print(f"已计算积分榜: {args.output} ({len(payload['standings'])} 队)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
