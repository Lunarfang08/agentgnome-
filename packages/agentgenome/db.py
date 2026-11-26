import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    budget: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("100"))
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    spent: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("subject", "tenant_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    subject: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(30))


class Scoped:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)


class Project(Scoped, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(100))


class Agent(Scoped, Base):
    __tablename__ = "agents"
    name: Mapped[str] = mapped_column(String(100))
    paused: Mapped[bool] = mapped_column(default=False)


class Genome(Scoped, Base):
    __tablename__ = "genomes"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    version: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    digest: Mapped[str | None] = mapped_column(String(71))
    published: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=1)


class Policy(Scoped, Base):
    __tablename__ = "policies"
    version: Mapped[int] = mapped_column(default=1)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class ApiKey(Scoped, Base):
    __tablename__ = "api_keys"
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)


class Run(Scoped, Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    genome_id: Mapped[str] = mapped_column(ForeignKey("genomes.id"))
    genome_hash: Mapped[str] = mapped_column(String(71))
    task: Mapped[str] = mapped_column(String(10000))
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32), default="QUEUED")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    reserved_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RunEvent(Scoped, Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Scoped, Base):
    __tablename__ = "audit_events"
    actor: Mapped[str] = mapped_column(String(255))
    operation: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Outbox(Scoped, Base):
    __tablename__ = "outbox_events"
    kind: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    delivered: Mapped[bool] = mapped_column(default=False)
    attempts: Mapped[int] = mapped_column(default=0)


class ToolAction(Scoped, Base):
    __tablename__ = "tool_actions"
    __table_args__ = (UniqueConstraint("run_id", "step"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    step: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(80))
    arguments_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32))
    receipt: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Approval(Scoped, Base):
    __tablename__ = "approvals"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    action_id: Mapped[str] = mapped_column(ForeignKey("tool_actions.id"), unique=True)
    arguments_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimOrder(Scoped, Base):
    __tablename__ = "sim_orders"
    __table_args__ = (UniqueConstraint("run_id"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    action_id: Mapped[str] = mapped_column(String(36), unique=True)
    item: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)


class Database:
    def __init__(self, url: str):
        self.engine = create_async_engine(url, pool_pre_ping=True, hide_parameters=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def foreign_keys(connection: Any, _: Any) -> None:
                connection.execute("PRAGMA foreign_keys=ON")

    @asynccontextmanager
    async def session(self, tenant_id: str | None = None) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session, session.begin():
            if tenant_id is not None and self.engine.dialect.name == "postgresql":
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
                )
            yield session
