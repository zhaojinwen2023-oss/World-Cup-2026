from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


TARGET_ZONES = {
    "beijing": "Asia/Shanghai",
    "eastern": "America/New_York",
    "western": "America/Los_Angeles",
}

STAGE_LABELS = {
    "Group Stage": "小组赛",
    "Round of 32": "32强",
    "Round of 16": "16强",
    "Quarter-final": "1/4决赛",
    "Quarter-finals": "1/4决赛",
    "Quarterfinals": "1/4决赛",
    "Semi-final": "半决赛",
    "Semi-finals": "半决赛",
    "Semifinals": "半决赛",
    "Third-place": "三四名",
    "Match for third place": "三四名",
    "Final": "决赛",
}

STATUS_LABELS = {
    "scheduled": "未开始",
    "live": "进行中",
    "halftime": "中场",
    "extra_time": "加时",
    "penalties": "点球",
    "finished": "已结束",
    "postponed": "延期",
    "cancelled": "取消",
}

STATUS_ALIASES = {
    "not_started": "scheduled",
    "in_progress": "live",
    "final": "finished",
    "penalty": "penalties",
    "未开始": "scheduled",
    "进行中": "live",
    "中场": "halftime",
    "加时": "extra_time",
    "点球": "penalties",
    "已结束": "finished",
    "延期": "postponed",
    "取消": "cancelled",
}

FINISHED_STATUSES = {"finished"}
LIVE_STATUSES = {"live", "halftime", "extra_time", "penalties"}
VALID_STATUSES = {"scheduled", "live", "halftime", "extra_time", "penalties", "finished", "postponed", "cancelled"}

STATIC_REQUIRED_COLUMNS = [
    "match_id",
    "stage",
    "round",
    "group",
    "home_placeholder",
    "away_placeholder",
    "home_team",
    "away_team",
    "stadium",
    "city",
    "country",
    "local_datetime",
    "local_timezone",
]

TRUE_VALUES = {"true", "1", "yes", "y", "是", "⭐", "star", "favorite"}
WEEKDAYS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    return project_root() / "data"


def ensure_output_dir() -> Path:
    output = project_root() / "output"
    output.mkdir(parents=True, exist_ok=True)
    return output


def default_static_schedule_path() -> Path:
    return data_dir() / "static_schedule.csv"


def default_live_results_path() -> Path:
    return data_dir() / "live_results.json"


def default_standings_path() -> Path:
    return data_dir() / "standings.json"


def default_top_scorers_path() -> Path:
    return data_dir() / "top_scorers.json"


def default_knockout_bracket_path() -> Path:
    return data_dir() / "knockout_bracket.json"


def default_app_data_path() -> Path:
    return data_dir() / "app_data.json"


def default_last_updated_path() -> Path:
    return data_dir() / "last_updated.json"


def normalize_bool(value: object) -> bool:
    return str(value).strip().lower() in TRUE_VALUES


def safe_int(value: object, default: int = 0) -> int:
    text = str(value or "").strip()
    if text == "":
        return default
    return int(float(text))


def maybe_int(value: object) -> int | None:
    text = str(value or "").strip()
    if text == "":
        return None
    return int(float(text))


def stage_label(stage: object) -> str:
    return STAGE_LABELS.get(str(stage).strip(), str(stage).strip())


def normalize_status(status: object) -> str:
    text = str(status or "").strip()
    if not text:
        return "scheduled"
    lowered = text.lower()
    return STATUS_ALIASES.get(text, STATUS_ALIASES.get(lowered, lowered if lowered in VALID_STATUSES else text))


def status_label(status: object) -> str:
    return STATUS_LABELS.get(normalize_status(status), str(status or ""))


def parse_local_datetime(local_datetime: str, local_timezone: str) -> datetime:
    tz = ZoneInfo(str(local_timezone).strip())
    dt = datetime.fromisoformat(str(local_datetime).strip())
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def format_dt(dt: datetime, include_zone: bool = True) -> str:
    weekday = WEEKDAYS_ZH[dt.weekday()]
    text = f"{dt:%Y-%m-%d} {weekday} {dt:%H:%M}"
    if include_zone:
        text = f"{text} ({dt.tzinfo.key})"
    return text


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_static_schedule(path: Path | str = default_static_schedule_path()) -> pd.DataFrame:
    df = pd.read_csv(Path(path), keep_default_na=False, dtype=str)
    # Backward compatibility for older generated data.
    if "placeholder_home" in df.columns and "home_placeholder" not in df.columns:
        df["home_placeholder"] = df["placeholder_home"]
    if "placeholder_away" in df.columns and "away_placeholder" not in df.columns:
        df["away_placeholder"] = df["placeholder_away"]
    if "home_team" not in df.columns:
        df["home_team"] = df.apply(lambda row: row.get("home_placeholder", "") if row.get("stage") == "Group Stage" else "", axis=1)
    if "away_team" not in df.columns:
        df["away_team"] = df.apply(lambda row: row.get("away_placeholder", "") if row.get("stage") == "Group Stage" else "", axis=1)
    if "round" not in df.columns:
        df["round"] = df["stage"]
    if "group" not in df.columns:
        df["group"] = df.get("notes", "").str.extract(r"Group\s+([A-L])", expand=False).fillna("")
    return df


