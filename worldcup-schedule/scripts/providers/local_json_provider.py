from __future__ import annotations

from pathlib import Path

from schedule_utils import default_knockout_bracket_path, default_live_results_path, default_standings_path, load_json
from .base_provider import BaseProvider


class LocalJsonProvider(BaseProvider):
    def __init__(self, live_path: Path | None = None, standings_path: Path | None = None, knockout_path: Path | None = None):
        self.live_path = live_path or default_live_results_path()
        self.standings_path = standings_path or default_standings_path()
        self.knockout_path = knockout_path or default_knockout_bracket_path()

    def fetch(self) -> dict:
        live = load_json(self.live_path, {"results": []})
        standings = load_json(self.standings_path, {"standings": []})
        knockout = load_json(self.knockout_path, {"knockout": []})
        return {
            "matches": live.get("results", live.get("matches", [])) if isinstance(live, dict) else live,
            "standings": standings.get("standings", []) if isinstance(standings, dict) else standings,
            "knockout": knockout.get("knockout", []) if isinstance(knockout, dict) else knockout,
            "last_updated": live.get("last_updated", "") if isinstance(live, dict) else "",
        }
