from __future__ import annotations

import argparse
import csv
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from schedule_utils import default_static_schedule_path


SOURCE_TIMEZONE = ZoneInfo("America/Denver")

VENUE_META = {
    "AT&T Stadium, Arlington": ("AT&T Stadium", "Arlington", "USA", "America/Chicago"),
    "Arrowhead Stadium, Kansas City": ("Arrowhead Stadium", "Kansas City", "USA", "America/Chicago"),
    "BC Place, Vancouver": ("BC Place", "Vancouver", "Canada", "America/Vancouver"),
    "BMO Field, Toronto": ("BMO Field", "Toronto", "Canada", "America/Toronto"),
    "Estadio Akron, Zapopan": ("Estadio Akron", "Zapopan", "Mexico", "America/Mexico_City"),
    "Estadio Azteca, Mexico City": ("Estadio Azteca", "Mexico City", "Mexico", "America/Mexico_City"),
    "Estadio BBVA, Guadalupe": ("Estadio BBVA", "Guadalupe", "Mexico", "America/Monterrey"),
    "Gillette Stadium, Foxborough": ("Gillette Stadium", "Foxborough", "USA", "America/New_York"),
    "Hard Rock Stadium, Miami Gardens": ("Hard Rock Stadium", "Miami Gardens", "USA", "America/New_York"),
    "Levi's Stadium, Santa Clara": ("Levi's Stadium", "Santa Clara", "USA", "America/Los_Angeles"),
    "Lincoln Financial Field, Philadelphia": ("Lincoln Financial Field", "Philadelphia", "USA", "America/New_York"),
    "Lumen Field, Seattle": ("Lumen Field", "Seattle", "USA", "America/Los_Angeles"),
    "Mercedes-Benz Stadium, Atlanta": ("Mercedes-Benz Stadium", "Atlanta", "USA", "America/New_York"),
    "MetLife Stadium, East Rutherford": ("MetLife Stadium", "East Rutherford", "USA", "America/New_York"),
    "NRG Stadium, Houston": ("NRG Stadium", "Houston", "USA", "America/Chicago"),
    "SoFi Stadium, Inglewood": ("SoFi Stadium", "Inglewood", "USA", "America/Los_Angeles"),
}

STAGE_MAP = {
    "Round of 32": "Round of 32",
    "Round of 16": "Round of 16",
    "Quarterfinals": "Quarter-final",
    "Semifinals": "Semi-final",
    "Match for third place": "Third-place",
    "Final": "Final",
}


def read_ics(path: Path) -> str:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".ics") and not name.startswith("__MACOSX/")]
            if not names:
                raise ValueError(f"No .ics file found in {path}")
            return archive.read(names[0]).decode("utf-8")
    return path.read_text(encoding="utf-8")


def unfold_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(" ") and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def parse_events(text: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in unfold_lines(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key] = value
    return events


def strip_flags(text: str) -> str:
    cleaned = []
    for char in text:
        codepoint = ord(char)
        if 0xE0000 <= codepoint <= 0xE007F:
            continue
        if unicodedata.category(char) == "So":
            continue
        cleaned.append(char)
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def parse_stage_and_id(description: str) -> tuple[str, int, str, str]:
    match = re.search(r"(.+?)\s+-\s+Match\s+(\d+)", description)
    if not match:
        raise ValueError(f"Cannot parse DESCRIPTION: {description}")
    raw_stage = match.group(1).strip()
    match_id = int(match.group(2))
    if raw_stage.startswith("Group "):
        return "Group Stage", match_id, raw_stage, raw_stage
    return STAGE_MAP.get(raw_stage, raw_stage), match_id, raw_stage, ""


def source_dt_to_local(yyyymmdd_thhmmss_z: str, venue_tz: str) -> str:
    raw = yyyymmdd_thhmmss_z.removesuffix("Z")
    source_naive = datetime.strptime(raw, "%Y%m%dT%H%M%S")
    source_dt = source_naive.replace(tzinfo=SOURCE_TIMEZONE)
    local_dt = source_dt.astimezone(ZoneInfo(venue_tz))
    return local_dt.replace(tzinfo=None).isoformat(timespec="seconds")


def event_to_row(event: dict[str, str]) -> dict[str, str | int]:
    stage, match_id, round_name, group_note = parse_stage_and_id(event["DESCRIPTION"])
    location = event["LOCATION"]
    if location not in VENUE_META:
        raise ValueError(f"Unknown venue: {location}")
    stadium, city, country, venue_tz = VENUE_META[location]
    summary = strip_flags(event["SUMMARY"])
    if " vs " not in summary:
        raise ValueError(f"Cannot parse SUMMARY: {summary}")
    home, away = [part.strip() for part in summary.split(" vs ", 1)]
    return {
        "match_id": match_id,
        "stage": stage,
        "round": round_name,
        "group": group_note.replace("Group ", "") if group_note else "",
        "home_placeholder": home,
        "away_placeholder": away,
        "home_team": home if stage == "Group Stage" else "",
        "away_team": away if stage == "Group Stage" else "",
        "stadium": stadium,
        "city": city,
        "country": country,
        "local_datetime": source_dt_to_local(event["DTSTART"], venue_tz),
        "local_timezone": venue_tz,
        "is_favorite": "false",
        "notes": group_note,
    }


def import_fixtures(source: Path, output: Path) -> list[dict[str, str | int]]:
    rows = [event_to_row(event) for event in parse_events(read_ics(source))]
    rows.sort(key=lambda row: int(row["match_id"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
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
                "is_favorite",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Import public 2026 World Cup fixtures from a FourFourTwo MDT .ics export.")
    parser.add_argument("source", type=Path, help="FourFourTwo .ics or .zip file")
    parser.add_argument("--output", type=Path, default=default_static_schedule_path(), help="static_schedule.csv 输出路径")
    args = parser.parse_args()
    rows = import_fixtures(args.source, args.output)
    print(f"已导入固定赛程: {args.output} ({len(rows)} 场)")
    print(f"第 1 场: {rows[0]['home_placeholder']} vs {rows[0]['away_placeholder']} / {rows[0]['local_datetime']} {rows[0]['local_timezone']}")
    print(f"第 104 场: {rows[-1]['home_placeholder']} vs {rows[-1]['away_placeholder']} / {rows[-1]['local_datetime']} {rows[-1]['local_timezone']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
