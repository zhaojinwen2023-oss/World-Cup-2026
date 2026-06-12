from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from schedule_utils import (
    default_app_data_path,
    ensure_output_dir,
    load_json,
)


def escape_ics(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold_ics_line(line: str) -> list[str]:
    if len(line.encode("utf-8")) <= 75:
        return [line]
    lines: list[str] = []
    current = ""
    current_len = 0
    for char in line:
        char_len = len(char.encode("utf-8"))
        limit = 75 if not lines else 74
        if current and current_len + char_len > limit:
            lines.append(current if not lines else f" {current}")
            current = char
            current_len = char_len
        else:
            current += char
            current_len += char_len
    if current:
        lines.append(current if not lines else f" {current}")
    return lines


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def utc_stamp(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_calendar(app_data_path: Path, output_path: Path, include_all: bool = False) -> int:
    app_data = load_json(app_data_path, {})
    matches = app_data.get("matches", [])
    selected = matches if include_all else [item for item in matches if item.get("is_favorite")]
    now = utc_stamp(datetime.now(UTC))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//World Cup Schedule//Dynamic Favorites//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:世界杯重点比赛",
    ]

    for item in selected:
        start = parse_utc(item["kickoff_utc"])
        end = start + timedelta(hours=2)
        title = f"世界杯：{item['home_team']} vs {item['away_team']}"
        description = "\n".join(
            [
                f"比赛阶段: {item['stage_label']}",
                f"比赛状态: {item.get('status_label', item.get('match_status', ''))}",
                f"比分: {item['score']}",
                f"北京时间: {item['beijing_display']}",
                f"美国东部时间: {item['eastern_display']}",
                f"美国西部时间: {item['western_display']}",
                f"城市 / 球场: {item['city']} / {item['stadium']}",
                f"备注: {item['notes']}" if item.get("notes") else "备注: ",
            ]
        )
        location = f"{item['city']}, {item['stadium']}"
        reminder_title = f"{item['home_team']} vs {item['away_team']}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:worldcup-2026-match-{item['match_id']}@local",
                f"DTSTAMP:{now}",
                f"DTSTART:{utc_stamp(start)}",
                f"DTEND:{utc_stamp(end)}",
                f"SUMMARY:{escape_ics(title)}",
                f"LOCATION:{escape_ics(location)}",
                f"DESCRIPTION:{escape_ics(description)}",
                "BEGIN:VALARM",
                "TRIGGER:-PT2H",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape_ics(f'世界杯 2 小时后开赛：{reminder_title}')}",
                "END:VALARM",
                "BEGIN:VALARM",
                "TRIGGER:-PT30M",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape_ics(f'世界杯 30 分钟后开赛：{reminder_title}')}",
                "END:VALARM",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        folded.extend(fold_ics_line(line))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\r\n".join(folded) + "\r\n", encoding="utf-8")
    return len(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build favorite match calendar reminders.")
    parser.add_argument("--app-data", type=Path, default=default_app_data_path(), help="app_data.json 路径")
    parser.add_argument("--output", type=Path, default=ensure_output_dir() / "worldcup_favorites.ics", help="输出 .ics 路径")
    parser.add_argument("--all", action="store_true", help="导出全部比赛，而不只是 is_favorite=true")
    args = parser.parse_args()
    count = build_calendar(args.app_data, args.output, args.all)
    print(f"已生成 {count} 场比赛提醒: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
