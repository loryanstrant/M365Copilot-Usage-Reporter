"""purge stored aiResponse rows (they are not human usage)

Graph's getAllEnterpriseInteractions returns two rows per exchange: the human
``userPrompt`` and Copilot's ``aiResponse``. Only the human prompt is a genuine
record of usage. Ingest now drops responses, but the idempotent upsert never
deletes, so rows ingested before that change remain and inflate every prompt
count. This one-off data migration removes them using the stored raw payload.

Revision ID: 0003_purge_ai_responses
Revises: 0002_schedule_interval
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_purge_ai_responses"
down_revision: str | None = "0002_schedule_interval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        # JSONB ->> extracts the text value of the key.
        op.execute(
            "DELETE FROM prompts "
            "WHERE raw_json ->> 'interactionType' = 'aiResponse'"
        )
    elif dialect == "sqlite":
        op.execute(
            "DELETE FROM prompts "
            "WHERE json_extract(raw_json, '$.interactionType') = 'aiResponse'"
        )
    # Other dialects: no-op (unsupported in this project).


def downgrade() -> None:
    # Deleted Copilot responses cannot (and should not) be restored.
    pass
