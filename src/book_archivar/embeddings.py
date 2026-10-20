from __future__ import annotations

import json
import urllib.request


class EmbeddingsClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        req = urllib.request.Request(
            self._url,
            data=json.dumps({"model": self._model, "input": texts}).encode(),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        return [item["embedding"] for item in data["data"]]
