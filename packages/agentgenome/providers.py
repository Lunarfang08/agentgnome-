from typing import Any, Literal, Protocol

import httpx
from pydantic import Field, model_validator

from agentgenome.genome import Strict


class ModelResponse(Strict):
    kind: Literal["tool", "final"]
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    output: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_action(self) -> "ModelResponse":
        if self.kind == "tool" and (not self.tool or self.output is not None):
            raise ValueError("tool response requires a tool and no final output")
        if self.kind == "final" and (
            self.output is None or self.tool is not None or self.arguments
        ):
            raise ValueError("final response requires output and no tool action")
        return self


class ModelProvider(Protocol):
    async def generate(self, task: str, observations: list[dict[str, Any]]) -> ModelResponse: ...


class FixtureProvider:
    """Explicit deterministic procurement demo; never selected in production."""

    async def generate(self, task: str, observations: list[dict[str, Any]]) -> ModelResponse:
        steps = [
            ("inventory.read", {}),
            ("orders.prepare", {"item": "paper", "quantity": 2}),
            ("orders.submit", {"item": "paper", "quantity": 2}),
        ]
        if len(observations) < len(steps):
            tool, arguments = steps[len(observations)]
            return ModelResponse(
                kind="tool", tool=tool, arguments=arguments, input_tokens=32, output_tokens=16
            )
        return ModelResponse(
            kind="final",
            output="Approved simulated purchase order submitted once.",
            input_tokens=32,
            output_tokens=16,
        )


class OpenAICompatibleProvider:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not model:
            raise ValueError("model ID is required")
        self.endpoint, self.api_key, self.model = endpoint, api_key, model
        self.transport = transport

    async def generate(self, task: str, observations: list[dict[str, Any]]) -> ModelResponse:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=False, transport=self.transport
        ) as client:
            response = await client.post(
                self.endpoint.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + self.api_key},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Return JSON matching this schema: "
                            + str(ModelResponse.model_json_schema()),
                        },
                        {"role": "user", "content": task},
                        {"role": "user", "content": str(observations)},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()
            parsed = ModelResponse.model_validate_json(data["choices"][0]["message"]["content"])
            usage = data["usage"]
            return ModelResponse.model_validate(
                {
                    **parsed.model_dump(),
                    "input_tokens": usage["prompt_tokens"],
                    "output_tokens": usage["completion_tokens"],
                }
            )
