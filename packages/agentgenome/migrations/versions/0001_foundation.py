"""Initial identity, registry, runtime, audit and outbox schema.

Frozen DDL snapshot; do not import live ORM models in migrations."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DDL = {
    "postgresql": [
        """CREATE TABLE tenants (
        id VARCHAR(36) NOT NULL,
        name VARCHAR(100) NOT NULL,
        budget NUMERIC(18, 6) NOT NULL,
        reserved NUMERIC(18, 6) NOT NULL,
        spent NUMERIC(18, 6) NOT NULL,
        PRIMARY KEY (id)
)""",
        """CREATE TABLE agents (
        name VARCHAR(100) NOT NULL,
        paused BOOLEAN NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE api_keys (
        digest VARCHAR(64) NOT NULL,
        scopes JSON NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked BOOLEAN NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (digest),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE audit_events (
        actor VARCHAR(255) NOT NULL,
        operation VARCHAR(100) NOT NULL,
        resource_id VARCHAR(100) NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE memberships (
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        subject VARCHAR(255) NOT NULL,
        role VARCHAR(30) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (subject, tenant_id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE outbox_events (
        kind VARCHAR(80) NOT NULL,
        resource_id VARCHAR(36) NOT NULL,
        delivered BOOLEAN NOT NULL,
        attempts INTEGER NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE policies (
        version INTEGER NOT NULL,
        body JSON NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE projects (
        name VARCHAR(100) NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE genomes (
        agent_id VARCHAR(36) NOT NULL,
        version VARCHAR(64) NOT NULL,
        manifest JSON NOT NULL,
        digest VARCHAR(71),
        published BOOLEAN NOT NULL,
        revision INTEGER NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (agent_id, version),
        FOREIGN KEY(agent_id) REFERENCES agents (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE runs (
        genome_id VARCHAR(36) NOT NULL,
        genome_hash VARCHAR(71) NOT NULL,
        task VARCHAR(10000) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        state VARCHAR(32) NOT NULL,
        sequence INTEGER NOT NULL,
        reserved_cost NUMERIC(18, 6) NOT NULL,
        actual_cost NUMERIC(18, 6) NOT NULL,
        checkpoint JSON NOT NULL,
        result JSON,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (tenant_id, idempotency_key),
        FOREIGN KEY(genome_id) REFERENCES genomes (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE run_events (
        run_id VARCHAR(36) NOT NULL,
        sequence INTEGER NOT NULL,
        kind VARCHAR(80) NOT NULL,
        payload JSON NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (run_id, sequence),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE sim_orders (
        run_id VARCHAR(36) NOT NULL,
        action_id VARCHAR(36) NOT NULL,
        item VARCHAR(100) NOT NULL,
        quantity INTEGER NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (run_id),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        UNIQUE (action_id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE tool_actions (
        run_id VARCHAR(36) NOT NULL,
        step INTEGER NOT NULL,
        tool VARCHAR(80) NOT NULL,
        arguments_hash VARCHAR(64) NOT NULL,
        state VARCHAR(32) NOT NULL,
        receipt JSON,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (run_id, step),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE approvals (
        run_id VARCHAR(36) NOT NULL,
        action_id VARCHAR(36) NOT NULL,
        arguments_hash VARCHAR(64) NOT NULL,
        status VARCHAR(20) NOT NULL,
        actor VARCHAR(255),
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        UNIQUE (action_id),
        FOREIGN KEY(action_id) REFERENCES tool_actions (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        "CREATE INDEX ix_agents_tenant_id ON agents (tenant_id)",
        "CREATE INDEX ix_api_keys_tenant_id ON api_keys (tenant_id)",
        "CREATE INDEX ix_audit_events_tenant_id ON audit_events (tenant_id)",
        "CREATE INDEX ix_memberships_tenant_id ON memberships (tenant_id)",
        "CREATE INDEX ix_memberships_subject ON memberships (subject)",
        "CREATE INDEX ix_outbox_events_tenant_id ON outbox_events (tenant_id)",
        "CREATE INDEX ix_policies_tenant_id ON policies (tenant_id)",
        "CREATE INDEX ix_projects_tenant_id ON projects (tenant_id)",
        "CREATE INDEX ix_genomes_agent_id ON genomes (agent_id)",
        "CREATE INDEX ix_genomes_tenant_id ON genomes (tenant_id)",
        "CREATE INDEX ix_runs_tenant_id ON runs (tenant_id)",
        "CREATE INDEX ix_run_events_run_id ON run_events (run_id)",
        "CREATE INDEX ix_run_events_tenant_id ON run_events (tenant_id)",
        "CREATE INDEX ix_sim_orders_tenant_id ON sim_orders (tenant_id)",
        "CREATE INDEX ix_tool_actions_tenant_id ON tool_actions (tenant_id)",
        "CREATE INDEX ix_approvals_tenant_id ON approvals (tenant_id)",
    ],
    "sqlite": [
        """CREATE TABLE tenants (
        id VARCHAR(36) NOT NULL,
        name VARCHAR(100) NOT NULL,
        budget NUMERIC(18, 6) NOT NULL,
        reserved NUMERIC(18, 6) NOT NULL,
        spent NUMERIC(18, 6) NOT NULL,
        PRIMARY KEY (id)
)""",
        """CREATE TABLE agents (
        name VARCHAR(100) NOT NULL,
        paused BOOLEAN NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE api_keys (
        digest VARCHAR(64) NOT NULL,
        scopes JSON NOT NULL,
        expires_at DATETIME NOT NULL,
        revoked BOOLEAN NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (digest),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE audit_events (
        actor VARCHAR(255) NOT NULL,
        operation VARCHAR(100) NOT NULL,
        resource_id VARCHAR(100) NOT NULL,
        occurred_at DATETIME NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE memberships (
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        subject VARCHAR(255) NOT NULL,
        role VARCHAR(30) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (subject, tenant_id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE outbox_events (
        kind VARCHAR(80) NOT NULL,
        resource_id VARCHAR(36) NOT NULL,
        delivered BOOLEAN NOT NULL,
        attempts INTEGER NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE policies (
        version INTEGER NOT NULL,
        body JSON NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE projects (
        name VARCHAR(100) NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE genomes (
        agent_id VARCHAR(36) NOT NULL,
        version VARCHAR(64) NOT NULL,
        manifest JSON NOT NULL,
        digest VARCHAR(71),
        published BOOLEAN NOT NULL,
        revision INTEGER NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (agent_id, version),
        FOREIGN KEY(agent_id) REFERENCES agents (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE runs (
        genome_id VARCHAR(36) NOT NULL,
        genome_hash VARCHAR(71) NOT NULL,
        task VARCHAR(10000) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        state VARCHAR(32) NOT NULL,
        sequence INTEGER NOT NULL,
        reserved_cost NUMERIC(18, 6) NOT NULL,
        actual_cost NUMERIC(18, 6) NOT NULL,
        checkpoint JSON NOT NULL,
        result JSON,
        created_at DATETIME NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (tenant_id, idempotency_key),
        FOREIGN KEY(genome_id) REFERENCES genomes (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE run_events (
        run_id VARCHAR(36) NOT NULL,
        sequence INTEGER NOT NULL,
        kind VARCHAR(80) NOT NULL,
        payload JSON NOT NULL,
        occurred_at DATETIME NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (run_id, sequence),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE sim_orders (
        run_id VARCHAR(36) NOT NULL,
        action_id VARCHAR(36) NOT NULL,
        item VARCHAR(100) NOT NULL,
        quantity INTEGER NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (run_id),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        UNIQUE (action_id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE tool_actions (
        run_id VARCHAR(36) NOT NULL,
        step INTEGER NOT NULL,
        tool VARCHAR(80) NOT NULL,
        arguments_hash VARCHAR(64) NOT NULL,
        state VARCHAR(32) NOT NULL,
        receipt JSON,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (run_id, step),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        """CREATE TABLE approvals (
        run_id VARCHAR(36) NOT NULL,
        action_id VARCHAR(36) NOT NULL,
        arguments_hash VARCHAR(64) NOT NULL,
        status VARCHAR(20) NOT NULL,
        actor VARCHAR(255),
        expires_at DATETIME NOT NULL,
        id VARCHAR(36) NOT NULL,
        tenant_id VARCHAR(36) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(run_id) REFERENCES runs (id),
        UNIQUE (action_id),
        FOREIGN KEY(action_id) REFERENCES tool_actions (id),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)""",
        "CREATE INDEX ix_agents_tenant_id ON agents (tenant_id)",
        "CREATE INDEX ix_api_keys_tenant_id ON api_keys (tenant_id)",
        "CREATE INDEX ix_audit_events_tenant_id ON audit_events (tenant_id)",
        "CREATE INDEX ix_memberships_tenant_id ON memberships (tenant_id)",
        "CREATE INDEX ix_memberships_subject ON memberships (subject)",
        "CREATE INDEX ix_outbox_events_tenant_id ON outbox_events (tenant_id)",
        "CREATE INDEX ix_policies_tenant_id ON policies (tenant_id)",
        "CREATE INDEX ix_projects_tenant_id ON projects (tenant_id)",
        "CREATE INDEX ix_genomes_agent_id ON genomes (agent_id)",
        "CREATE INDEX ix_genomes_tenant_id ON genomes (tenant_id)",
        "CREATE INDEX ix_runs_tenant_id ON runs (tenant_id)",
        "CREATE INDEX ix_run_events_run_id ON run_events (run_id)",
        "CREATE INDEX ix_run_events_tenant_id ON run_events (tenant_id)",
        "CREATE INDEX ix_sim_orders_tenant_id ON sim_orders (tenant_id)",
        "CREATE INDEX ix_tool_actions_tenant_id ON tool_actions (tenant_id)",
        "CREATE INDEX ix_approvals_tenant_id ON approvals (tenant_id)",
    ],
}


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    for statement in DDL[dialect]:
        op.execute(statement)
    if dialect == "postgresql":
        op.execute("ALTER TABLE agents ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE agents FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON agents USING (tenant_id =
current_setting('app.tenant_id',
true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON audit_events USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON outbox_events USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE policies ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE policies FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON policies USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE projects ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE projects FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON projects USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE genomes ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE genomes FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON genomes USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE runs ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE runs FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON runs USING (tenant_id =
current_setting('app.tenant_id',
true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE run_events ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE run_events FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON run_events USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE sim_orders ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE sim_orders FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON sim_orders USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE tool_actions ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE tool_actions FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON tool_actions USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("ALTER TABLE approvals ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE approvals FORCE ROW LEVEL SECURITY")
        op.execute(
            """CREATE POLICY tenant_scope ON approvals USING (tenant_id =
current_setting('app.tenant_id', true)) WITH CHECK (tenant_id =
current_setting('app.tenant_id', true))"""
        )
        op.execute("""CREATE FUNCTION reject_immutable() RETURNS trigger LANGUAGE plpgsql AS
$$
        BEGIN RAISE EXCEPTION 'immutable record'; END $$""")
        op.execute("""CREATE FUNCTION protect_genome() RETURNS trigger LANGUAGE plpgsql AS
$$
        BEGIN IF OLD.published THEN RAISE EXCEPTION 'published genome
is immutable'; END
IF;
        RETURN NEW; END $$""")
        op.execute(
            """CREATE TRIGGER genome_immutable BEFORE UPDATE OR DELETE ON genomes FOR
EACH ROW EXECUTE
FUNCTION protect_genome()"""
        )
        for table in ("audit_events", "run_events"):
            op.execute(
                f"CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION reject_immutable()"
            )
    elif dialect == "sqlite":
        op.execute(
            """CREATE TRIGGER genome_immutable_update BEFORE UPDATE ON genomes WHEN
OLD.published = 1
BEGIN SELECT RAISE(ABORT, 'immutable genome'); END"""
        )
        op.execute(
            """CREATE TRIGGER genome_immutable_delete BEFORE DELETE ON genomes WHEN
OLD.published = 1
BEGIN SELECT RAISE(ABORT, 'immutable genome'); END"""
        )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive initial downgrade is disabled; restore a verified backup instead"
    )
