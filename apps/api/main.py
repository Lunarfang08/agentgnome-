import asyncio
import hashlib
import json
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from agentgenome.auth import Authenticator, Identity
from agentgenome.config import Settings
from agentgenome.db import Agent, ApiKey, Approval, Audit, Database, Genome, Project, Run, RunEvent
from agentgenome.genome import Manifest
from agentgenome.http import BodyLimit
from agentgenome.service import TERMINAL, admit, audit, finish, scoped
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError


class NameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    genome_id: str
    task: str = Field(min_length=1, max_length=10000)


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scopes: list[str]
    expires_in_hours: int = Field(default=24, ge=1, le=720)


def run_view(run: Run) -> dict[str, Any]:
    return {
        "id": run.id,
        "genome_hash": run.genome_hash,
        "state": run.state,
        "task": run.task,
        "checkpoint": run.checkpoint,
        "result": run.result,
        "actual_cost": str(run.actual_cost),
        "created_at": run.created_at.isoformat(),
    }


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or Settings()
    database = database or Database(settings.database_url)
    auth = Authenticator(settings, database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await database.engine.dispose()

    app = FastAPI(title="AgentGenome", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodyLimit)
    app.state.database, app.state.settings = database, settings

    @app.middleware("http")
    async def headers(request: Request, call_next: Any) -> Response:
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        return response  # type: ignore[no-any-return]

    def problem(request: Request, status: int, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": "Request failed",
                "status": status,
                "detail": detail,
                "instance": request.url.path,
                "code": "http_" + str(status),
                "request_id": getattr(request.state, "request_id", ""),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return problem(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(request, 422, "request schema is invalid")

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError) -> JSONResponse:
        return problem(request, 409, "resource conflict")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        return problem(request, 500, "internal error; use request ID for support")

    bearer_scheme = HTTPBearer(auto_error=False)

    async def identity(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ) -> Identity:
        if credentials is None:
            raise HTTPException(401, "bearer token required")
        return await auth.authenticate(credentials.credentials)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "alive", "profile": settings.profile}

    @app.get("/readyz")
    async def ready(response: Response) -> dict[str, Any]:
        async def db_check() -> None:
            async with database.sessions() as session:
                await session.execute(text("SELECT 1"))
                revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != "0002":
                    raise RuntimeError("database migrations are not current")

        async def redis_check() -> None:
            async with Redis.from_url(settings.redis_url) as client:
                await client.ping()

        async def temporal_check() -> None:
            from temporalio.client import Client

            client = await Client.connect(settings.temporal_address)
            await client.service_client.check_health()

        async def artifact_check() -> None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key.get_secret_value(),
                aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
                config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 0}),
            )
            await asyncio.to_thread(client.head_bucket, Bucket=settings.s3_bucket)

        async def check(name: str, operation: Any) -> tuple[str, str]:
            try:
                await asyncio.wait_for(operation(), timeout=4)
                return name, "ready"
            except Exception:
                return name, "unavailable"

        checks = dict(
            await asyncio.gather(
                check("database", db_check),
                check("redis", redis_check),
                check("temporal", temporal_check),
                check("artifacts", artifact_check),
            )
        )
        if any(value != "ready" for value in checks.values()):
            response.status_code = 503
        return {"checks": checks}

    @app.get("/api/v1/me")
    async def me(who: Annotated[Identity, Depends(identity)]) -> dict[str, Any]:
        return {
            "subject": who.subject,
            "tenant_id": who.tenant_id,
            "scopes": sorted(who.scopes),
            "profile": settings.profile,
        }

    @app.post("/api/v1/api-keys", status_code=201)
    async def key_create(
        body: KeyInput, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, str]:
        who.require("admin")
        if not set(body.scopes) <= who.scopes:
            raise HTTPException(403, "cannot grant unowned scopes")
        token = "ag_" + secrets.token_urlsafe(32)
        async with database.session(who.tenant_id) as session:
            key = ApiKey(
                tenant_id=who.tenant_id,
                digest=hashlib.sha256(token.encode()).hexdigest(),
                scopes=body.scopes,
                expires_at=datetime.now(UTC) + timedelta(hours=body.expires_in_hours),
            )
            session.add(key)
            await session.flush()
            audit(session, who, "api_key.create", key.id)
            return {"id": key.id, "token": token}

    @app.post("/api/v1/api-keys/{key_id}/revoke")
    async def key_revoke(
        key_id: str, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, bool]:
        who.require("admin")
        async with database.session(who.tenant_id) as session:
            key = await scoped(session, ApiKey, key_id, who.tenant_id)
            key.revoked = True
            audit(session, who, "api_key.revoke", key.id)
        return {"revoked": True}

    @app.post("/api/v1/projects", status_code=201)
    async def project_create(
        body: NameInput, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, str]:
        who.require("write")
        async with database.session(who.tenant_id) as session:
            project = Project(tenant_id=who.tenant_id, name=body.name)
            session.add(project)
            await session.flush()
            audit(session, who, "project.create", project.id)
            return {"id": project.id, "name": project.name}

    @app.post("/api/v1/agents", status_code=201)
    async def agent_create(
        body: NameInput, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, str]:
        who.require("write")
        async with database.session(who.tenant_id) as session:
            agent = Agent(tenant_id=who.tenant_id, name=body.name)
            session.add(agent)
            await session.flush()
            audit(session, who, "agent.create", agent.id)
            return {"id": agent.id, "name": agent.name}

    @app.get("/api/v1/agents")
    async def agents(
        who: Annotated[Identity, Depends(identity)], cursor: str = "", limit: int = 50
    ) -> dict[str, Any]:
        who.require("read")
        async with database.session(who.tenant_id) as session:
            rows = list(
                await session.scalars(
                    select(Agent)
                    .where(Agent.tenant_id == who.tenant_id, Agent.id > cursor)
                    .order_by(Agent.id)
                    .limit(max(1, min(limit, 100)))
                )
            )
            return {
                "items": [{"id": a.id, "name": a.name} for a in rows],
                "next_cursor": rows[-1].id if rows else None,
            }

    @app.post("/api/v1/agents/{agent_id}/genomes", status_code=201)
    async def genome_create(
        agent_id: str, body: Manifest, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, Any]:
        who.require("write")
        async with database.session(who.tenant_id) as session:
            await scoped(session, Agent, agent_id, who.tenant_id)
            for parent in body.metadata.parents:
                exists = await session.scalar(
                    select(Genome).where(
                        Genome.tenant_id == who.tenant_id,
                        Genome.digest == parent,
                        Genome.published.is_(True),
                    )
                )
                if exists is None:
                    raise HTTPException(
                        422, "parent must reference a published genome in this tenant"
                    )
            genome = Genome(
                tenant_id=who.tenant_id,
                agent_id=agent_id,
                version=body.metadata.version,
                manifest=body.model_dump(mode="json"),
            )
            session.add(genome)
            await session.flush()
            audit(session, who, "genome.create", genome.id)
            return {"id": genome.id, "published": False}

    @app.get("/api/v1/genomes/{genome_id}")
    @app.get("/api/v1/genomes/{genome_id}/export")
    async def genome_get(
        genome_id: str, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, Any]:
        who.require("read")
        async with database.session(who.tenant_id) as session:
            genome = await scoped(session, Genome, genome_id, who.tenant_id)
            return {
                "id": genome.id,
                "manifest": genome.manifest,
                "digest": genome.digest,
                "published": genome.published,
                "revision": genome.revision,
            }

    @app.post("/api/v1/genomes/{genome_id}/publish")
    async def publish(
        genome_id: str, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, str]:
        who.require("write")
        async with database.session(who.tenant_id) as session:
            genome = await scoped(session, Genome, genome_id, who.tenant_id, lock=True)
            if not genome.published:
                genome.digest = Manifest.model_validate(genome.manifest).digest()
                genome.published = True
                audit(session, who, "genome.publish", genome.id)
            return {"id": genome.id, "digest": str(genome.digest)}

    @app.post("/api/v1/runs", status_code=202)
    async def run_create(
        body: RunInput,
        who: Annotated[Identity, Depends(identity)],
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        if not settings.fake_provider:
            raise HTTPException(422, "fixture provider must be explicitly enabled")
        async with database.session(who.tenant_id) as session:
            genome = await scoped(session, Genome, body.genome_id, who.tenant_id)
            run = await admit(session, who, genome, body.task, idempotency_key)
            return {**run_view(run), "status_url": "/api/v1/runs/" + run.id}

    @app.get("/api/v1/runs")
    async def runs(
        who: Annotated[Identity, Depends(identity)], cursor: str = "", limit: int = 50
    ) -> dict[str, Any]:
        who.require("read")
        async with database.session(who.tenant_id) as session:
            rows = list(
                await session.scalars(
                    select(Run)
                    .where(Run.tenant_id == who.tenant_id, Run.id > cursor)
                    .order_by(Run.id)
                    .limit(max(1, min(limit, 100)))
                )
            )
            return {
                "items": [run_view(r) for r in rows],
                "next_cursor": rows[-1].id if rows else None,
            }

    @app.get("/api/v1/runs/{run_id}")
    async def run_get(run_id: str, who: Annotated[Identity, Depends(identity)]) -> dict[str, Any]:
        who.require("read")
        async with database.session(who.tenant_id) as session:
            return run_view(await scoped(session, Run, run_id, who.tenant_id))

    @app.post("/api/v1/runs/{run_id}/cancel")
    async def cancel(run_id: str, who: Annotated[Identity, Depends(identity)]) -> dict[str, str]:
        who.require("run")
        async with database.session(who.tenant_id) as session:
            run = await scoped(session, Run, run_id, who.tenant_id, lock=True)
            await finish(session, run, "CANCELLED", {"code": "cancelled"})
            audit(session, who, "run.cancel", run.id)
            return {"state": run.state}

    @app.get("/api/v1/approvals")
    async def approvals(who: Annotated[Identity, Depends(identity)]) -> dict[str, Any]:
        who.require("read")
        async with database.session(who.tenant_id) as session:
            rows = list(
                await session.scalars(
                    select(Approval)
                    .where(Approval.tenant_id == who.tenant_id, Approval.status == "PENDING")
                    .limit(100)
                )
            )
            return {
                "items": [
                    {
                        "id": a.id,
                        "run_id": a.run_id,
                        "action_id": a.action_id,
                        "arguments_hash": a.arguments_hash,
                        "expires_at": a.expires_at.isoformat(),
                    }
                    for a in rows
                ]
            }

    @app.post("/api/v1/approvals/{approval_id}/{decision}")
    async def approve(
        approval_id: str, decision: str, who: Annotated[Identity, Depends(identity)]
    ) -> dict[str, str]:
        who.require("approve")
        if decision not in {"approve", "reject"}:
            raise HTTPException(404, "resource not found")
        async with database.session(who.tenant_id) as session:
            approval = await scoped(session, Approval, approval_id, who.tenant_id)
            run = await scoped(session, Run, approval.run_id, who.tenant_id, lock=True)
            await session.refresh(approval, with_for_update=True)
            if run.state in TERMINAL or approval.status != "PENDING":
                raise HTTPException(409, "approval is no longer pending")
            if approval.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(409, "approval expired")
            approval.status = "APPROVED" if decision == "approve" else "REJECTED"
            approval.actor = who.subject
            audit(session, who, "approval." + decision, approval.id)
            return {"status": approval.status}

    @app.get("/api/v1/runs/{run_id}/events")
    async def events(
        run_id: str,
        request: Request,
        who: Annotated[Identity, Depends(identity)],
        last_event_id: Annotated[int, Header(ge=0)] = 0,
    ) -> StreamingResponse:
        who.require("read")
        async with database.session(who.tenant_id) as session:
            await scoped(session, Run, run_id, who.tenant_id)
        bearer = request.headers.get("authorization", "")[7:]

        async def stream() -> AsyncIterator[str]:
            cursor = last_event_id
            while not await request.is_disconnected():
                try:
                    await auth.authenticate(bearer)
                except HTTPException:
                    return
                async with database.session(who.tenant_id) as session:
                    run = await scoped(session, Run, run_id, who.tenant_id)
                    rows = list(
                        await session.scalars(
                            select(RunEvent)
                            .where(
                                RunEvent.tenant_id == who.tenant_id,
                                RunEvent.run_id == run_id,
                                RunEvent.sequence > cursor,
                            )
                            .order_by(RunEvent.sequence)
                            .limit(100)
                        )
                    )
                    for row in rows:
                        cursor = row.sequence
                        payload = {
                            "schema_version": 1,
                            "event_id": row.id,
                            "run_id": run_id,
                            "sequence": row.sequence,
                            "type": row.kind,
                            "payload": row.payload,
                            "genome_hash": run.genome_hash,
                            "occurred_at": row.occurred_at.isoformat(),
                        }
                        yield f"id: {cursor}\nevent: {row.kind}\ndata: {json.dumps(payload)}\n\n"
                    if run.state in TERMINAL and cursor >= run.sequence:
                        return
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.get("/api/v1/audit")
    async def audit_list(who: Annotated[Identity, Depends(identity)]) -> dict[str, Any]:
        who.require("admin")
        async with database.session(who.tenant_id) as session:
            rows = list(
                await session.scalars(
                    select(Audit)
                    .where(Audit.tenant_id == who.tenant_id)
                    .order_by(Audit.occurred_at.desc())
                    .limit(100)
                )
            )
            return {
                "items": [
                    {
                        "actor": r.actor,
                        "operation": r.operation,
                        "resource_id": r.resource_id,
                        "occurred_at": r.occurred_at.isoformat(),
                    }
                    for r in rows
                ]
            }

    return app
