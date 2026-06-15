from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

from schedule_utils import default_static_schedule_path, safe_int

from .base_provider import BaseProvider, ProviderError, http_get_json
from .sportmonks_provider import StaticMatchIndex


class ApiFootballProvider(BaseProvider):
    """API-SPORTS / API-Football adapter for World Cup fixtures and live scores."""

    STATUS_MAP = {
        "TBD": "scheduled",
        "NS": "scheduled",
        "1H": "live",
        "2H": "live",
        "LIVE": "live",
        "HT": "halftime",
        "ET": "extra_time",
        "BT": "extra_time",
        "P": "penalties",
        "FT": "finished",
        "AET": "finished",
        "PEN": "finished",
        "PST": "postponed",
        "SUSP": "postponed",
        "INT": "postponed",
        "CANC": "cancelled",
        "ABD": "cancelled",
        "AWD": "cancelled",
        "WO": "cancelled",
    }

    def __init__(self, static_path: Path | None = None):
        self.key = clean_key(os.getenv("API_FOOTBALL_KEY") or os.getenv("APISPORTS_KEY"))
        self.base_url = os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io").rstrip("/")
        self.league_id = os.getenv("API_FOOTBALL_WORLD_CUP_LEAGUE_ID", "1")
        self.season = os.getenv("API_FOOTBALL_WORLD_CUP_SEASON", "2026")
        self.fixtures_url = os.getenv("API_FOOTBALL_FIXTURES_URL", "")
        self.top_scorers_url = os.getenv("API_FOOTBALL_TOP_SCORERS_URL", "")
        self.auth_mode = os.getenv("API_FOOTBALL_AUTH_MODE", "apisports").strip().lower()
        self.rapidapi_host = os.getenv("API_FOOTBALL_RAPIDAPI_HOST", urlparse(self.base_url).netloc)
        self.static_path = static_path or default_static_schedule_path()

    def fetch(self) -> dict:
        if not self.key:
            raise ProviderError("API-SPORTS 需要 API_FOOTBALL_KEY。请写入 .env 或 GitHub Secrets。")

        payload = self._fetch_fixtures()
        errors = payload.get("errors")
        if errors:
            raise ProviderError(f"API-SPORTS 请求失败：{clean_error(errors)}")

        fixtures = payload.get("response") or []
        if not fixtures:
            raise ProviderError("API-SPORTS 没有返回世界杯 fixtures。请确认套餐包含 World Cup 2026 数据。")

        static_index = StaticMatchIndex(self.static_path)
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        matches = []
        unmatched = []
        for fixture in fixtures:
            normalized = self._normalize_fixture(fixture, now)
            match_id = static_index.match_fixture(normalized)
            if match_id is None:
                unmatched.append(normalized.get("api_football_fixture_id"))
                continue
            normalized["match_id"] = match_id
            matches.append(normalized)

        top_scorers, scorer_warning = self._fetch_top_scorers(now)
        result = {"matches": matches, "standings": [], "top_scorers": top_scorers, "top_scorers_last_updated": now, "knockout": [], "last_updated": now}
        warnings = []
        if unmatched:
            warnings.append(f"{len(unmatched)} 条 API-SPORTS fixtures 未能匹配到本地 match_id。")
        if scorer_warning:
            warnings.append(scorer_warning)
        if warnings:
            result["warnings"] = warnings
        return result

    def _fetch_fixtures(self) -> dict:
        headers = self._headers()
        if self.fixtures_url:
            return http_get_json(self.fixtures_url, headers=headers)
        query = urlencode({"league": self.league_id, "season": self.season})
        return http_get_json(f"{self.base_url}/fixtures?{query}", headers=headers)

    def _fetch_top_scorers(self, fallback_updated: str) -> tuple[list[dict], str]:
        headers = self._headers()
        try:
            if self.top_scorers_url:
                payload = http_get_json(self.top_scorers_url, headers=headers)
            else:
                query = urlencode({"league": self.league_id, "season": self.season})
                payload = http_get_json(f"{self.base_url}/players/topscorers?{query}", headers=headers)
        except ProviderError as exc:
            return [], f"API-SPORTS 射手榜暂不可用：{exc}"

        errors = payload.get("errors")
        if errors:
            return [], f"API-SPORTS 射手榜暂不可用：{clean_error(errors)}"

        rows = payload.get("response") or []
        return [normalize_top_scorer(item, index, fallback_updated) for index, item in enumerate(rows, start=1)], ""

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "worldcup-schedule/1.0"}
        if self.auth_mode in {"rapidapi", "rapid_api", "x-rapidapi"}:
            headers["x-rapidapi-key"] = self.key
            headers["x-rapidapi-host"] = self.rapidapi_host
        else:
            headers["x-apisports-key"] = self.key
        return headers

    def _normalize_fixture(self, item: dict, fallback_updated: str) -> dict:
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        score = item.get("score") or {}
        penalty = score.get("penalty") or {}
        goals = item.get("goals") or {}
        status = self._status_value(fixture.get("status") or {})
        winner = ""
        loser = ""
        if home.get("winner") is True:
            winner, loser = home.get("name", ""), away.get("name", "")
        elif away.get("winner") is True:
            winner, loser = away.get("name", ""), home.get("name", "")
        return {
            "api_football_fixture_id": fixture.get("id"),
            "home_team": str(home.get("name") or "").strip(),
            "away_team": str(away.get("name") or "").strip(),
            "home_score": blank_none(goals.get("home")),
            "away_score": blank_none(goals.get("away")),
            "home_penalty_score": blank_none(penalty.get("home")),
            "away_penalty_score": blank_none(penalty.get("away")),
            "status": status,
            "minute": self._minute_value(fixture.get("status") or {}),
            "winner": str(winner or "").strip(),
            "loser": str(loser or "").strip(),
            "is_finished": status == "finished",
            "last_updated": fallback_updated,
            "kickoff": parse_api_datetime(fixture.get("date")),
            "stadium": str((fixture.get("venue") or {}).get("name") or "").strip(),
            "round": str((item.get("league") or {}).get("round") or "").strip(),
        }

    def _status_value(self, status: dict) -> str:
        short = str(status.get("short") or "").strip().upper()
        return self.STATUS_MAP.get(short, "scheduled")

    def _minute_value(self, status: dict) -> object:
        elapsed = status.get("elapsed")
        extra = status.get("extra")
        if elapsed in (None, ""):
            return ""
        if extra not in (None, "", 0):
            return f"{safe_int(elapsed)}+{safe_int(extra)}"
        return elapsed