def load_json(path: Path | str, default: object) -> object:
    file_path = Path(path)
    if not file_path.exists():
        return default
    return json.loads(file_path.read_text(encoding="utf-8"))


def write_json(path: Path | str, payload: object) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_live_result(item: dict) -> dict:
    status = normalize_status(item.get("status", item.get("match_status", "scheduled")))
    home_score = item.get("home_score", "")
    away_score = item.get("away_score", "")
    home_pen = item.get("home_penalty_score", "")
    away_pen = item.get("away_penalty_score", "")
    return {
        "match_id": safe_int(item.get("match_id")),
        "home_team": str(item.get("home_team", "")).strip(),
        "away_team": str(item.get("away_team", "")).strip(),
        "home_score": home_score if home_score != 0 else 0,
        "away_score": away_score if away_score != 0 else 0,
        "home_penalty_score": home_pen if home_pen != 0 else 0,
        "away_penalty_score": away_pen if away_pen != 0 else 0,
        "status": status,
        "minute": item.get("minute", ""),
        "winner": str(item.get("winner", "")).strip(),
        "loser": str(item.get("loser", "")).strip(),
        "is_finished": bool(item.get("is_finished", status in FINISHED_STATUSES)),
        "last_updated": str(item.get("last_updated", "")).strip(),
    }


def load_live_results(path: Path | str = default_live_results_path()) -> dict:
    payload = load_json(path, {"last_updated": "", "results": []})
    if isinstance(payload, list):
        payload = {"last_updated": "", "results": payload}
    results = [normalize_live_result(item) for item in payload.get("results", payload.get("matches", []))]
    by_id = {item["match_id"]: item for item in results}
    return {"last_updated": payload.get("last_updated", ""), "results": results, "by_id": by_id}


def normalize_standing_row(item: dict) -> dict:
    row = dict(item)
    for column in ["played", "won", "drawn", "lost", "goals_for", "goals_against", "goal_difference", "points", "fair_play_points", "rank"]:
        row[column] = safe_int(row.get(column, 0))
    row["group"] = str(row.get("group", "")).strip().upper()
    row["team"] = str(row.get("team", "")).strip()
    row["qualified_status"] = str(row.get("qualified_status", "unknown") or "unknown").strip()
    return row


def load_standings(path: Path | str = default_standings_path()) -> dict:
    payload = load_json(path, {"last_updated": "", "standings": []})
    if isinstance(payload, list):
        payload = {"last_updated": "", "standings": payload}
    rows = [normalize_standing_row(item) for item in payload.get("standings", [])]
    rows.sort(key=lambda row: (row["group"], row["rank"]))
    return {"last_updated": payload.get("last_updated", ""), "standings": rows}


def normalize_top_scorer(item: dict, rank: int = 0) -> dict:
    return {
        "rank": safe_int(item.get("rank"), rank),
        "player_id": str(item.get("player_id", "")).strip(),
        "player": str(item.get("player", item.get("name", ""))).strip(),
        "team": str(item.get("team", "")).strip(),
        "goals": safe_int(item.get("goals")),
        "assists": item.get("assists", ""),
        "penalties": item.get("penalties", ""),
        "appearances": item.get("appearances", ""),
        "minutes": item.get("minutes", ""),
        "photo": str(item.get("photo", "")).strip(),
    }


