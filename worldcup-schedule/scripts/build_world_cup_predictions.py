from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from build_champion_predictions import BEIJING, load_json, should_update
from team_features import build_team_features, write_feature_csv
from tournament_simulator import TournamentSimulator


ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "Poisson + 50,000次蒙特卡洛 v1.0"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def probability_frame(payload: dict) -> pd.DataFrame:
    rows = []
    for item in payload["team_probabilities"]:
        row = {
            "team": item["team"],
            "group": item["group"],
            "group_1st": item["group_position_probabilities"]["1"],
            "group_2nd": item["group_position_probabilities"]["2"],
            "group_3rd": item["group_position_probabilities"]["3"],
            "group_4th": item["group_position_probabilities"]["4"],
            "round_of_32": item["round_of_32"],
            "round_of_16": item["round_of_16"],
            "quarterfinal": item["quarterfinal"],
            "semifinal": item["semifinal"],
            "final": item["final"],
            "champion": item["champion"],
            "most_likely_path": item["most_likely_path"],
            "elo": item["strength"]["elo"],
            "fifa_rank": item["strength"]["fifa_rank"],
            "attack_strength": item["strength"]["attack"],
            "defense_strength": item["strength"]["defense"],
            "form_score": item["strength"]["form"],
        }
        rows.append(row)
    return pd.DataFrame(rows)


def group_probability_frame(payload: dict) -> pd.DataFrame:
    rows = []
    for group in payload["group_probabilities"]:
        for team in group["teams"]:
            positions = team["group_position_probabilities"]
            rows.append({
                "group": group["group"],
                "team": team["team"],
                "first": positions["1"],
                "second": positions["2"],
                "third": positions["3"],
                "fourth": positions["4"],
                "qualify_round_of_32": team["round_of_32"],
            })
    return pd.DataFrame(rows)


def match_probability_frame(payload: dict) -> pd.DataFrame:
    return pd.DataFrame(payload["match_predictions"])


def compatibility_champion_payload(payload: dict, app_data: dict, features: pd.DataFrame) -> dict:
    by_team = features.set_index("team").to_dict("index")
    teams = payload["team_probabilities"][:12]
    visible_total = round(sum(float(team["champion"]) for team in teams), 1)
    return {
        "model_version": MODEL_VERSION,
        "generated_at": payload["generated_at"],
        "status": "model",
        "source_label": "历史 Elo、近20场攻防、Poisson比分与完整赛事模拟",
        "data_freshness": {
            "app_data_generated_at": app_data.get("generated_at", ""),
            "live_last_updated": app_data.get("live_last_updated", ""),
            "finished_matches": sum(bool(match.get("is_finished")) for match in app_data.get("matches") or []),
            "simulations": payload["simulations"],
        },
        "sources": payload["sources"],
        "other_probability": round(max(0.0, 100.0 - visible_total), 1),
        "methodology": [
            {"label": "长期实力", "weight": 40, "description": "历史 Elo 与可手动导入的 FIFA 排名构成赛前实力基线"},
            {"label": "攻防状态", "weight": 35, "description": "近20场进球、失球和时间衰减状态估计预期进球"},
            {"label": "赛事模拟", "weight": 25, "description": "Poisson 比分模型驱动完整小组赛和官方淘汰赛路径模拟"},
        ],
        "teams": [
            {
                "team": item["team"],
                "champion_probability": item["champion"],
                "strength_score": int(round(75 + (float(by_team[item["team"]]["elo"]) - 1500) / 10)),
                "historical_elo": item["strength"]["elo"],
                "historical_matches": int(by_team[item["team"]]["last20_played"]),
                "historical_record": {
                    "won": int(by_team[item["team"]]["last20_wins"]),
                    "drawn": int(by_team[item["team"]]["last20_draws"]),
                    "lost": int(by_team[item["team"]]["last20_losses"]),
                },
                "form_score": int(round(float(item["strength"]["form"]) * 100)),
                "path_score": item["round_of_16"],
                "summary": f"32强 {item['round_of_32']:.1f}% · 16强 {item['round_of_16']:.1f}%",
            }
            for item in teams
        ],
    }


