from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
LIVE_STATUSES = {"live", "halftime", "extra_time", "penalties"}

TEAM_NAME_ZH = {
    "Algeria": "阿尔及利亚",
    "Argentina": "阿根廷",
    "Australia": "澳大利亚",
    "Austria": "奥地利",
    "Belgium": "比利时",
    "Bosnia and Herzegovina": "波黑",
    "Brazil": "巴西",
    "Canada": "加拿大",
    "Cape Verde": "佛得角",
    "Colombia": "哥伦比亚",
    "Croatia": "克罗地亚",
    "Curaçao": "库拉索",
    "Czech Republic": "捷克",
    "DR Congo": "刚果（金）",
    "Ecuador": "厄瓜多尔",
    "Egypt": "埃及",
    "England": "英格兰",
    "France": "法国",
    "Germany": "德国",
    "Ghana": "加纳",
    "Haiti": "海地",
    "Iran": "伊朗",
    "Iraq": "伊拉克",
    "Ivory Coast": "科特迪瓦",
    "Japan": "日本",
    "Jordan": "约旦",
    "Mexico": "墨西哥",
    "Morocco": "摩洛哥",
    "Netherlands": "荷兰",
    "New Zealand": "新西兰",
    "Norway": "挪威",
    "Panama": "巴拿马",
    "Paraguay": "巴拉圭",
    "Portugal": "葡萄牙",
    "Qatar": "卡塔尔",
    "Saudi Arabia": "沙特阿拉伯",
    "Scotland": "苏格兰",
    "Senegal": "塞内加尔",
    "South Africa": "南非",
    "South Korea": "韩国",
    "Spain": "西班牙",
    "Sweden": "瑞典",
    "Switzerland": "瑞士",
    "Tunisia": "突尼斯",
    "Turkey": "土耳其",
    "United States": "美国",
    "Uruguay": "乌拉圭",
    "Uzbekistan": "乌兹别克斯坦",
}

STATUS_LABELS = {
    "scheduled": "未开始",
    "live": "进行中",
    "halftime": "中场",
    "extra_time": "加时",
    "penalties": "点球大战",
    "finished": "已结束",
    "postponed": "延期",
    "cancelled": "取消",
}


def default_app_data_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "app_data.json"


def load_app_data(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("matches"), list):
        raise ValueError(f"{path} 缺少 matches 数组")
    return payload


def display_team(team: object) -> str:
    text = str(team or "待定").strip() or "待定"
    return TEAM_NAME_ZH.get(text, text)


def kickoff_time(match: dict) -> str:
    raw = str(match.get("kickoff_utc") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.astimezone(BEIJING_TZ).strftime("%H:%M")
        except ValueError:
            pass
    display = str(match.get("beijing_display") or "")
    parts = display.split()
    return parts[2] if len(parts) >= 3 else "待定"


def stage_text(match: dict) -> str:
    stage = str(match.get("stage_label") or match.get("stage") or "比赛").strip()
    group = str(match.get("group") or "").strip()
    if group and stage == "小组赛":
        return f"{stage} {group}组"
    return stage


def status_text(match: dict) -> str:
    status = str(match.get("status") or "scheduled").strip().lower()
    label = STATUS_LABELS.get(status, str(match.get("status_label") or status))
    minute = str(match.get("minute") or "").strip()
    if status in LIVE_STATUSES and minute:
        suffix = minute if minute.endswith("'") else f"{minute}'"
        return f"{label} · {suffix}"
    return label


def score_text(match: dict) -> str:
    score = str(match.get("score") or "").strip()
    return score.replace("-", " : ", 1) if score else "vs"


def match_markdown(match: dict) -> str:
    home = display_team(match.get("home_team"))
    away = display_team(match.get("away_team"))
    return (
        f"**{kickoff_time(match)} · {stage_text(match)}**\n"
        f"{home}  **{score_text(match)}**  {away}\n"
        f"{status_text(match)}"
    )


def report_matches(matches: list[dict], target_date: str) -> tuple[list[dict], bool]:
    dates = sorted(
        {str(match.get("beijing_date") or "") for match in matches if match.get("beijing_date")}
    )
    if not dates or target_date < dates[0] or target_date > dates[-1]:
        return [], False

    selected = [match for match in matches if str(match.get("beijing_date") or "") == target_date]
    selected.sort(key=lambda match: str(match.get("kickoff_utc") or ""))
    if selected:
        return selected, True

    upcoming = [match for match in matches if str(match.get("beijing_date") or "") > target_date]
    upcoming.sort(key=lambda match: str(match.get("kickoff_utc") or ""))
    return upcoming[:3], True


def build_card(app_data: dict, target_date: str, web_url: str = "") -> dict | None:
    matches, in_tournament = report_matches(app_data["matches"], target_date)
    if not in_tournament:
        return None

    target = date.fromisoformat(target_date)
    today_matches = [
        match for match in matches if str(match.get("beijing_date") or "") == target_date
    ]
    finished = sum(str(match.get("status") or "") == "finished" for match in today_matches)
    live = sum(str(match.get("status") or "") in LIVE_STATUSES for match in today_matches)
    scheduled = sum(str(match.get("status") or "") == "scheduled" for match in today_matches)

    if today_matches:
        summary = f"已结束 {finished} · 进行中 {live} · 待开赛 {scheduled}"
        body = "\n\n".join(match_markdown(match) for match in matches)
    else:
        summary = "今日休赛 · 下一比赛日"
        body = "\n\n".join(match_markdown(match) for match in matches)

    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**{summary}**"}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": body or "暂无比赛信息"}},
    ]

    updated = str(
        app_data.get("live_last_updated") or app_data.get("generated_at") or "未知"
    ).strip()
    elements.extend(
        [
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": f"北京时间 · 数据更新：{updated}"}],
            },
        ]
    )
    if web_url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "查看完整赛程"},
                        "url": web_url,
                    }
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"2026 世界杯 · {target.month}月{target.day}日战报",
            },
        },
        "elements": elements,
    }