def load_top_scorers(path: Path | str = default_top_scorers_path()) -> dict:
    payload = load_json(path, {"last_updated": "", "scorers": []})
    if isinstance(payload, list):
        payload = {"last_updated": "", "scorers": payload}
    rows = [normalize_top_scorer(item, index) for index, item in enumerate(payload.get("scorers", []), start=1)]
    rows = [row for row in rows if row["player"]]
    rows.sort(key=lambda row: (-row["goals"], -safe_int(row.get("assists")), row["rank"], row["player"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return {"last_updated": payload.get("last_updated", ""), "scorers": rows}


def load_knockout_bracket(path: Path | str = default_knockout_bracket_path()) -> dict:
    payload = load_json(path, {"last_updated": "", "knockout": []})
    if isinstance(payload, list):
        payload = {"last_updated": "", "knockout": payload}
    rows = []
    for item in payload.get("knockout", []):
        row = dict(item)
        row["match_id"] = safe_int(row.get("match_id"))
        row["next_match_id"] = maybe_int(row.get("next_match_id"))
        row["status"] = normalize_status(row.get("status", "scheduled"))
        rows.append(row)
    return {"last_updated": payload.get("last_updated", ""), "knockout": rows, "by_id": {row["match_id"]: row for row in rows}}


def score_display(home_score: object, away_score: object, home_penalty: object = "", away_penalty: object = "") -> str:
    home = str(home_score if home_score is not None else "").strip()
    away = str(away_score if away_score is not None else "").strip()
    if home == "" or away == "":
        return ""
    score = f"{home}-{away}"
    home_pen = str(home_penalty if home_penalty is not None else "").strip()
    away_pen = str(away_penalty if away_penalty is not None else "").strip()
    if home_pen != "" and away_pen != "":
        score = f"{score} 点球 {home_pen}-{away_pen}"
    return score


def penalty_display(home_penalty: object, away_penalty: object) -> str:
    home = str(home_penalty if home_penalty is not None else "").strip()
    away = str(away_penalty if away_penalty is not None else "").strip()
    return f"{home}-{away}" if home != "" and away != "" else ""


def optional_column(row: pd.Series, column: str, default: str = "") -> str:
    if column not in row.index:
        return default
    return str(row[column]).strip()


def pending_label(slot: str) -> str:
    text = str(slot or "").strip()
    if not text:
        return "待定"
    if text.startswith("待定"):
        return text
    return f"待定：{text}"


def static_home(row: pd.Series) -> str:
    return optional_column(row, "home_team") or optional_column(row, "home_placeholder")


def static_away(row: pd.Series) -> str:
    return optional_column(row, "away_team") or optional_column(row, "away_placeholder")


def enriched_match_from_row(row: pd.Series, live: dict, knockout: dict) -> dict:
    match_id = safe_int(row["match_id"])
    local_dt = parse_local_datetime(row["local_datetime"], row["local_timezone"])
    beijing_dt = local_dt.astimezone(ZoneInfo(TARGET_ZONES["beijing"]))
    eastern_dt = local_dt.astimezone(ZoneInfo(TARGET_ZONES["eastern"]))
    western_dt = local_dt.astimezone(ZoneInfo(TARGET_ZONES["western"]))

    home_placeholder = optional_column(row, "home_placeholder")
    away_placeholder = optional_column(row, "away_placeholder")
    home_team = str(live.get("home_team") or knockout.get("home_team") or static_home(row) or pending_label(home_placeholder)).strip()
    away_team = str(live.get("away_team") or knockout.get("away_team") or static_away(row) or pending_label(away_placeholder)).strip()

    status = normalize_status(live.get("status", knockout.get("status", "scheduled")))
    home_score = live.get("home_score", knockout.get("home_score", ""))
    away_score = live.get("away_score", knockout.get("away_score", ""))
    home_penalty = live.get("home_penalty_score", knockout.get("home_penalty_score", ""))
    away_penalty = live.get("away_penalty_score", knockout.get("away_penalty_score", ""))
    winner = str(live.get("winner") or knockout.get("winner") or "").strip()
    loser = str(live.get("loser") or knockout.get("loser") or "").strip()
    score = score_display(home_score, away_score, home_penalty, away_penalty)
    is_favorite = normalize_bool(optional_column(row, "is_favorite", "false"))
    stage = str(row["stage"]).strip()

    return {
        "match_id": match_id,
        "stage": stage,
        "stage_label": stage_label(stage),
        "round": optional_column(row, "round", stage),
        "group": optional_column(row, "group"),
        "home_placeholder": home_placeholder,
        "away_placeholder": away_placeholder,
        "home_team": home_team,
        "away_team": away_team,
        "home_slot_resolved": bool(home_team and not home_team.startswith("待定")),
        "away_slot_resolved": bool(away_team and not away_team.startswith("待定")),
        "home_slot_label": pending_label(home_placeholder),
        "away_slot_label": pending_label(away_placeholder),
        "matchup": f"{home_team} vs {away_team}",
        "stadium": str(row["stadium"]).strip(),
        "city": str(row["city"]).strip(),
        "country": str(row["country"]).strip(),
        "local_timezone": str(row["local_timezone"]).strip(),
        "kickoff_utc": utc_iso(local_dt),
        "local_display": format_dt(local_dt),
        "beijing_display": format_dt(beijing_dt),
        "eastern_display": format_dt(eastern_dt),
        "western_display": format_dt(western_dt),
        "beijing_date": f"{beijing_dt:%Y-%m-%d}",
        "beijing_is_early_morning": 0 <= beijing_dt.hour < 6,
        "status": status,
        "status_label": status_label(status),
        "match_status": status_label(status),
        "minute": live.get("minute", ""),
        "score": score,
        "home_score": home_score,
        "away_score": away_score,
        "home_penalty_score": home_penalty,
        "away_penalty_score": away_penalty,
        "penalty_score": penalty_display(home_penalty, away_penalty),
        "winner": winner,
        "loser": loser,
        "is_finished": bool(live.get("is_finished", status in FINISHED_STATUSES)),
        "is_live": status in LIVE_STATUSES,
        "last_updated": str(live.get("last_updated", knockout.get("last_updated", ""))).strip(),
        "is_favorite": is_favorite,
        "favorite_mark": "⭐" if is_favorite else "",
        "notes": optional_column(row, "notes", ""),
    }
