from __future__ import annotations

import os

from .base_provider import BaseProvider, ProviderError, payload_from_url


class WorldCupApiProvider(BaseProvider):
    def fetch(self) -> dict:
        url = os.getenv("WORLDCUP_API_URL")
        if not url:
            raise ProviderError("WorldCupAPI 需要 WORLDCUP_API_URL。没有 URL 时请使用 --source local 或 --source google_sheet。")
        payload = payload_from_url(url, "matches")
        return {
            "matches": payload.get("matches", payload.get("results", [])),
            "standings": payload.get("standings", []),
            "knockout": payload.get("knockout", []),
            "last_updated": payload.get("last_updated", ""),
        }
