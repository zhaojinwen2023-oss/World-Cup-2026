from __future__ import annotations

import os

from .base_provider import BaseProvider, ProviderError


class LiveScoreProvider(BaseProvider):
    def fetch(self) -> dict:
        if not os.getenv("LIVESCORE_API_KEY"):
            raise ProviderError("LiveScore API 需要 LIVESCORE_API_KEY。没有 key 时请使用 --source local 或 --source google_sheet。")
        raise ProviderError("LiveScore API 适配器已预留；需要你的 API 响应样例后映射 match_id。")
