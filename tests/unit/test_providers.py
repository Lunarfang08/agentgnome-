import json

import httpx
import pytest
from agentgenome.providers import ModelResponse, OpenAICompatibleProvider
from pydantic import ValidationError


async def test_openai_compatible_contract_and_usage():
    def respond(request):
        assert request.url.path == "/v1/chat/completions"
        assert json.loads(request.content)["model"] == "operator-configured-model"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"kind": "tool", "tool": "inventory.read", "arguments": {}}
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    provider = OpenAICompatibleProvider(
        "https://provider.example/v1",
        "fixture-key",
        "operator-configured-model",
        httpx.MockTransport(respond),
    )
    result = await provider.generate("Read inventory", [])
    assert (result.input_tokens, result.output_tokens, result.tool) == (12, 5, "inventory.read")


async def test_provider_failure_is_not_success():
    provider = OpenAICompatibleProvider(
        "https://provider.example/v1",
        "fixture-key",
        "configured",
        httpx.MockTransport(lambda request: httpx.Response(429)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate("task", [])


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "tool"},
        {"kind": "final"},
        {"kind": "final", "output": "ok", "tool": "orders.submit"},
    ],
)
def test_invalid_model_actions_rejected(value):
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(value)
