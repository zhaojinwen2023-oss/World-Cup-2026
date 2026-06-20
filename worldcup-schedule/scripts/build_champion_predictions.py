from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
BEIJING = ZoneInfo("Asia/Shanghai")
MODEL_VERSION = "可解释模型 v1.0"
MODEL_WEIGHTS = {
    "strength": 0.45,
    "form": 0.30,
    "path": 0.25,
}
SOFTMAX_TEMPERATURE = 5.0
FINISHED_STATUSES = {"finished", "after extra time", "after penalties"}
TEAM_ALIASES = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Cape Verde Islands": "Cape Verde",
    "Congo DR": "DR Congo",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "USA": "United States",
}
KNOCKOUT_WIN_PATH = {
    "Round of 32": 65,
    "Round of 16": 74,
    "Quarter-final": 84,
    "Quarter-finals": 84,
    "Quarterfinals": 84,
    "Semi-final": 94,
    "Semi-finals": 94,
    "Semifinals": 94,
    "Final": 100,
}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def is_resolved_team(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.startswith("待定") and not any(token in text.lower() for token in ("winner ", "runner-up", "loser ", "3rd ", "third "))


def canonical_team(value: object) -> str:
    text = str(value or "").strip()
    return TEAM_ALIASES.get(text, text)


def is_finished(match: dict) -> bool:
    return bool(match.get("is_finished")) or str(match.get("status") or "").strip().lower() in FINISHED_STATUSES


def score_value(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def match_result_for_team(match: dict, team: str) -> dict | None:
    home = canonical_team(match.get("home_team"))
    away = canonical_team(match.get("away_team"))
    if team not in {home, away} or not is_finished(match):
        return None

    home_score = score_value(match.get("home_score"))
    away_score = score_value(match.get("away_score"))
    if home_score is None or away_score is None:
        return None

    is_home = team == home
    goals_for = home_score if is_home else away_score
    goals_against = away_score if is_home else home_score
    winner = canonical_team(match.get("winner"))
    loser = canonical_team(match.get("loser"))

    if winner == team:
        outcome = "win"
    elif loser == team:
        outcome = "loss"
    elif goals_for > goals_against:
        outcome = "win"
    elif goals_for < goals_against:
        outcome = "loss"
    else:
        outcome = "draw"

    return {
        "outcome": outcome,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "stage": str(match.get("stage") or ""),
        "kickoff": str(match.get("kickoff_utc") or ""),
    }


def tournament_teams(matches: list[dict]) -> list[str]:
    teams = set()
    for match in matches:
        if str(match.get("stage") or "") != "Group Stage":
            continue
        for key in ("home_team", "away_team"):
            team = canonical_team(match.get(key))
            if is_resolved_team(team):
                teams.add(team)
    return sorted(teams)


def recent_form(team: str, matches: list[dict], strength: float) -> tuple[float, dict]:
    results = [result for match in matches if (result := match_result_for_team(match, team))]
    results.sort(key=lambda item: item["kickoff"])
    results = results[-5:]
    prior = clamp(strength - 4, 45, 90)
    if not results:
        return prior, {"played": 0, "won": 0, "drawn": 0, "lost": 0, "goal_difference": 0}

    won = sum(result["outcome"] == "win" for result in results)
    drawn = sum(result["outcome"] == "draw" for result in results)
    lost = len(results) - won - drawn
    goals_for = sum(result["goals_for"] for result in results)
    goals_against = sum(result["goals_against"] for result in results)
    points_per_game = (won * 3 + drawn) / len(results)
    goal_difference_per_game = (goals_for - goals_against) / len(results)
    observed = clamp(50 + (points_per_game - 1.5) * 16 + goal_difference_per_game * 5, 12, 96)
    score = (prior * 3 + observed * len(results)) / (3 + len(results))
    return clamp(score, 20, 95), {
        "played": len(results),
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "goal_difference": goals_for - goals_against,
    }


def standings_by_team(app_data: dict) -> dict[str, dict]:
    return {
        canonical_team(row.get("team")): row
        for row in app_data.get("standings", [])
        if is_resolved_team(row.get("team"))
    }


def upcoming_opponent_strength(team: str, matches: list[dict], strengths: dict[str, float]) -> float | None:
    opponents = []
    for match in matches:
        if is_finished(match):
            continue
        home = canonical_team(match.get("home_team"))
        away = canonical_team(match.get("away_team"))
        if home == team and away in strengths:
            opponents.append((str(match.get("kickoff_utc") or ""), strengths[away]))
        elif away == team and home in strengths:
            opponents.append((str(match.get("kickoff_utc") or ""), strengths[home]))
    if not opponents:
        return None
    opponents.sort(key=lambda item: item[0])
    selected = [strength for _, strength in opponents[:3]]
    return sum(selected) / len(selected)


def progression_state(team: str, matches: list[dict]) -> tuple[bool, bool, float]:
    eliminated = False
    champion = False
    progress_path = 0.0
    for match in matches:
        if str(match.get("stage") or "") == "Group Stage" or not is_finished(match):
            continue
        result = match_result_for_team(match, team)
        if not result:
            continue
        if result["outcome"] == "loss":
            eliminated = True
        if result["outcome"] == "win":
            progress_path = max(progress_path, KNOCKOUT_WIN_PATH.get(result["stage"], 60))
            if result["stage"] == "Final":
                champion = True
    return eliminated, champion, progress_path


def path_score(team: str, matches: list[dict], standings: dict[str, dict], strengths: dict[str, float]) -> tuple[float, bool, bool]:
    row = standings.get(team, {})
    played = int(row.get("played") or 0)
    rank = int(row.get("rank") or 0)
    qualified_status = str(row.get("qualified_status") or "possible")
    eliminated = qualified_status == "eliminated"

    target_by_rank = {1: 74, 2: 66, 3: 55, 4: 38}
    target = target_by_rank.get(rank, 50)
    if qualified_status == "qualified" and rank == 3:
        target = 59
    score = 50 + (target - 50) * min(1, played / 3)

    knockout_eliminated, champion, progress_path = progression_state(team, matches)
    eliminated = eliminated or knockout_eliminated
    if progress_path:
        score = max(score, progress_path)

    opponent_strength = upcoming_opponent_strength(team, matches, strengths)
    if opponent_strength is not None:
        score += clamp((75 - opponent_strength) * 0.25, -5, 5)
    return clamp(score, 20, 100), eliminated, champion


def rounded_percentages(raw_percentages: dict[str, float]) -> dict[str, float]:
    units = {team: int(math.floor(value * 10 + 1e-9)) for team, value in raw_percentages.items()}
    missing = 1000 - sum(units.values())
    order = sorted(raw_percentages, key=lambda team: (raw_percentages[team] * 10 - units[team], raw_percentages[team], team), reverse=True)
    for team in order[:missing]:
        units[team] += 1
    return {team: value / 10 for team, value in units.items()}


def probability_distribution(rows: list[dict]) -> dict[str, float]:
    champion = next((row["team"] for row in rows if row["champion"]), None)
    if champion:
        return {row["team"]: 100.0 if row["team"] == champion else 0.0 for row in rows}

    active = [row for row in rows if not row["eliminated"]]
    if not active:
        raise ValueError("没有可参与冠军概率计算的球队")
    max_score = max(row["composite_score"] for row in active)
    weights = {
        row["team"]: math.exp((row["composite_score"] - max_score) / SOFTMAX_TEMPERATURE)
        for row in active
    }
    total = sum(weights.values())
    raw = {team: weight / total * 100 for team, weight in weights.items()}
    rounded = rounded_percentages(raw)
    return {row["team"]: rounded.get(row["team"], 0.0) for row in rows}


def summary_for(row: dict) -> str:
    if row["champion"]:
        return "已夺得本届赛事冠军"
    stats = row["form_stats"]
    if not stats["played"]:
        return "赛前综合实力模型"
    goal_difference = stats["goal_difference"]
    sign = "+" if goal_difference > 0 else ""
    return f"近{stats['played']}场 {stats['won']}胜{stats['drawn']}平{stats['lost']}负，净胜球{sign}{goal_difference}"


def build_predictions(app_data: dict, seed_data: dict, generated_at: datetime, top_count: int = 12) -> dict:
    matches = list(app_data.get("matches") or [])
    strengths = {str(team): float(score) for team, score in (seed_data.get("teams") or {}).items()}
    teams = tournament_teams(matches)
    missing = [team for team in teams if team not in strengths]
    if missing:
        raise ValueError(f"实力种子缺少球队: {', '.join(missing)}")
    if not teams:
        raise ValueError("app_data.json 中没有可识别的小组赛球队")

    standings = standings_by_team(app_data)
    rows = []
    for team in teams:
        strength = strengths[team]
        form, form_stats = recent_form(team, matches, strength)
        path, eliminated, champion = path_score(team, matches, standings, strengths)
        composite = strength * MODEL_WEIGHTS["strength"] + form * MODEL_WEIGHTS["form"] + path * MODEL_WEIGHTS["path"]
        rows.append({
            "team": team,
            "strength_score": round(strength),
            "form_score": round(form),
            "path_score": round(path),
            "composite_score": composite,
            "eliminated": eliminated,
            "champion": champion,
            "form_stats": form_stats,
        })

    probabilities = probability_distribution(rows)
    rows.sort(key=lambda row: (probabilities[row["team"]], row["composite_score"], row["team"]), reverse=True)
    visible = rows[:top_count]
    other_probability = round(sum(probabilities[row["team"]] for row in rows[top_count:]), 1)
    finished_matches = sum(is_finished(match) for match in matches)
    generated_text = generated_at.astimezone(BEIJING).replace(microsecond=0).isoformat()

    return {
        "model_version": MODEL_VERSION,
        "generated_at": generated_text,
        "status": "model",
        "source_label": "赛前实力种子 + 最新赛果统计模型",
        "data_freshness": {
            "app_data_generated_at": app_data.get("generated_at", ""),
            "live_last_updated": app_data.get("live_last_updated", ""),
            "finished_matches": finished_matches,
        },
        "sources": [
            {
                "title": "项目赛程、赛果、积分榜与淘汰赛数据",
                "path": "data/app_data.json",
                "last_updated": app_data.get("generated_at", ""),
            },
            {
                "title": seed_data.get("source_label", "赛前实力种子"),
                "path": "data/team_strength_seed.json",
                "last_updated": seed_data.get("as_of", ""),
            },
        ],
        "other_probability": other_probability,
        "methodology": [
            {
                "label": "球队实力",
                "weight": 45,
                "description": "赛前相对实力种子，作为每日模型的稳定基线",
            },
            {
                "label": "近期状态",
                "weight": 30,
                "description": "最近五场赛事内战绩、积分效率与净胜球趋势",
            },
            {
                "label": "晋级路径",
                "weight": 25,
                "description": "小组排名、淘汰赛进度与未来对手相对难度",
            },
        ],
        "teams": [
            {
                "team": row["team"],
                "champion_probability": probabilities[row["team"]],
                "strength_score": row["strength_score"],
                "form_score": row["form_score"],
                "path_score": row["path_score"],
                "summary": summary_for(row),
            }
            for row in visible
        ],
    }


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def should_update(previous: dict, now: datetime, daily_after_hour: int | None, force: bool) -> tuple[bool, str]:
    if force or daily_after_hour is None:
        return True, "强制或未启用日更门控"
    if not previous:
        return True, "预测文件不存在，生成初始结果"
    local_now = now.astimezone(BEIJING)
    if local_now.hour < daily_after_hour:
        return False, f"北京时间尚未到 {daily_after_hour:02d}:00"
    previous_time = parse_datetime(str(previous.get("generated_at") or ""))
    if previous.get("status") == "model" and previous_time:
        previous_local = previous_time.astimezone(BEIJING)
        if previous_local.date() == local_now.date() and previous_local.hour >= daily_after_hour:
            return False, "今天已经在日更时间后生成过预测"
    return True, "进入今天的预测更新时间"


def main() -> int:
    parser = argparse.ArgumentParser(description="根据最新战况生成每日冠军概率。")
    parser.add_argument("--app-data", type=Path, default=ROOT / "data" / "app_data.json")
    parser.add_argument("--strength-seed", type=Path, default=ROOT / "data" / "team_strength_seed.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "champion_predictions.json")
    parser.add_argument("--daily-after-hour", type=int, choices=range(0, 24))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--now", help="测试或回放使用的 ISO 时间；默认当前时间")
    args = parser.parse_args()

    now = parse_datetime(args.now) if args.now else datetime.now(BEIJING)
    if now is None:
        raise SystemExit("--now 必须是有效 ISO 时间")
    previous = load_json(args.output) if args.output.exists() else {}
    update, reason = should_update(previous, now, args.daily_after_hour, args.force)
    if not update:
        print(f"跳过冠军预测更新: {reason}")
        return 0

    payload = build_predictions(load_json(args.app_data), load_json(args.strength_seed), now)
    write_json(args.output, payload)
    total = sum(float(row["champion_probability"]) for row in payload["teams"]) + float(payload["other_probability"])
    if round(total, 1) != 100.0:
        raise SystemExit(f"冠军概率合计异常: {total}")
    print(f"已生成冠军预测: {args.output} ({payload['data_freshness']['finished_matches']} 场已结束比赛，概率合计 {total:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
