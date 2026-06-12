from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from schedule_utils import default_static_schedule_path, load_static_schedule, parse_local_datetime, safe_int, static_away, static_home

from .base_provider import BaseProvider, ProviderError, http_get_json


SPORTMONKS_STATUS_MAP = {
    "NS": "scheduled",
    "TBA": "scheduled",
    "not_started": "scheduled",
    "not started": "scheduled",
    "scheduled": "scheduled",
    "1st half": "live",
    "2nd half": "live",
    "inplay": "live",
    "live": "live",
    "HT": "halftime",
    "half-time": "halftime",
    "halftime": "halftime",
    "ET": "extra_time",
    "extra time": "extra_time",
    "PEN": "penalties",
    "penalties": "penalties",
    "FT": "finished",
    "AET": "finished",
    "FT_PEN": "finished",
    "finished": "finished",
    "ended": "finished",
    "POSTP": "postponed",
    "postponed": "postponed",
    "CANC": "cancelled",
    "cancelled": "cancelled",
}


class SportMonksProvider(BaseProvider):
    """SportMonks football adapter for World Cup fixtures and live scores."""

    def __init__(self, static_path: Path | None = None):
        self.key = os.getenv("SPORTMONKS_KEY")
        self.base_url = os.getenv("SPORTMONKS_BASE_URL", "https://api.sportmonks.com/v3/football").rstrip("/")
        self.league_id = os.getenv("SPORTMONKS_WORLD_CUP_LEAGUE_ID", "732")
        self.start_date = os.getenv("SPORTMONKS_START_DATE", "2026-06-11")
        self.end_date = os.getenv("SPORTMONKS_END_DATE", "2026-07-20")
        self.fixtures_url = os.getenv("SPORTMONKS_FIXTURES_URL", "")
        self.standings_url = os.getenv("SPORTMONKS_STANDINGS_URL", "")
        self.static_path = static_path or default_static_schedule_path()

    def fetch(self) -> dict:
        if not self.key:
            raise ProviderError("SportMonks 需要 SPORTMONKS_KEY。请写入 .env 或 GitHub Secrets。")

        raw_payloads = self._fetch_fixture_payloads()
        raw_fixtures = []
        for payload in raw_payloads:
            raw_fixtures.extend(extract_fixtures(payload.get("data", [])))

        if not raw_fixtures:
            messages = [str(payload.get("message", "")).strip() for payload in raw_payloads if payload.get("message")]
            detail = "；".join(messages) or "SportMonks 没有返回 fixtures。"
            raise ProviderError(
                f"SportMonks 未返回世界杯赛程/比分：{detail} "
                "请确认 token 的订阅包含 Football World Cup 数据，或设置 SPORTMONKS_FIXTURES_URL 指向可访问的 fixtures endpoint。"
            )

        static_index = StaticMatchIndex(self.static_path)
        matches = []
        unmatched = []
        for fixture in raw_fixtures:
            normalized = normalize_fixture(fixture)
            match_id = static_index.match_fixture(normalized)
            if match_id is None:
                unmatched.append(normalized.get("sportmonks_fixture_id"))
                continue
            normalized["match_id"] = match_id
            matches.append(normalized)

        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload = {"matches": matches, "standings": [], "knockout": [], "last_updated": now}
        if unmatched:
            payload["warnings"] = [f"{len(unmatched)} 条 SportMonks fixtures 未能匹配到本地 match_id。"]
        return payload

    def _fetch_fixture_payloads(self) -> list[dict]:
        if self.fixtures_url:
            return self._get_paginated(self.fixtures_url)

        url = f"{self.base_url}/fixtures/between/{self.start_date}/{self.end_date}"
        params = {
            "api_token": self.key,
            "filters": f"fixtureLeagues:{self.league_id}",
            "include": "participants;scores;state;venue;round;stage;group;periods",
            "per_page": "50",
        }
        return self._get_paginated(with_query(url, params))

    def _get_paginated(self, url: str) -> list[dict]:
        if "api_token=" not in url:
            url = with_query(url, {"api_token": self.key})
        pages = []
        next_url = url
        for _ in range(20):
            payload = http_get_json(next_url)
            pages.append(payload)
            pagination = payload.get("pagination") or {}
            if not pagination.get("has_more"):
                break
            next_url = with_query(url, {"page": safe_int(pagination.get("current_page"), 1) + 1})
        return pages


class StaticMatchIndex:
    def __init__(self, static_path: Path):
        self.rows = []
        static_rows = load_static_schedule(static_path)
        for _, row in static_rows.iterrows():
            kickoff = parse_local_datetime(str(row["local_datetime"]), str(row["local_timezone"])).astimezone(UTC)
            self.rows.append(
                {
                    "match_id": safe_int(row["match_id"]),
                    "stage": str(row["stage"]).strip(),
                    "round": str(row["round"]).strip(),
                    "group": str(row["group"]).strip(),
                    "home": normalize_name(static_home(row)),
                    "away": normalize_name(static_away(row)),
                    "stadium": normalize_name(str(row["stadium"])),
                    "city": normalize_name(str(row["city"])),
                    "kickoff": kickoff,
                }
            )

    def match_fixture(self, fixture: dict) -> int | None:
        kickoff = fixture.get("kickoff")
        home = normalize_name(fixture.get("home_team"))
        away = normalize_name(fixture.get("away_team"))
        stadium = normalize_name(fixture.get("stadium"))

        if home and away:
            for row in self.rows:
                if {home, away} == {row["home"], row["away"]}:
                    return row["match_id"]

        if kickoff:
            close_rows = [
                row
                for row in self.rows
                if abs((row["kickoff"] - kickoff).total_seconds()) <= 18 * 60 * 60
                and (not stadium or stadium in row["stadium"] or row["stadium"] in stadium)
            ]
            if len(close_rows) == 1:
                return close_rows[0]["match_id"]

            same_round = [row for row in close_rows if fixture.get("round") and normalize_name(fixture.get("round")) in normalize_name(row["round"])]
            if len(same_round) == 1:
                return same_round[0]["match_id"]

        return None


