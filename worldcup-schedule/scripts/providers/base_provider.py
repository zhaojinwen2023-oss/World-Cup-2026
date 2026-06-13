from __future__ import annotations

import csv
import json
import os
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

try:
    import requests
except ImportError:  # pragma: no cover - fallback for minimal local environments.
    requests = None


class ProviderError(RuntimeError):
    pass


class BaseProvider(ABC):
    @abstractmethod
    def fetch(self) -> dict[str, Any]:
        """Return {'matches': [], 'standings': [], 'knockout': []}."""


def load_env_file(path: Path | str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def http_get_text(url: str, headers: dict[str, str] | None = None) -> str:
    request_headers = headers or {"User-Agent": "worldcup-schedule/1.0"}
    if requests is not None:
        try:
            response = requests.get(url, headers=request_headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.HTTPError as exc:
            body = exc.response.text[:400] if exc.response is not None else ""
            code = exc.response.status_code if exc.response is not None else "unknown"
            raise ProviderError(f"HTTP {code}: {body}") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"网络请求失败: {exc}") from exc

    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8-sig")
    except HTTPError as exc:
        body = exc.read().decode("utf-8-sig", errors="replace")[:400]
        raise ProviderError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise ProviderError(f"网络请求失败: {exc.reason}") from exc


def http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    return json.loads(http_get_text(url, headers=headers))


def parse_csv_text(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(text.splitlines()))


def payload_from_url(url: str, root_key: str) -> dict:
    text = http_get_text(url)
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        payload = json.loads(text)
        return {root_key: payload} if isinstance(payload, list) else payload
    return {root_key: parse_csv_text(text)}


def empty_payload() -> dict[str, Any]:
    return {"matches": [], "standings": [], "knockout": []}
