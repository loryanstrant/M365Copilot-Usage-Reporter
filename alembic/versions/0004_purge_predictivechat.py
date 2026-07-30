"""purge system-generated PredictiveChat rows (not human usage)

PredictiveChat is a system-generated chat type, not a real Copilot surface, so
it must not be counted as usage. Ingest now drops it, but the idempotent upsert
never deletes, so any rows ingested before this change remain and inflate app
counts. This one-off data migration removes them using the stored raw payload
(matching the prefix-stripped appClass, case-insensitively).

Revision ID: 0004_purge_predictivechat
Revises: 0003_purge_ai_responses
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_purge_predictivechat"
down_revision: str | None = "0003_purge_ai_responses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        # appClass may or may not carry the IPM.SkypeTeams.Message.Copilot. prefix.
        op.execute(
            "DELETE FROM prompts "
            "WHERE lower(raw_json ->> 'appClass') LIKE '%predictivechat' "
            "   OR lower(app_name) = 'predictivechat'"
        )
    elif dialect == "sqlite":
        op.execute(
            "DELETE FROM prompts "
            "WHERE lower(json_extract(raw_json, '$.appClass')) LIKE '%predictivechat' "
            "   OR lower(app_name) = 'predictivechat'"
        )
    # Other dialects: no-op (unsupported in this project).


def downgrade() -> None:
    # Deleted system-generated rows cannot (and should not) be restored.
    pass
