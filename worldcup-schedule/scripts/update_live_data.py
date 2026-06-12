from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from build_app_data import build_app_data
from build_excel import build_workbook
from build_ics import build_calendar
from calculate_standings import calculate_standings
from providers import ApiFootballProvider, GoogleSheetProvider, LiveScoreProvider, LocalJsonProvider, SportMonksProvider, WorldCupApiProvider
from providers.base_provider import ProviderError, load_env_file
from resolve_knockout import resolve_knockout
from schedule_utils import (
    default_app_data_path,
    default_knockout_bracket_path,
    default_last_updated_path,
    default_live_results_path,
    default_standings_path,
    default_static_schedule_path,
    ensure_output_dir,
    load_static_schedule,
    load_standings,
    normalize_live_result,
    normalize_standing_row,
    normalize_status,
    safe_int,
    static_away,
    static_home,
    write_json,
)


def provider_from_source(args) -> object:
    if args.source == "local":
        return LocalJsonProvider(args.live, args.standings, args.knockout)
    if args.source == "google_sheet":
        return GoogleSheetProvider(args.live_url, args.standings_url, args.knockout_url)
    if args.source == "api_football":
        return ApiFootballProvider()
    if args.source == "sportmonks":
        return SportMonksProvider()
    if args.source == "livescore":
        return LiveScoreProvider()
    if args.source == "worldcupapi":
        return WorldCupApiProvider()
    raise ProviderError(f"未知数据源: {args.source}")


def default_live_rows(static_path: Path) -> dict[int, dict]:
    rows = {}
    static_rows = load_static_schedule(static_path)
    for _, row in static_rows.iterrows():
        match_id = safe_int(row["match_id"])
        rows[match_id] = {
            "match_id": match_id,
            "home_team": static_home(row) if row["stage"] == "Group Stage" else "",
            "away_team": static_away(row) if row["stage"] == "Group Stage" else "",
            "home_score": "",
            "away_score": "",
            "home_penalty_score": "",
            "away_penalty_score": "",
            "status": "scheduled",
            "minute": "",
            "winner": "",
            "loser": "",
            "is_finished": False,
            "last_updated": "",
        }
    return rows


def infer_winner_loser(item: dict) -> dict:
    status = normalize_status(item.get("status"))
    item["status"] = status
    item["is_finished"] = bool(item.get("is_finished", status == "finished"))
    if item.get("winner") or status != "finished":
        return item
    home_score = str(item.get("home_score", "")).strip()
    away_score = str(item.get("away_score", "")).strip()
    if home_score == "" or away_score == "":
        return item
    home_team = item.get("home_team", "")
    away_team = item.get("away_team", "")
    home = safe_int(home_score)
    away = safe_int(away_score)
    if home > away:
        item["winner"], item["loser"] = home_team, away_team
    elif away > home:
        item["winner"], item["loser"] = away_team, home_team
    else:
        home_pen = str(item.get("home_penalty_score", "")).strip()
        away_pen = str(item.get("away_penalty_score", "")).strip()
        if home_pen != "" and away_pen != "":
            if safe_int(home_pen) > safe_int(away_pen):
                item["winner"], item["loser"] = home_team, away_team
            elif safe_int(away_pen) > safe_int(home_pen):
                item["winner"], item["loser"] = away_team, home_team
    return item


def merge_live_results(static_path: Path, provider_matches: list[dict], last_updated: str) -> dict:
    merged = default_live_rows(static_path)
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for raw in provider_matches:
        item = normalize_live_result(raw)
        match_id = item["match_id"]
        if match_id not in merged:
            continue
        updates = {}
        for key, value in item.items():
            if value is None:
                continue
            if key in {"home_team", "away_team"} and str(value).strip() == "":
                continue
            updates[key] = value
        merged[match_id].update(updates)
        merged[match_id]["last_updated"] = merged[match_id].get("last_updated") or last_updated or now
        merged[match_id] = infer_winner_loser(merged[match_id])
    return {"last_updated": last_updated or now, "results": [merged[key] for key in sorted(merged)]}


