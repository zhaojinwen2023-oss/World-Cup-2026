from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from build_champion_predictions import canonical_team, is_finished, rounded_percentages
from match_prediction_model import MatchPredictionModel


STAGE_KEYS = ("round_of_32", "round_of_16", "quarterfinal", "semifinal", "final", "champion")
FINISH_LABELS = {
    "group_stage": "小组赛",
    "round_of_32": "32强",
    "round_of_16": "16强",
    "quarterfinal": "8强",
    "semifinal": "4强",
    "final": "亚军",
    "champion": "冠军",
}


@dataclass
class GroupSimulation:
    teams: list[str]
    points: np.ndarray
    goals_for: np.ndarray
    goals_against: np.ndarray
    rankings: np.ndarray
    fixtures: list[tuple[int, int, np.ndarray, np.ndarray]]


def source_group(source: str, kind: str) -> str | None:
    pattern = r"Winner\s+Group\s+([A-L])" if kind == "winner" else r"(?:Runner-up|Second)\s+Group\s+([A-L])"
    match = re.search(pattern, source, flags=re.I)
    return match.group(1).upper() if match else None


def third_groups(source: str) -> tuple[str, ...]:
    match = re.search(r"(?:3rd|Third)(?:\s+place)?\s+Group\s+([A-L](?:/[A-L])*)", source, flags=re.I)
    return tuple(match.group(1).upper().split("/")) if match else ()


def previous_match(source: str, kind: str = "winner") -> int | None:
    pattern = r"Winner\s+Match\s+(\d+)" if kind == "winner" else r"Loser\s+Match\s+(\d+)"
    match = re.search(pattern, source, flags=re.I)
    return int(match.group(1)) if match else None


