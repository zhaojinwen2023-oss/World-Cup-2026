from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path

from schedule_utils import (
    default_knockout_bracket_path,
    default_live_results_path,
    default_standings_path,
    default_static_schedule_path,
    load_live_results,
    load_standings,
    load_static_schedule,
    normalize_status,
    safe_int,
    score_display,
    static_away,
    static_home,
    write_json,
)


GROUPS = set("ABCDEFGHIJKL")


def pending_group(group: str, rank: int) -> str:
    rank_name = {1: "第一", 2: "第二", 3: "第三"}.get(rank, f"第{rank}")
    return f"待定：{group}组{rank_name}"


def pending_text(text: str) -> str:
    return text if text.startswith("待定") else f"待定：{text}"


def standings_by_rank(standings: list[dict]) -> dict[tuple[str, int], dict]:
    return {(row["group"], safe_int(row["rank"])): row for row in standings}


def best_thirds(standings: list[dict]) -> list[dict]:
    thirds = [row for row in standings if safe_int(row.get("rank")) == 3]
    thirds.sort(key=lambda row: (-safe_int(row.get("points")), -safe_int(row.get("goal_difference")), -safe_int(row.get("goals_for")), safe_int(row.get("fair_play_points")), row.get("team", "")))
    for index, row in enumerate(thirds, start=1):
        row["best_third_rank"] = index
        row["best_third_qualified"] = row.get("qualified_status") == "qualified" or index <= 8 and row.get("qualified_status") != "eliminated"
    return thirds


def result_winner_loser(result: dict, home_team: str, away_team: str) -> tuple[str, str]:
    winner = str(result.get("winner", "")).strip()
    loser = str(result.get("loser", "")).strip()
    if winner:
        if not loser and home_team and away_team:
            loser = away_team if winner == home_team else home_team
        return winner, loser
    status = normalize_status(result.get("status"))
    if status != "finished":
        return "", ""
    home_score = str(result.get("home_score", "")).strip()
    away_score = str(result.get("away_score", "")).strip()
    if home_score == "" or away_score == "":
        return "", ""
    home = safe_int(home_score)
    away = safe_int(away_score)
    if home > away:
        return home_team, away_team
    if away > home:
        return away_team, home_team
    home_penalty = str(result.get("home_penalty_score", "")).strip()
    away_penalty = str(result.get("away_penalty_score", "")).strip()
    if home_penalty != "" and away_penalty != "":
        if safe_int(home_penalty) > safe_int(away_penalty):
            return home_team, away_team
        if safe_int(away_penalty) > safe_int(home_penalty):
            return away_team, home_team
    return "", ""


def resolve_group_source(source: str, by_rank: dict[tuple[str, int], dict]) -> tuple[str, bool]:
    winner = re.search(r"Winner\s+Group\s+([A-L])", source, flags=re.I)
    runner = re.search(r"(Runner-up|Second)\s+Group\s+([A-L])", source, flags=re.I)
    third = re.search(r"(3rd|Third)(?:\s+place)?\s+Group\s+([A-L](?:/[A-L])*)", source, flags=re.I)
    if winner:
        group = winner.group(1).upper()
        row = by_rank.get((group, 1))
        return (row["team"], True) if row and row.get("qualified_status") in {"qualified", "possible"} and row.get("played", 0) >= 3 else (pending_group(group, 1), False)
    if runner:
        group = runner.group(2).upper()
        row = by_rank.get((group, 2))
        return (row["team"], True) if row and row.get("qualified_status") in {"qualified", "possible"} and row.get("played", 0) >= 3 else (pending_group(group, 2), False)
    if third:
        groups = [item.upper() for item in third.group(2).split("/") if item.upper() in GROUPS]
        return f"待定：{'/'.join(groups)}组第三之一", False
    return source, bool(source and not source.startswith("Winner Match") and not source.startswith("Loser Match"))


def resolve_third_source(source: str, thirds: list[dict]) -> tuple[str, bool]:
    match = re.search(r"(3rd|Third)(?:\s+place)?\s+Group\s+([A-L](?:/[A-L])*)", source, flags=re.I)
    if not match:
        return "", False
    groups = [item.upper() for item in match.group(2).split("/") if item.upper() in GROUPS]
    for row in thirds:
        if row["group"] in groups and row.get("best_third_qualified") and row.get("played", 0) >= 3:
            return row["team"], True
    return f"待定：{'/'.join(groups)}组第三之一", False


