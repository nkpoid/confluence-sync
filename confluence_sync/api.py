from __future__ import annotations

import time
from typing import Any, Iterator

import requests

from .config import Config

MAX_RETRIES = 3
BACKOFF_BASE = 1.0


class ConfluenceAPI:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        pat = config.get_pat()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {pat}",
                "Accept": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.config.base_url}{path}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.request(method, url, timeout=30, **kwargs)
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < MAX_RETRIES - 1:
                        wait = BACKOFF_BASE * (2**attempt)
                        time.sleep(wait)
                        continue
                resp.raise_for_status()
                return resp
            except requests.ConnectionError:
                if attempt < MAX_RETRIES - 1:
                    wait = BACKOFF_BASE * (2**attempt)
                    time.sleep(wait)
                    continue
                raise
        return resp  # type: ignore[return-value]

    def get_spaces(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start = 0
        limit = 50
        while True:
            resp = self._request(
                "GET",
                "/rest/api/space",
                params={"start": start, "limit": limit, "type": "global"},
            )
            data = resp.json()
            results.extend(data.get("results", []))
            if data.get("size", 0) < limit:
                break
            start += limit
        return results

    def search_pages(
        self, cql: str, limit: int = 50
    ) -> Iterator[dict[str, Any]]:
        start = 0
        while True:
            resp = self._request(
                "GET",
                "/rest/api/content/search",
                params={
                    "cql": cql,
                    "limit": limit,
                    "start": start,
                    "expand": "version,metadata.labels,space,body.storage",
                },
            )
            data = resp.json()
            results = data.get("results", [])
            yield from results
            if data.get("size", 0) < limit:
                break
            start += limit

    def get_page(self, page_id: str) -> dict[str, Any]:
        resp = self._request(
            "GET",
            f"/rest/api/content/{page_id}",
            params={"expand": "version,metadata.labels,space,body.storage"},
        )
        return resp.json()

    def page_exists(self, page_id: str) -> bool:
        try:
            url = f"{self.config.base_url}/rest/api/content/{page_id}"
            resp = self.session.get(url, timeout=30, params={"expand": "version"})
            return resp.status_code == 200
        except requests.RequestException:
            return True  # assume exists on error

    def get_attachments(self, page_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start = 0
        limit = 50
        while True:
            resp = self._request(
                "GET",
                f"/rest/api/content/{page_id}/child/attachment",
                params={"start": start, "limit": limit},
            )
            data = resp.json()
            results.extend(data.get("results", []))
            if data.get("size", 0) < limit:
                break
            start += limit
        return results

    def download_attachment(self, download_path: str) -> bytes:
        url = f"{self.config.base_url}{download_path}"
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content
