import hashlib
import json
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Metadata(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    parents: list[str] = Field(default_factory=list, max_length=20)


class Model(Strict):
    route: str = Field(min_length=1, max_length=100)
    fallbackRoutes: list[str] = Field(default_factory=list, max_length=5)


class Harness(Strict):
    strategy: Literal["plan-execute-verify", "tool-loop", "dag"] = "plan-execute-verify"
    maxIterations: int = Field(default=30, ge=1, le=1000)
    checkpointEachStep: Literal[True] = True


class Context(Strict):
    maxInputTokens: int = Field(default=48000, ge=256, le=1000000)
    reservedOutputTokens: int = Field(default=4096, ge=1)
    compactionThreshold: float = Field(default=0.75, gt=0, lt=1)
    progressiveDisclosure: bool = True
    preserve: list[str] = Field(
        default_factory=lambda: ["requirements", "policy", "openActions", "decisions"]
    )


class Memory(Strict):
    namespaces: list[Literal["semantic", "episodic", "procedural"]] = Field(default_factory=list)
    topK: int = Field(default=5, ge=0, le=100)
    writePolicy: Literal["verified-only"] = "verified-only"


class Tools(Strict):
    allowed: list[str] = Field(max_length=100)
    programmaticCalling: bool = False
    maxCalls: int = Field(default=100, ge=1, le=10000)
    maxConcurrency: int = Field(default=5, ge=1, le=100)


class Sandbox(Strict):
    profile: Literal["trusted-fixture", "restricted-gvisor", "firecracker"]
    cpu: int = Field(default=2, ge=1, le=64)
    memoryMiB: int = Field(default=1024, ge=64, le=65536)
    networkPolicy: Literal["deny-by-default"] = "deny-by-default"


class Limits(Strict):
    maxWallSeconds: int = Field(default=900, ge=1, le=86400)
    maxCostUsd: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=6)]
    maxTotalTokens: int = Field(default=150000, ge=1, le=10000000)


class Evaluation(Strict):
    suite: str = Field(min_length=1, max_length=100)


class Evolution(Strict):
    enabled: bool = False
    mutablePaths: list[str] = Field(default_factory=list)
    approvalRequired: Literal[True] = True

    @model_validator(mode="after")
    def protected(self) -> "Evolution":
        allowed = {"harness.strategy", "context", "skills", "memory.topK"}
        if not set(self.mutablePaths) <= allowed:
            raise ValueError("protected evolution path")
        return self


class Spec(Strict):
    model: Model
    harness: Harness = Field(default_factory=Harness)
    context: Context = Field(default_factory=Context)
    skills: list[str] = Field(default_factory=list, max_length=100)
    memory: Memory = Field(default_factory=Memory)
    tools: Tools
    sandbox: Sandbox
    limits: Limits
    evaluation: Evaluation
    evolution: Evolution = Field(default_factory=Evolution)


class Manifest(Strict):
    apiVersion: Literal["agentgenome.io/v1"]
    kind: Literal["AgentGenome"]
    metadata: Metadata
    spec: Spec

    def canonical(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical()).hexdigest()