def with_query(url: str, params: dict[str, object]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in params.items() if value not in (None, "")})
    return urlunparse(parsed._replace(query=urlencode(query)))


def extract_fixtures(node: object) -> list[dict]:
    fixtures = []
    if isinstance(node, list):
        for item in node:
            fixtures.extend(extract_fixtures(item))
    elif isinstance(node, dict):
        if "starting_at" in node and ("participants" in node or "scores" in node or "state_id" in node):
            fixtures.append(node)
        else:
            for value in node.values():
                fixtures.extend(extract_fixtures(value))
    return fixtures


def normalize_fixture(fixture: dict) -> dict:
    home_team, away_team = participant_names(fixture.get("participants", []))
    home_score, away_score, home_penalty, away_penalty = score_values(fixture.get("scores", []))
    status = status_value(fixture)
    winner = winner_name(fixture.get("participants", []))
    loser = ""
    if winner and home_team and away_team:
        loser = away_team if normalize_name(winner) == normalize_name(home_team) else home_team
    kickoff = parse_sportmonks_datetime(fixture.get("starting_at"))
    return {
        "sportmonks_fixture_id": fixture.get("id"),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "home_penalty_score": home_penalty,
        "away_penalty_score": away_penalty,
        "status": status,
        "minute": minute_value(fixture),
        "winner": winner,
        "loser": loser,
        "is_finished": status == "finished",
        "last_updated": str(fixture.get("updated_at") or ""),
        "kickoff": kickoff,
        "stadium": nested_name(fixture.get("venue")),
        "round": nested_name(fixture.get("round")) or nested_name(fixture.get("stage")),
    }


def participant_names(participants: object) -> tuple[str, str]:
    home = ""
    away = ""
    if not isinstance(participants, list):
        return home, away
    for participant in participants:
        name = nested_name(participant)
        location = str((participant.get("meta") or {}).get("location") or (participant.get("meta") or {}).get("home_away") or "").lower()
        if location == "home":
            home = name
        elif location == "away":
            away = name
    if (not home or not away) and len(participants) >= 2:
        home = home or nested_name(participants[0])
        away = away or nested_name(participants[1])
    return home, away


def winner_name(participants: object) -> str:
    if not isinstance(participants, list):
        return ""
    for participant in participants:
        meta = participant.get("meta") or {}
        if meta.get("winner") is True:
            return nested_name(participant)
    return ""


def score_values(scores: object) -> tuple[object, object, object, object]:
    home_score = away_score = home_penalty = away_penalty = ""
    if not isinstance(scores, list):
        return home_score, away_score, home_penalty, away_penalty
    for item in scores:
        score = item.get("score") if isinstance(item, dict) else {}
        description = str(item.get("description", "")).lower() if isinstance(item, dict) else ""
        participant = str((score or {}).get("participant") or item.get("participant") or "").lower()
        goals = (score or {}).get("goals", item.get("goals", ""))
        if goals is None or participant not in {"home", "away"}:
            continue
        is_penalty = "pen" in description or "shootout" in description
        if is_penalty and participant == "home":
            home_penalty = goals
        elif is_penalty and participant == "away":
            away_penalty = goals
        elif participant == "home":
            home_score = goals
        elif participant == "away":
            away_score = goals
    return home_score, away_score, home_penalty, away_penalty


def status_value(fixture: dict) -> str:
    state = fixture.get("state") or {}
    candidates = [
        state.get("short_name") if isinstance(state, dict) else "",
        state.get("name") if isinstance(state, dict) else "",
        fixture.get("state"),
        fixture.get("status"),
        fixture.get("status_name"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        if text in SPORTMONKS_STATUS_MAP:
            return SPORTMONKS_STATUS_MAP[text]
        lowered = text.lower()
        if lowered in SPORTMONKS_STATUS_MAP:
            return SPORTMONKS_STATUS_MAP[lowered]
    return "scheduled"


def minute_value(fixture: dict) -> object:
    time = fixture.get("time") or {}
    if isinstance(time, dict):
        for key in ["minute", "current_minute", "injury_time"]:
            if time.get(key) not in (None, ""):
                return time[key]
    periods = fixture.get("periods") or []
    if isinstance(periods, list) and periods:
        current = periods[-1]
        if isinstance(current, dict):
            return current.get("minutes") or current.get("minute") or ""
    return ""


def parse_sportmonks_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def nested_name(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    if item.get("name"):
        return str(item["name"]).strip()
    nested = item.get("participant") or item.get("team") or item.get("venue") or {}
    if isinstance(nested, dict) and nested.get("name"):
        return str(nested["name"]).strip()
    return ""


def normalize_name(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
