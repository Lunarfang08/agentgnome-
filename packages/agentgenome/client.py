from collections.abc import AsyncIterator
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(f"AgentGenome API error {status}: {code}")
        self.status, self.code = status, code


class AsyncClient:
    """Initial typed-resource transport; no unsafe automatic write retries."""

    def __init__(self, base_url: str, token: str, timeout: float = 10):
        self.http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/api/v1/",
            headers={"Authorization": "Bearer " + token},
            timeout=timeout,
            follow_redirects=False,
        )

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.http.aclose()

    async def request(self, method: str, resource: str, **kwargs: Any) -> dict[str, Any]:
        response = await self.http.request(method, resource.lstrip("/"), **kwargs)
        if response.is_error:
            try:
                code = str(response.json().get("code", "request_failed"))
            except ValueError:
                code = "request_failed"
            raise ApiError(response.status_code, code)
        return dict(response.json())

    async def run(self, genome_id: str, task: str, idempotency_key: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            "runs",
            json={"genome_id": genome_id, "task": task},
            headers={"Idempotency-Key": idempotency_key},
        )

    async def events(self, run_id: str, last_event_id: int = 0) -> AsyncIterator[str]:
        # Explicit caller cursor; transparent reconnect is pending.
        async with self.http.stream(
            "GET", f"runs/{run_id}/events", headers={"Last-Event-ID": str(last_event_id)}
        ) as response:
            if response.is_error:
                raise ApiError(response.status_code, "event_stream_failed")
            async for line in response.aiter_lines():
                yield line
