from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from schedule_utils import (
    default_app_data_path,
    default_knockout_bracket_path,
    default_live_results_path,
    default_standings_path,
    default_static_schedule_path,
    default_top_scorers_path,
    enriched_match_from_row,
    load_knockout_bracket,
    load_live_results,
    load_standings,
    load_static_schedule,
    load_top_scorers,
    safe_int,
    write_json,
)


def best_thirds_from_standings(standings: list[dict]) -> list[dict]:
    thirds = [dict(row) for row in standings if safe_int(row.get("rank")) == 3]
    thirds.sort(key=lambda row: (-safe_int(row.get("points")), -safe_int(row.get("goal_difference")), -safe_int(row.get("goals_for")), safe_int(row.get("fair_play_points")), row.get("team", "")))
    for index, row in enumerate(thirds, start=1):
        row["best_third_rank"] = index
        row["best_third_qualified"] = row.get("qualified_status") == "qualified"
    return thirds


def build_app_data(static_path: Path, live_path: Path, standings_path: Path, knockout_path: Path, output_path: Path, top_scorers_path: Path | None = None) -> dict:
    static_rows = load_static_schedule(static_path)
    live = load_live_results(live_path)
    standings = load_standings(standings_path)
    knockout = load_knockout_bracket(knockout_path)
    top_scorers = load_top_scorers(top_scorers_path or default_top_scorers_path())

    matches = []
    for _, row in static_rows.iterrows():
        match_id = safe_int(row["match_id"])
        matches.append(enriched_match_from_row(row, live["by_id"].get(match_id, {}), knockout["by_id"].get(match_id, {})))

    matches.sort(key=lambda item: item["kickoff_utc"])
    payload = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "live_last_updated": live["last_updated"],
        "standings_last_updated": standings["last_updated"],
        "top_scorers_last_updated": top_scorers["last_updated"],
        "knockout_last_updated": knockout["last_updated"],
        "matches": matches,
        "standings": standings["standings"],
        "top_scorers": top_scorers["scorers"],
        "best_thirds": best_thirds_from_standings(standings["standings"]),
        "knockout": knockout["knockout"],
    }
    write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build app_data.json for PWA and exports.")
    parser.add_argument("--static", type=Path, default=default_static_schedule_path(), help="static_schedule.csv 路径")
    parser.add_argument("--live", type=Path, default=default_live_results_path(), help="live_results.json 路径")
    parser.add_argument("--standings", type=Path, default=default_standings_path(), help="standings.json 路径")
    parser.add_argument("--knockout", type=Path, default=default_knockout_bracket_path(), help="knockout_bracket.json 路径")
    parser.add_argument("--top-scorers", type=Path, default=default_top_scorers_path(), help="top_scorers.json 路径")
    parser.add_argument("--output", type=Path, default=default_app_data_path(), help="输出 app_data.json 路径")
    args = parser.parse_args()
    payload = build_app_data(args.static, args.live, args.standings, args.knockout, args.output, args.top_scorers)
    print(f"已生成 App 数据: {args.output} ({len(payload['matches'])} 场比赛)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
