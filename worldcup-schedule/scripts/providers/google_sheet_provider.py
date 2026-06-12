from __future__ import annotations

import os

from .base_provider import BaseProvider, empty_payload, payload_from_url


class GoogleSheetProvider(BaseProvider):
    def __init__(self, live_url: str | None = None, standings_url: str | None = None, knockout_url: str | None = None):
        self.live_url = live_url or os.getenv("WORLDCUP_LIVE_URL")
        self.standings_url = standings_url or os.getenv("WORLDCUP_STANDINGS_URL")
        self.knockout_url = knockout_url or os.getenv("WORLDCUP_KNOCKOUT_URL")

    def fetch(self) -> dict:
        payload = empty_payload()
        if self.live_url:
            live_payload = payload_from_url(self.live_url, "matches")
            payload["matches"] = live_payload.get("matches", live_payload.get("results", []))
            payload["last_updated"] = live_payload.get("last_updated", "")
        if self.standings_url:
            standings_payload = payload_from_url(self.standings_url, "standings")
            payload["standings"] = standings_payload.get("standings", [])
        if self.knockout_url:
            knockout_payload = payload_from_url(self.knockout_url, "knockout")
            payload["knockout"] = knockout_payload.get("knockout", [])
        return payload
