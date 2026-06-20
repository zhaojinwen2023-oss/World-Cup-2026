from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse

from build_champion_predictions import canonical_team, tournament_teams
from providers.api_football_provider import clean_error, clean_key
from providers.base_provider import ProviderError, http_get_json, load_env_file


ROOT = Path(__file__).resolve().parents[1]
FINISHED_STATUSES = {"FT", "AET", "PEN"}


def api_headers(base_url: str) -> dict[str, str]:
    key = clean_key(os.getenv("API_FOOTBALL_KEY") or os.getenv("APISPORTS_KEY"))
    if not key:
        raise ProviderError("API-SPORTS 需要 API_FOOTBALL_KEY。请写入 .env 或 GitHub Secrets。")
    auth_mode = os.getenv("API_FOOTBALL_AUTH_MODE", "apisports").strip().lower()
    headers = {"User-Agent": "worldcup-schedule/1.0"}
    if auth_mode in {"rapidapi", "rapid_api", "x-rapidapi"}:
        headers["x-rapidapi-key"] = key
        headers["x-rapidapi-host"] = os.getenv("API_FOOTBALL_RAPIDAPI_HOST", urlparse(base_url).netloc)
    else:
        headers["x-apisports-key"] = key
    return headers


def api_get(base_url: str, endpoint: str, params: dict[str, object], headers: dict[str, str]) -> dict:
    payload = http_get_json(f"{base_url}/{endpoint}?{urlencode(params)}", headers=headers)
    errors = payload.get("errors")
    if errors:
        raise ProviderError(f"API-SPORTS 请求失败：{clean_error(errors)}")
    return payload


def current_world_cup_team_ids(base_url: str, headers: dict[str, str], target_teams: set[str]) -> dict[str, int]:
    league_id = os.getenv("API_FOOTBALL_WORLD_CUP_LEAGUE_ID", "1")
    season = os.getenv("API_FOOTBALL_WORLD_CUP_SEASON", "2026")
    payload = api_get(base_url, "fixtures", {"league": league_id, "season": season}, headers)
    ids: dict[str, int] = {}
    for item in payload.get("response") or []:
        teams = item.get("teams") or {}
        for side in ("home", "away"):
            team = teams.get(side) or {}
            name = canonical_team(team.get("name"))
            team_id = team.get("id")
            if name in target_teams and team_id not in (None, ""):
                ids[name] = int(team_id)
    missing = sorted(target_teams - ids.keys())
    if missing:
        raise ProviderError(f"无法从世界杯赛程解析球队 API ID：{', '.join(missing)}")
    return ids


def normalized_historical_fixture(item: dict) -> dict | None:
    fixture = item.get("fixture") or {}
    status = str((fixture.get("status") or {}).get("short") or "").upper()
    goals = item.get("goals") or {}
    if status not in FINISHED_STATUSES or goals.get("home") is None or goals.get("away") is None:
        return None
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    league = item.get("league") or {}
    score = item.get("score") or {}
    penalty = score.get("penalty") or {}
    return {
        "fixture_id": int(fixture.get("id")),
        "date": str(fixture.get("date") or ""),
        "competition_id": league.get("id"),
        "competition": str(league.get("name") or "").strip(),
        "competition_country": str(league.get("country") or "").strip(),
        "season": league.get("season"),
        "round": str(league.get("round") or "").strip(),
        "home_team": canonical_team(home.get("name")),
        "away_team": canonical_team(away.get("name")),
        "home_team_id": home.get("id"),
        "away_team_id": away.get("id"),
        "home_score": int(goals.get("home")),
        "away_score": int(goals.get("away")),
        "home_penalty_score": penalty.get("home"),
        "away_penalty_score": penalty.get("away"),
        "status": status,
    }


def fetch_history(app_data: dict, start: date, end: date, base_url: str, headers: dict[str, str]) -> dict:
    target_teams = set(tournament_teams(app_data.get("matches") or []))
    team_ids = current_world_cup_team_ids(base_url, headers, target_teams)
    fixtures: dict[int, dict] = {}
    seasons = list(range(start.year, end.year + 1))
    for index, (team, team_id) in enumerate(sorted(team_ids.items()), start=1):
        team_match_count = 0
        for season in seasons:
            payload = api_get(
                base_url,
                "fixtures",
                {
                    "team": team_id,
                    "season": season,
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "timezone": "UTC",
                },
                headers,
            )
            for item in payload.get("response") or []:
                normalized = normalized_historical_fixture(item)
                if normalized:
                    fixtures[normalized["fixture_id"]] = normalized
                    team_match_count += 1
        print(f"历史赛果抓取 {index}/{len(team_ids)}: {team} ({team_match_count} 条，{len(seasons)} 个赛季)")

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "version": "api-football-history-v1",
        "generated_at": generated_at,
        "source": "API-Football",
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days},
        "queried_seasons": seasons,
        "team_ids": team_ids,
        "matches": sorted(fixtures.values(), key=lambda row: (row["date"], row["fixture_id"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取世界杯参赛队开赛前24个月的国家队历史赛果。")
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--app-data", type=Path, default=ROOT / "data" / "app_data.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "historical_results.json")
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 6, 10), help="历史窗口截止日，默认世界杯开赛前一天")
    parser.add_argument("--window-days", type=int, default=730)
    args = parser.parse_args()

    load_env_file(args.env)
    base_url = os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io").rstrip("/")
    end = args.end
    start = end - timedelta(days=args.window_days)
    app_data = json.loads(args.app_data.read_text(encoding="utf-8"))
    try:
        payload = fetch_history(app_data, start, end, base_url, api_headers(base_url))
    except ProviderError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已保存历史赛果: {args.output} ({len(payload['matches'])} 场)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