def export_results(payload: dict, features: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    probabilities = probability_frame(payload)
    groups = group_probability_frame(payload)
    matches = match_probability_frame(payload)
    probabilities.to_csv(output_dir / "worldcup_prediction_probabilities.csv", index=False, encoding="utf-8-sig")
    groups.to_csv(output_dir / "worldcup_group_probabilities.csv", index=False, encoding="utf-8-sig")
    matches.to_csv(output_dir / "worldcup_match_predictions.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(output_dir / "worldcup_prediction_model.xlsx", engine="openpyxl") as writer:
        probabilities.to_excel(writer, sheet_name="晋级概率", index=False)
        groups.to_excel(writer, sheet_name="小组排名概率", index=False)
        matches.to_excel(writer, sheet_name="单场预测", index=False)
        features.to_excel(writer, sheet_name="球队模型输入", index=False)


def build_payload(app_data: dict, history: dict, ratings: dict, features: pd.DataFrame, simulations: int, seed: int, generated_at: datetime) -> dict:
    simulation = TournamentSimulator(app_data, features, simulations=simulations, seed=seed).run()
    return {
        "model_version": MODEL_VERSION.replace("50,000", f"{simulations:,}"),
        "generated_at": generated_at.astimezone(BEIJING).replace(microsecond=0).isoformat(),
        "status": "model",
        "simulations": simulations,
        "sources": [
            {"title": "世界杯赛程、实时赛果与积分", "path": "data/app_data.json", "last_updated": app_data.get("generated_at", "")},
            {"title": "过去24个月国际比赛", "path": "data/historical_results.json", "last_updated": history.get("generated_at", "")},
            {"title": ratings.get("source_label", "时间衰减 Elo"), "path": "data/team_strength_ratings.json", "last_updated": ratings.get("as_of", "")},
            {"title": "手动球队指标覆盖", "path": "data/team_model_overrides.csv", "last_updated": "按文件内容"},
        ],
        "methodology": {
            "match_model": "Elo/FIFA差、近20场进攻强度、防守强度、近期状态与东道主因素生成预期进球；Poisson分布生成比分。",
            "group_tiebreakers": "积分、净胜球、进球数、同分球队相互积分/净胜球/进球数、公平竞赛分；仍相同时以模型评分稳定排序。",
            "qualification": "每组前二和12个小组第三中排名最高的8队进入32强。",
            "knockout": simulation["third_place_allocation"],
        },
        **simulation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成2026世界杯 Poisson + 蒙特卡洛完整预测。")
    parser.add_argument("--app-data", type=Path, default=ROOT / "data" / "app_data.json")
    parser.add_argument("--history", type=Path, default=ROOT / "data" / "historical_results.json")
    parser.add_argument("--ratings", type=Path, default=ROOT / "data" / "team_strength_ratings.json")
    parser.add_argument("--overrides", type=Path, default=ROOT / "data" / "team_model_overrides.csv")
    parser.add_argument("--features-output", type=Path, default=ROOT / "data" / "team_model_inputs.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "tournament_predictions.json")
    parser.add_argument("--champion-output", type=Path, default=ROOT / "data" / "champion_predictions.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--simulations", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=20260620)
    parser.add_argument("--daily-after-hour", type=int, choices=range(0, 24))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--now", help="测试或回放使用的 ISO 时间")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(BEIJING)
    previous = load_json(args.output) if args.output.exists() else {}
    update, reason = should_update(previous, now, args.daily_after_hour, args.force)
    if not update:
        print(f"跳过完整世界杯预测更新: {reason}")
        return 0
    app_data = load_json(args.app_data)
    history = load_json(args.history)
    ratings = load_json(args.ratings)
    features = build_team_features(history, ratings, app_data, args.overrides)
    write_feature_csv(features, args.features_output)
    payload = build_payload(app_data, history, ratings, features, args.simulations, args.seed, now)
    write_json(args.output, payload)
    write_json(args.champion_output, compatibility_champion_payload(payload, app_data, features))
    export_results(payload, features, args.output_dir)
    print(f"已生成完整世界杯预测: {args.output} ({args.simulations:,} 次模拟，{len(payload['team_probabilities'])} 支球队)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
