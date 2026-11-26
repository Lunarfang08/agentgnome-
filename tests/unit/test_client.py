import httpx
import pytest
from agentgenome import ApiError, AsyncClient


async def test_client_error_and_write_idempotency():
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer private-token"
        assert request.headers["Idempotency-Key"] == "stable-key"
        return httpx.Response(429, json={"code": "quota"})

    async with AsyncClient("http://test", "private-token") as client:
        await client.http.aclose()
        client.http = httpx.AsyncClient(
            base_url="http://test/api/v1/",
            headers={"Authorization": "Bearer private-token"},
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ApiError) as error:
            await client.run("g", "task", "stable-key")
        assert error.value.status == 429
        assert "private-token" not in str(error.value)
    assert len(calls) == 1