def blank_none(value: object) -> object:
    return "" if value is None else value


def normalize_top_scorer(item: dict, rank: int, fallback_updated: str) -> dict:
    player = item.get("player") or {}
    stats = first_stat(item)
    team = stats.get("team") or {}
    goals = stats.get("goals") or {}
    games = stats.get("games") or {}
    penalty = stats.get("penalty") or {}
    return {
        "rank": rank,
        "player_id": str(player.get("id") or "").strip(),
        "player": str(player.get("name") or "").strip(),
        "team": str(team.get("name") or "").strip(),
        "goals": safe_int(goals.get("total")),
        "assists": blank_none(goals.get("assists")),
        "penalties": blank_none(penalty.get("scored")),
        "appearances": blank_none(games.get("appearences", games.get("appearances"))),
        "minutes": blank_none(games.get("minutes")),
        "photo": str(player.get("photo") or "").strip(),
        "last_updated": fallback_updated,
    }


def first_stat(item: dict) -> dict:
    stats = item.get("statistics")
    if isinstance(stats, list) and stats:
        return stats[0] if isinstance(stats[0], dict) else {}
    return {}


def clean_key(value: object) -> str:
    return str(value or "").strip().strip('"').strip("'")


def parse_api_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def clean_error(errors: object) -> str:
    if isinstance(errors, dict):
        parts = [str(value).strip() for value in errors.values() if str(value).strip()]
        return "；".join(parts) if parts else str(errors)
    if isinstance(errors, list):
        parts = [str(value).strip() for value in errors if str(value).strip()]
        return "；".join(parts) if parts else str(errors)
    return str(errors)
