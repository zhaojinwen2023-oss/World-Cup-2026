from __future__ import annotations

import base64
import hashlib
import hmac
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from push_feishu_report import (  # noqa: E402
    build_card,
    build_signature,
    parse_targets,
    report_matches,
    webhook_payload,
)


def sample_match(match_id: int, date_key: str, status: str, score: str = "") -> dict:
    return {
        "match_id": match_id,
        "beijing_date": date_key,
        "kickoff_utc": f"{date_key}T06:00:00Z",
        "stage_label": "小组赛",
        "group": "A",
        "home_team": "Mexico",
        "away_team": "South Africa",
        "status": status,
        "minute": 67 if status == "live" else "",
        "score": score,
    }


class FeishuReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_data = {
            "generated_at": "2026-06-18T05:50:00Z",
            "live_last_updated": "2026-06-18T05:45:00Z",
            "matches": [
                sample_match(1, "2026-06-18", "finished", "2-1"),
                sample_match(2, "2026-06-18", "live", "1-0"),
                sample_match(3, "2026-06-19", "scheduled"),
            ],
        }

    def test_build_card_contains_daily_summary_and_chinese_team_names(self) -> None:
        card = build_card(self.app_data, "2026-06-18", "https://example.com/worldcup")

        self.assertIsNotNone(card)
        self.assertEqual(card["header"]["title"]["content"], "2026 世界杯 · 6月18日战报")
        content = "\n".join(
            element.get("text", {}).get("content", "")
            for element in card["elements"]
            if element.get("tag") == "div"
        )
        self.assertIn("已结束 1 · 进行中 1 · 待开赛 0", content)
        self.assertIn("墨西哥  **2 : 1**  南非", content)
        self.assertIn("进行中 · 67'", content)
        self.assertEqual(card["elements"][-1]["tag"], "action")

    def test_rest_day_shows_next_matches(self) -> None:
        matches, in_tournament = report_matches(self.app_data["matches"], "2026-06-17")
        self.assertFalse(in_tournament)
        self.assertEqual(matches, [])

        app_data = dict(self.app_data)
        app_data["matches"] = [
            sample_match(1, "2026-06-16", "finished", "2-1"),
            sample_match(2, "2026-06-18", "scheduled"),
        ]
        card = build_card(app_data, "2026-06-17")
        self.assertIn("今日休赛 · 下一比赛日", card["elements"][0]["text"]["content"])

    def test_signature_and_payload(self) -> None:
        timestamp = 1_717_000_000
        expected = base64.b64encode(
            hmac.new(b"1717000000\ntest-secret", digestmod=hashlib.sha256).digest()
        ).decode("utf-8")

        self.assertEqual(build_signature("test-secret", timestamp), expected)
        payload = webhook_payload({"elements": []}, "test-secret", timestamp)
        self.assertEqual(payload["timestamp"], str(timestamp))
        self.assertEqual(payload["sign"], expected)

    def test_outside_tournament_returns_no_card(self) -> None:
        self.assertIsNone(build_card(self.app_data, "2026-08-01"))

    def test_parse_multiple_targets(self) -> None:
        targets = parse_targets(
            '[{"name":"朋友A","webhook":"https://example.com/a","secret":"sa"},'
            '{"name":"暂停","webhook":"https://example.com/off","enabled":false},'
            '{"name":"朋友B","webhook":"https://example.com/b"}]'
        )
        self.assertEqual([target["name"] for target in targets], ["朋友A", "朋友B"])
        self.assertEqual(targets[0]["secret"], "sa")
        self.assertEqual(targets[1]["secret"], "")

    def test_parse_targets_keeps_single_webhook_compatibility(self) -> None:
        self.assertEqual(
            parse_targets("", "https://example.com/default", "default-secret"),
            [
                {
                    "name": "默认群",
                    "webhook": "https://example.com/default",
                    "secret": "default-secret",
                }
            ],
        )

    def test_parse_targets_rejects_missing_webhook(self) -> None:
        with self.assertRaisesRegex(ValueError, "缺少 webhook"):
            parse_targets('[{"name":"朋友A"}]')


if __name__ == "__main__":
    unittest.main()
