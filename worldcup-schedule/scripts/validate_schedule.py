from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from build_app_data import build_app_data
from resolve_knockout import resolve_knockout
from schedule_utils import (
    STATIC_REQUIRED_COLUMNS,
    VALID_STATUSES,
    default_app_data_path,
    default_knockout_bracket_path,
    default_live_results_path,
    default_standings_path,
    default_static_schedule_path,
    default_top_scorers_path,
    load_knockout_bracket,
    load_live_results,
    load_standings,
    load_static_schedule,
    load_top_scorers,
    normalize_status,
    safe_int,
    static_away,
    static_home,
)


STATIC_NON_EMPTY_COLUMNS = [
    "match_id",
    "stage",
    "round",
    "stadium",
    "city",
    "country",
    "local_datetime",
    "local_timezone",
]


def validate(static_path: Path, live_path: Path, standings_path: Path, knockout_path: Path, app_data_path: Path, top_scorers_path: Path) -> int:
    errors: list[str] = []
    static_rows = load_static_schedule(static_path)
    missing = [column for column in STATIC_REQUIRED_COLUMNS if column not in static_rows.columns]
    if missing:
        errors.append(f"static_schedule.csv 缺少字段: {', '.join(missing)}")
        print_errors(errors)
        return 1

    ids: set[int] = set()
    for index, row in static_rows.iterrows():
        line = index + 2
        try:
            match_id = safe_int(row["match_id"])
            if match_id in ids:
                errors.append(f"static_schedule.csv 第 {line} 行: match_id 重复: {match_id}")
            ids.add(match_id)
        except ValueError:
            errors.append(f"static_schedule.csv 第 {line} 行: match_id 不是整数: {row['match_id']}")

        for column in STATIC_NON_EMPTY_COLUMNS:
            if not str(row[column]).strip():
                errors.append(f"static_schedule.csv 第 {line} 行: {column} 不能为空")

        stage = str(row["stage"]).strip()
        if stage == "Group Stage":
            if not str(row["group"]).strip():
                errors.append(f"static_schedule.csv 第 {line} 行: 小组赛 group 不能为空")
            if not static_home(row):
                errors.append(f"static_schedule.csv 第 {line} 行: 小组赛主队不能为空")
            if not static_away(row):
                errors.append(f"static_schedule.csv 第 {line} 行: 小组赛客队不能为空")
        else:
            if not static_home(row):
                errors.append(f"static_schedule.csv 第 {line} 行: 淘汰赛主队来源不能为空")
            if not static_away(row):
                errors.append(f"static_schedule.csv 第 {line} 行: 淘汰赛客队来源不能为空")

        try:
            datetime.fromisoformat(str(row["local_datetime"]).strip())
        except ValueError:
            errors.append(f"static_schedule.csv 第 {line} 行: local_datetime 不是 ISO 格式: {row['local_datetime']}")

        try:
            ZoneInfo(str(row["local_timezone"]).strip())
        except ZoneInfoNotFoundError:
            errors.append(f"static_schedule.csv 第 {line} 行: 无效时区: {row['local_timezone']}")

    live = load_live_results(live_path)
    for item in live["results"]:
        try:
            match_id = safe_int(item.get("match_id"))
        except ValueError:
            errors.append(f"live_results.json: match_id 不是整数: {item.get('match_id')}")
            continue
        if match_id not in ids:
            errors.append(f"live_results.json: match_id 不存在于 static_schedule.csv: {match_id}")
        status = normalize_status(item.get("status", item.get("match_status")))
        if status not in VALID_STATUSES:
            errors.append(f"live_results.json 第 {match_id} 场: 未知 status: {item.get('status', item.get('match_status'))}")

    standings = load_standings(standings_path)
    for row in standings["standings"]:
        if row["group"] == "" or row["team"] == "":
            errors.append("standings.json: group 和 team 不能为空")
        if row["rank"] < 1:
            errors.append(f"standings.json: {row['team']} rank 必须 >= 1")

    top_scorers = load_top_scorers(top_scorers_path)
    for row in top_scorers["scorers"]:
        if row["player"] == "":
            errors.append("top_scorers.json: player 不能为空")
        if row["goals"] < 0:
            errors.append(f"top_scorers.json: {row['player']} goals 不能为负数")

    knockout = load_knockout_bracket(knockout_path)
    for row in knockout["knockout"]:
        match_id = row["match_id"]
        if match_id not in ids:
            errors.append(f"knockout_bracket.json: match_id 不存在于 static_schedule.csv: {match_id}")
        status = normalize_status(row.get("status"))
        if status not in VALID_STATUSES:
            errors.append(f"knockout_bracket.json 第 {match_id} 场: 未知 status: {row.get('status')}")

    if not errors:
        try:
            knockout = resolve_knockout(static_path, live_path, standings_path)
            build_app_data(static_path, live_path, standings_path, knockout_path, app_data_path, top_scorers_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"动态数据合成失败: {exc}")
            knockout = {"knockout": []}

    if errors:
        print_errors(errors)
        return 1

    print(f"赛程校验通过: {len(static_rows)} 场比赛，{len(live['results'])} 条实时结果，{len(standings['standings'])} 条积分榜记录，{len(top_scorers['scorers'])} 条射手榜记录，{len(knockout['knockout'])} 场淘汰赛。")
    print(f"已生成 App 数据: {app_data_path}")
    print("淘汰赛解析示例:")
    for row in knockout["knockout"][:5]:
        print(f"- 第 {row['match_id']} 场 {row.get('round', row.get('stage', ''))}: {row['home_team']} vs {row['away_team']}")
    return 0


def print_errors(errors: list[str]) -> None:
    print("赛程校验失败:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate dynamic worldcup schedule data.")
    parser.add_argument("--static", type=Path, default=default_static_schedule_path(), help="static_schedule.csv 路径")
    parser.add_argument("--live", type=Path, default=default_live_results_path(), help="live_results.json 路径")
    parser.add_argument("--standings", type=Path, default=default_standings_path(), help="standings.json 路径")
    parser.add_argument("--knockout", type=Path, default=default_knockout_bracket_path(), help="knockout_bracket.json 路径")
    parser.add_argument("--top-scorers", type=Path, default=default_top_scorers_path(), help="top_scorers.json 路径")
    parser.add_argument("--app-data", type=Path, default=default_app_data_path(), help="app_data.json 输出路径")
    args = parser.parse_args()
    return validate(args.static, args.live, args.standings, args.knockout, args.app_data, args.top_scorers)


if __name__ == "__main__":
    raise SystemExit(main())
