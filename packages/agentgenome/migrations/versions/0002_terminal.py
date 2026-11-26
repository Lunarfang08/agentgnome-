"""Protect terminal runs against later modification at the database boundary."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_terminal_run() RETURNS trigger LANGUAGE
plpgsql AS $$
        BEGIN IF OLD.state IN
('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT','BUDGET_EXHAUSTED')
        THEN RAISE EXCEPTION 'terminal run is immutable'; END IF;
RETURN NEW; END $$""")
        op.execute(
            """CREATE TRIGGER terminal_immutable BEFORE UPDATE OR DELETE ON runs FOR
EACH ROW EXECUTE
FUNCTION protect_terminal_run()"""
        )
    else:
        op.execute(
            """CREATE TRIGGER terminal_immutable BEFORE UPDATE ON runs WHEN OLD.state
IN
('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT','BUDGET_EXHAUSTED')
BEGIN SELECT
RAISE(ABORT, 'terminal run is immutable'); END"""
        )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS terminal_immutable"
        + (" ON runs" if op.get_bind().dialect.name == "postgresql" else "")
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION protect_terminal_run()")