def build_signature(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def webhook_payload(card: dict, secret: str = "", timestamp: int | None = None) -> dict:
    payload = {"msg_type": "interactive", "card": card}
    if secret:
        current_timestamp = int(timestamp if timestamp is not None else time.time())
        payload["timestamp"] = str(current_timestamp)
        payload["sign"] = build_signature(secret, current_timestamp)
    return payload


def parse_targets(targets_json: str, webhook_url: str = "", secret: str = "") -> list[dict]:
    text = targets_json.strip()
    if not text:
        url = webhook_url.strip()
        return [{"name": "默认群", "webhook": url, "secret": secret.strip()}] if url else []

    try:
        raw_targets = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"FEISHU_TARGETS_JSON 不是有效 JSON：{exc.msg}") from exc
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("FEISHU_TARGETS_JSON 必须是非空数组")

    targets = []
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 个飞书目标必须是对象")
        if raw.get("enabled") is False:
            continue
        name = str(raw.get("name") or f"目标{index}").strip()
        url = str(raw.get("webhook") or "").strip()
        target_secret = str(raw.get("secret") or "").strip()
        if not url:
            raise ValueError(f"飞书目标“{name}”缺少 webhook")
        targets.append({"name": name, "webhook": url, "secret": target_secret})
    if not targets:
        raise ValueError("FEISHU_TARGETS_JSON 没有启用的目标")
    return targets


def send_webhook(webhook_url: str, payload: dict, timeout: int = 20) -> dict:
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "worldcup-schedule/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"飞书 Webhook 返回 HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接飞书 Webhook: {exc.reason}") from exc

    code = result.get("code", result.get("StatusCode", 0))
    if code not in (0, "0", None):
        message = result.get("msg", result.get("StatusMessage", "未知错误"))
        raise RuntimeError(f"飞书推送失败（{code}）：{message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="生成并推送飞书世界杯每日战报")
    parser.add_argument("--data", type=Path, default=default_app_data_path(), help="app_data.json 路径")
    parser.add_argument("--date", default="", help="战报日期，格式 YYYY-MM-DD；默认北京时间今天")
    parser.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL", ""))
    parser.add_argument("--secret", default=os.environ.get("FEISHU_WEBHOOK_SECRET", ""))
    parser.add_argument(
        "--targets-json",
        default=os.environ.get("FEISHU_TARGETS_JSON", ""),
        help="多群配置 JSON；设置后优先于单个 Webhook",
    )
    parser.add_argument("--web-url", default=os.environ.get("WORLDCUP_WEB_URL", ""))
    parser.add_argument("--dry-run", action="store_true", help="只输出飞书请求体，不发送")
    args = parser.parse_args()

    target_date = args.date or datetime.now(BEIJING_TZ).date().isoformat()
    try:
        date.fromisoformat(target_date)
    except ValueError as exc:
        parser.error(f"无效日期：{target_date}（需要 YYYY-MM-DD）")
        raise exc

    app_data = load_app_data(args.data)
    card = build_card(app_data, target_date, args.web_url.strip())
    if card is None:
        print(f"{target_date} 不在赛事日期范围内，跳过推送。")
        return 0

    try:
        targets = parse_targets(args.targets_json, args.webhook_url, args.secret)
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        previews = [
            {"name": target["name"], "payload": webhook_payload(card, target["secret"])}
            for target in targets
        ]
        print(json.dumps(previews or [{"name": "预览", "payload": webhook_payload(card)}], ensure_ascii=False, indent=2))
        return 0
    if not targets:
        parser.error("缺少 FEISHU_TARGETS_JSON 或 FEISHU_WEBHOOK_URL")

    failures = []
    for target in targets:
        try:
            send_webhook(target["webhook"], webhook_payload(card, target["secret"]))
            print(f"飞书战报推送成功：{target_date} -> {target['name']}")
        except RuntimeError as exc:
            failures.append(f"{target['name']}：{exc}")

    if failures:
        for failure in failures:
            print(f"飞书战报推送失败：{failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