def provider_standings_payload(rows: list[dict], fallback_last_updated: str) -> dict:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "last_updated": fallback_last_updated or now,
        "standings": [normalize_standing_row(row) for row in rows],
    }


def merge_knockout_payload(resolved: dict, provider_rows: list[dict], fallback_last_updated: str) -> dict:
    if not provider_rows:
        return resolved
    by_id = {safe_int(row["match_id"]): dict(row) for row in resolved.get("knockout", [])}
    for raw in provider_rows:
        match_id = safe_int(raw.get("match_id"))
        if match_id in by_id:
            by_id[match_id].update({key: value for key, value in raw.items() if value not in (None, "")})
        else:
            by_id[match_id] = dict(raw)
    return {
        "last_updated": fallback_last_updated or resolved.get("last_updated", ""),
        "knockout": [by_id[key] for key in sorted(by_id)],
        "best_thirds": resolved.get("best_thirds", []),
    }


def update_live_data(args) -> None:
    load_env_file(args.env)
    provider = provider_from_source(args)
    payload = provider.fetch()

    live_payload = merge_live_results(args.static, payload.get("matches", []), payload.get("last_updated", ""))
    write_json(args.live, live_payload)

    if args.standings_mode == "provider" and payload.get("standings"):
        standings_payload = provider_standings_payload(payload["standings"], payload.get("last_updated", ""))
    else:
        standings_payload = calculate_standings(args.static, args.live)
    write_json(args.standings, standings_payload)
    # Reload after writing so downstream code sees the same normalized file contents.
    _ = load_standings(args.standings)

    knockout_payload = resolve_knockout(args.static, args.live, args.standings)
    if args.knockout_mode == "provider" and payload.get("knockout"):
        knockout_payload = merge_knockout_payload(knockout_payload, payload["knockout"], payload.get("last_updated", ""))
    write_json(args.knockout, knockout_payload)

    app_data = build_app_data(args.static, args.live, args.standings, args.knockout, args.app_data)
    output_dir = ensure_output_dir()
    build_workbook(args.app_data, output_dir / "worldcup_2026_schedule.xlsx")
    build_calendar(args.app_data, output_dir / "worldcup_favorites.ics")

    write_json(
        args.last_updated,
        {
            "last_updated": app_data["generated_at"],
            "source": args.source,
            "live_results": args.live.as_posix(),
            "standings": args.standings.as_posix(),
            "knockout_bracket": args.knockout.as_posix(),
            "app_data": args.app_data.as_posix(),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Update live results, standings, knockout bracket, app data, Excel, and ICS.")
    parser.add_argument("--source", choices=["api_football", "sportmonks", "livescore", "worldcupapi", "google_sheet", "local"], default="local")
    parser.add_argument("--standings-mode", choices=["auto", "provider"], default="auto", help="auto=从比分重算积分榜；provider=使用数据源提供的 standings")
    parser.add_argument("--knockout-mode", choices=["auto", "provider"], default="auto", help="auto=从积分榜/赛果解析；provider=在自动解析结果上叠加数据源 knockout")
    parser.add_argument("--env", type=Path, default=Path(".env"), help=".env 文件路径")
    parser.add_argument("--live-url", help="Google Sheet / CSV / JSON 比分 URL")
    parser.add_argument("--standings-url", help="Google Sheet / CSV / JSON 积分榜 URL")
    parser.add_argument("--knockout-url", help="Google Sheet / CSV / JSON 淘汰赛 URL")
    parser.add_argument("--static", type=Path, default=default_static_schedule_path())
    parser.add_argument("--live", type=Path, default=default_live_results_path())
    parser.add_argument("--standings", type=Path, default=default_standings_path())
    parser.add_argument("--knockout", type=Path, default=default_knockout_bracket_path())
    parser.add_argument("--app-data", type=Path, default=default_app_data_path())
    parser.add_argument("--last-updated", type=Path, default=default_last_updated_path())
    args = parser.parse_args()
    try:
        update_live_data(args)
    except ProviderError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"已完成实时数据刷新: {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
