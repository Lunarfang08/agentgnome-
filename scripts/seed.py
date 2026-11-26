import asyncio

from agentgenome.auth import DEV_TENANT
from agentgenome.config import Settings
from agentgenome.db import Database, Membership, Tenant
from sqlalchemy import select


async def seed():
    settings = Settings()
    if settings.profile != "dev":
        raise RuntimeError("Demo seed is permitted only in dev")
    db = Database(settings.database_url)
    async with db.sessions() as session, session.begin():
        if not await session.get(Tenant, DEV_TENANT):
            session.add(Tenant(id=DEV_TENANT, name="Development tenant"))
            await session.flush()
        if not await session.scalar(select(Membership).where(Membership.subject == "dev-admin")):
            session.add(Membership(tenant_id=DEV_TENANT, subject="dev-admin", role="admin"))
    await db.engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