class TournamentSimulator:
    def __init__(self, app_data: dict, features: pd.DataFrame, simulations: int = 50_000, seed: int = 20260620):
        if simulations < 1:
            raise ValueError("simulations 必须大于0")
        self.app_data = app_data
        self.matches = sorted(app_data.get("matches") or [], key=lambda row: int(row.get("match_id", 0)))
        self.features = features.set_index("team")
        self.model = MatchPredictionModel(features)
        self.simulations = simulations
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.group_rows = [row for row in self.matches if row.get("stage") == "Group Stage"]
        self.knockout_rows = [row for row in self.matches if row.get("stage") != "Group Stage"]
        self.groups = self._group_teams()
        self.team_group = {team: group for group, teams in self.groups.items() for team in teams}
        self.fair_play = {
            canonical_team(row.get("team")): int(row.get("fair_play_points") or 0)
            for row in app_data.get("standings") or []
        }
        self.stage_counts = {team: Counter() for team in self.features.index}
        self.finish_counts = {team: Counter() for team in self.features.index}
        self._advance_cache: dict[tuple[str, str, str], float] = {}
        self._third_slot_rules = {
            int(row["match_id"]): third_groups(str(row.get("home_placeholder") or row.get("home_source") or ""))
            or third_groups(str(row.get("away_placeholder") or row.get("away_source") or ""))
            for row in self.knockout_rows
            if third_groups(str(row.get("home_placeholder") or row.get("home_source") or ""))
            or third_groups(str(row.get("away_placeholder") or row.get("away_source") or ""))
        }

    def _group_teams(self) -> dict[str, list[str]]:
        groups: dict[str, set[str]] = defaultdict(set)
        for row in self.group_rows:
            group = str(row.get("group") or str(row.get("round") or "").replace("Group ", ""))
            groups[group].add(canonical_team(row.get("home_team")))
            groups[group].add(canonical_team(row.get("away_team")))
        result = {group: sorted(teams) for group, teams in groups.items()}
        if len(result) != 12 or any(len(teams) != 4 for teams in result.values()):
            raise ValueError("世界杯小组结构必须为12组、每组4队")
        return dict(sorted(result.items()))

    def _score_arrays(self, row: dict) -> tuple[np.ndarray, np.ndarray]:
        if is_finished(row):
            home = np.full(self.simulations, int(row.get("home_score", 0)), dtype=np.int16)
            away = np.full(self.simulations, int(row.get("away_score", 0)), dtype=np.int16)
            return home, away
        home_team = canonical_team(row.get("home_team"))
        away_team = canonical_team(row.get("away_team"))
        distribution = self.model.score_distribution(home_team, away_team, str(row.get("country") or ""))
        sampled = self.rng.choice(distribution.size, size=self.simulations, p=distribution)
        width = self.model.max_goals + 1
        return (sampled // width).astype(np.int16), (sampled % width).astype(np.int16)

    def _simulate_groups(self) -> dict[str, GroupSimulation]:
        simulations = {}
        for group, teams in self.groups.items():
            index = {team: position for position, team in enumerate(teams)}
            points = np.zeros((self.simulations, 4), dtype=np.int16)
            goals_for = np.zeros((self.simulations, 4), dtype=np.int16)
            goals_against = np.zeros((self.simulations, 4), dtype=np.int16)
            fixtures = []
            for row in [item for item in self.group_rows if str(item.get("group") or "") == group]:
                home_team = canonical_team(row.get("home_team"))
                away_team = canonical_team(row.get("away_team"))
                home_index, away_index = index[home_team], index[away_team]
                home_goals, away_goals = self._score_arrays(row)
                fixtures.append((home_index, away_index, home_goals, away_goals))
                goals_for[:, home_index] += home_goals
                goals_against[:, home_index] += away_goals
                goals_for[:, away_index] += away_goals
                goals_against[:, away_index] += home_goals
                home_wins = home_goals > away_goals
                away_wins = away_goals > home_goals
                draws = home_goals == away_goals
                points[:, home_index] += home_wins * 3 + draws
                points[:, away_index] += away_wins * 3 + draws
            rankings = self._rank_group_rows(teams, points, goals_for, goals_against, fixtures)
            simulations[group] = GroupSimulation(teams, points, goals_for, goals_against, rankings, fixtures)
        return simulations

    def _rank_group_rows(
        self,
        teams: list[str],
        points: np.ndarray,
        goals_for: np.ndarray,
        goals_against: np.ndarray,
        fixtures: list[tuple[int, int, np.ndarray, np.ndarray]],
    ) -> np.ndarray:
        goal_difference = goals_for - goals_against
        base_key = points.astype(np.int64) * 1_000_000 + (goal_difference.astype(np.int64) + 50) * 10_000 + goals_for.astype(np.int64) * 100
        rankings = np.argsort(-base_key, axis=1, kind="stable")
        ordered_keys = np.take_along_axis(base_key, rankings, axis=1)
        tie_rows = np.where(np.any(ordered_keys[:, 1:] == ordered_keys[:, :-1], axis=1))[0]
        ratings = [self.model.rating(team) for team in teams]
        fair_play = [self.fair_play.get(team, 0) for team in teams]
        for simulation_index in tie_rows:
            order = rankings[simulation_index].tolist()
            start = 0
            while start < 4:
                end = start + 1
                while end < 4 and base_key[simulation_index, order[end]] == base_key[simulation_index, order[start]]:
                    end += 1
                tied = order[start:end]
                if len(tied) > 1:
                    h_points = {team_index: 0 for team_index in tied}
                    h_for = {team_index: 0 for team_index in tied}
                    h_against = {team_index: 0 for team_index in tied}
                    for home_index, away_index, home_goals, away_goals in fixtures:
                        if home_index not in h_points or away_index not in h_points:
                            continue
                        home_score = int(home_goals[simulation_index])
                        away_score = int(away_goals[simulation_index])
                        h_for[home_index] += home_score
                        h_against[home_index] += away_score
                        h_for[away_index] += away_score
                        h_against[away_index] += home_score
                        if home_score > away_score:
                            h_points[home_index] += 3
                        elif away_score > home_score:
                            h_points[away_index] += 3
                        else:
                            h_points[home_index] += 1
                            h_points[away_index] += 1
                    tied.sort(key=lambda team_index: (h_points[team_index], h_for[team_index] - h_against[team_index], h_for[team_index], -fair_play[team_index], ratings[team_index]), reverse=True)
                    order[start:end] = tied
                start = end
            rankings[simulation_index] = order
        return rankings

    @lru_cache(maxsize=600)
    def _third_assignment_options(self, qualified_groups: tuple[str, ...]) -> tuple[tuple[tuple[int, str], ...], ...]:
        slots = tuple(sorted(self._third_slot_rules))
        options = []

        def assign(position: int, used: set[str], mapping: list[tuple[int, str]]) -> None:
            if position == len(slots):
                options.append(tuple(mapping))
                return
            slot = slots[position]
            for group in qualified_groups:
                if group not in used and group in self._third_slot_rules[slot]:
                    assign(position + 1, used | {group}, [*mapping, (slot, group)])

        assign(0, set(), [])
        if not options:
            raise ValueError(f"无法为最佳第三名分配32强槽位: {qualified_groups}")
        return tuple(options)

    def _third_assignment(self, qualified_groups: list[str]) -> dict[int, str]:
        options = self._third_assignment_options(tuple(sorted(qualified_groups)))
        selected = options[int(self.rng.integers(0, len(options)))]
        return dict(selected)

    def _resolve_source(self, source: str, positions: dict[str, list[str]], third_assignment: dict[int, str], match_id: int, results: dict[int, tuple[str, str]]) -> str:
        winner_group = source_group(source, "winner")
        if winner_group:
            return positions[winner_group][0]
        runner_group = source_group(source, "runner")
        if runner_group:
            return positions[runner_group][1]
        if third_groups(source):
            return positions[third_assignment[match_id]][2]
        winner_match = previous_match(source, "winner")
        if winner_match:
            return results[winner_match][0]
        loser_match = previous_match(source, "loser")
        if loser_match:
            return results[loser_match][1]
        return canonical_team(source)

    def _sample_knockout(self, home: str, away: str, country: str) -> tuple[str, str]:
        key = (home, away, country)
        probability = self._advance_cache.get(key)
        if probability is None:
            probability = self.model.home_advancement_probability(home, away, country)
            self._advance_cache[key] = probability
        return (home, away) if self.rng.random() < probability else (away, home)

    def _simulate_knockout(self, group_simulations: dict[str, GroupSimulation]) -> None:
        rows = {int(row["match_id"]): row for row in self.knockout_rows}
        for simulation_index in range(self.simulations):
            positions = {
                group: [state.teams[index] for index in state.rankings[simulation_index]]
                for group, state in group_simulations.items()
            }
            thirds = []
            for group, state in group_simulations.items():
                local_index = int(state.rankings[simulation_index, 2])
                team = state.teams[local_index]
                thirds.append((team, group, int(state.points[simulation_index, local_index]), int(state.goals_for[simulation_index, local_index] - state.goals_against[simulation_index, local_index]), int(state.goals_for[simulation_index, local_index]), -self.fair_play.get(team, 0), self.model.rating(team)))
            thirds.sort(key=lambda item: (item[2], item[3], item[4], item[5], item[6]), reverse=True)
            qualified_thirds = thirds[:8]
            qualified = {team for group in positions.values() for team in group[:2]} | {item[0] for item in qualified_thirds}
            for team in self.features.index:
                if team in qualified:
                    self.stage_counts[team]["round_of_32"] += 1
                else:
                    self.finish_counts[team]["group_stage"] += 1
            assignment = self._third_assignment([item[1] for item in qualified_thirds])
            results: dict[int, tuple[str, str]] = {}
            for match_id in sorted(rows):
                row = rows[match_id]
                source_home = str(row.get("home_placeholder") or row.get("home_source") or "")
                source_away = str(row.get("away_placeholder") or row.get("away_source") or "")
                home = self._resolve_source(source_home, positions, assignment, match_id, results)
                away = self._resolve_source(source_away, positions, assignment, match_id, results)
                if is_finished(row) and row.get("winner"):
                    winner = canonical_team(row.get("winner"))
                    loser = away if winner == home else home
                else:
                    winner, loser = self._sample_knockout(home, away, str(row.get("country") or ""))
                results[match_id] = (winner, loser)
                stage = str(row.get("stage") or "")
                if stage == "Round of 32":
                    self.stage_counts[winner]["round_of_16"] += 1
                    self.finish_counts[loser]["round_of_32"] += 1
                elif stage == "Round of 16":
                    self.stage_counts[winner]["quarterfinal"] += 1
                    self.finish_counts[loser]["round_of_16"] += 1
                elif stage == "Quarter-final":
                    self.stage_counts[winner]["semifinal"] += 1
                    self.finish_counts[loser]["quarterfinal"] += 1
                elif stage == "Semi-final":
                    self.stage_counts[winner]["final"] += 1
                    self.finish_counts[loser]["semifinal"] += 1
                elif stage == "Final":
                    self.stage_counts[winner]["champion"] += 1
                    self.finish_counts[loser]["final"] += 1
                    self.finish_counts[winner]["champion"] += 1

    def _team_probabilities(self, group_simulations: dict[str, GroupSimulation]) -> list[dict]:
        group_positions: dict[str, list[int]] = {team: [0, 0, 0, 0] for team in self.features.index}
        for state in group_simulations.values():
            for position in range(4):
                counts = np.bincount(state.rankings[:, position], minlength=4)
                for local_index, count in enumerate(counts):
                    group_positions[state.teams[local_index]][position] += int(count)
        rounded_stages = {
            stage: rounded_percentages({
                team: self.stage_counts[team][stage] / self.simulations * 100
                for team in self.features.index
            })
            for stage in STAGE_KEYS
        }
        output = []
        for team in self.features.index:
            position_probabilities = [round(count / self.simulations * 100, 1) for count in group_positions[team]]
            stage_probabilities = {stage: rounded_stages[stage][team] for stage in STAGE_KEYS}
            likely_finish = max(self.finish_counts[team], key=self.finish_counts[team].get)
            likely_group_position = int(np.argmax(position_probabilities)) + 1
            feature = self.features.loc[team]
            output.append({
                "team": team,
                "group": self.team_group[team],
                "group_position_probabilities": {str(index + 1): value for index, value in enumerate(position_probabilities)},
                **stage_probabilities,
                "most_likely_path": f"小组第{likely_group_position} → {FINISH_LABELS[likely_finish]}",
                "strength": {
                    "fifa_rank": None if pd.isna(feature.get("fifa_rank")) else int(feature["fifa_rank"]),
                    "elo": round(float(feature["elo"]), 1),
                    "attack": round(float(feature["attack_strength"]), 2),
                    "defense": round(float(feature["defense_strength"]), 2),
                    "form": round(float(feature["form_score"]), 2),
                },
            })
        return sorted(output, key=lambda row: (row["champion"], row["final"], row["semifinal"]), reverse=True)

    def match_predictions(self) -> list[dict]:
        predictions = []
        for row in self.group_rows:
            if is_finished(row):
                continue
            home = canonical_team(row.get("home_team"))
            away = canonical_team(row.get("away_team"))
            prediction = self.model.predict(home, away, str(row.get("country") or ""))
            home_rating, away_rating = self.model.rating(home), self.model.rating(away)
            if home_rating >= away_rating:
                favorite, underdog = home, away
                upset_probability = prediction["away_win_probability"]
            else:
                favorite, underdog = away, home
                upset_probability = prediction["home_win_probability"]
            predictions.append({
                "match_id": int(row["match_id"]),
                "group": str(row.get("group") or ""),
                "kickoff_utc": row.get("kickoff_utc", ""),
                "country": row.get("country", ""),
                **prediction,
                "favorite": favorite,
                "underdog": underdog,
                "rating_difference": round(abs(home_rating - away_rating), 1),
                "upset_probability": upset_probability,
            })
        return predictions

    def run(self) -> dict:
        group_simulations = self._simulate_groups()
        self._simulate_knockout(group_simulations)
        team_probabilities = self._team_probabilities(group_simulations)
        matches = self.match_predictions()
        upsets = sorted([row for row in matches if row["rating_difference"] >= 25], key=lambda row: row["upset_probability"], reverse=True)[:10]
        return {
            "simulations": self.simulations,
            "random_seed": self.seed,
            "team_probabilities": team_probabilities,
            "group_probabilities": [
                {
                    "group": group,
                    "teams": [row for row in team_probabilities if row["group"] == group],
                }
                for group in self.groups
            ],
            "match_predictions": matches,
            "upset_matches": upsets,
            "third_place_allocation": "按官方32强候选小组槽位进行无重复可行匹配；多个合法方案时在蒙特卡洛中均匀抽取",
        }