def derive_next_map(static_rows) -> dict[int, tuple[int, str, str]]:
    mapping: dict[int, tuple[int, str, str]] = {}
    for _, row in static_rows.iterrows():
        if row["stage"] == "Group Stage":
            continue
        match_id = safe_int(row["match_id"])
        for slot_name, source in [("home", static_home(row)), ("away", static_away(row))]:
            winner = re.search(r"Winner\s+Match\s+(\d+)", source, flags=re.I)
            loser = re.search(r"Loser\s+Match\s+(\d+)", source, flags=re.I)
            if winner:
                mapping[safe_int(winner.group(1))] = (match_id, slot_name, "winner")
            if loser:
                mapping[safe_int(loser.group(1))] = (match_id, slot_name, "loser")
    return mapping


def resolve_knockout(static_path: Path, live_path: Path, standings_path: Path) -> dict:
    static_rows = load_static_schedule(static_path)
    live = load_live_results(live_path)
    standings = load_standings(standings_path)
    by_rank = standings_by_rank(standings["standings"])
    thirds = best_thirds(standings["standings"])
    next_map = derive_next_map(static_rows)

    bracket: dict[int, dict] = {}
    for _, row in static_rows.iterrows():
        if row["stage"] == "Group Stage":
            continue
        match_id = safe_int(row["match_id"])
        home_source = static_home(row)
        away_source = static_away(row)
        home_team, home_resolved = resolve_third_source(home_source, thirds) if re.search(r"(3rd|Third)", home_source, flags=re.I) else resolve_group_source(home_source, by_rank)
        away_team, away_resolved = resolve_third_source(away_source, thirds) if re.search(r"(3rd|Third)", away_source, flags=re.I) else resolve_group_source(away_source, by_rank)
        bracket[match_id] = {
            "match_id": match_id,
            "round": row["round"] or row["stage"],
            "stage": row["stage"],
            "home_source": home_source,
            "away_source": away_source,
            "home_team": home_team,
            "away_team": away_team,
            "home_resolved": home_resolved,
            "away_resolved": away_resolved,
            "home_score": "",
            "away_score": "",
            "home_penalty_score": "",
            "away_penalty_score": "",
            "winner": "",
            "loser": "",
            "next_match_id": next_map.get(match_id, (None, "", ""))[0],
            "next_slot": next_map.get(match_id, (None, "", ""))[1],
            "status": "scheduled",
            "last_updated": "",
        }

    for match_id in sorted(bracket):
        row = bracket[match_id]
        result = live["by_id"].get(match_id, {})
        if result:
            row["home_score"] = result.get("home_score", "")
            row["away_score"] = result.get("away_score", "")
            row["home_penalty_score"] = result.get("home_penalty_score", "")
            row["away_penalty_score"] = result.get("away_penalty_score", "")
            row["status"] = normalize_status(result.get("status", "scheduled"))
            row["last_updated"] = result.get("last_updated", "")
            winner, loser = result_winner_loser(result, row["home_team"], row["away_team"])
            row["winner"] = winner
            row["loser"] = loser
        if row["winner"] and row["next_match_id"] in bracket:
            target = bracket[row["next_match_id"]]
            team = row["winner"] if next_map[match_id][2] == "winner" else row["loser"]
            if row["next_slot"] == "home":
                target["home_team"] = team
                target["home_resolved"] = True
            elif row["next_slot"] == "away":
                target["away_team"] = team
                target["away_resolved"] = True

    rows = [bracket[key] for key in sorted(bracket)]
    return {
        "last_updated": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "knockout": rows,
        "best_thirds": thirds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve knockout bracket from standings and live results.")
    parser.add_argument("--static", type=Path, default=default_static_schedule_path(), help="static_schedule.csv 路径")
    parser.add_argument("--live", type=Path, default=default_live_results_path(), help="live_results.json 路径")
    parser.add_argument("--standings", type=Path, default=default_standings_path(), help="standings.json 路径")
    parser.add_argument("--output", type=Path, default=default_knockout_bracket_path(), help="knockout_bracket.json 输出路径")
    args = parser.parse_args()
    payload = resolve_knockout(args.static, args.live, args.standings)
    write_json(args.output, payload)
    print(f"已解析淘汰赛: {args.output} ({len(payload['knockout'])} 场)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
