"""Keyword-only policy coverage rows never say "missing": additive history column + one-time relabel of stored rows
(deterministic, non-AI, non xx-1 "missing" → "partial"/Low "AI unavailable – keyword check only, needs manual review"); the original
status/confidence/reason/needs are kept in history. Downgrade restores them from history and drops the column.

Revision ID: 0037
Revises: 0036
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

KEYWORD_ONLY = "AI unavailable for this control – keyword check only, needs manual review."
WHERE = "status = 'missing' AND concept <> 'profile-ai' AND control_id !~ '^[a-z]{2}-1$'"


def upgrade() -> None:
    op.add_column("policy_requirement_coverage", sa.Column("history", JSONB))
    op.execute(sa.text(f"""
        UPDATE policy_requirement_coverage SET
          history = COALESCE(history, '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
              'status', status, 'confidence', confidence, 'reason', reason, 'needs', needs,
              'at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'why', 'keyword-only result relabelled (0037)')),
          status = 'partial', confidence = 'Low',
          reason = left(:k || ' ' || replace(reason, 'No sentence addresses this requirement.', 'No keyword match was found.'), 2000),
          needs = replace(replace(needs, 'The policy does not clearly address this requirement.',
                                  'Manual review needed: the quoted policy text may address this requirement, but this is not confirmed.'),
                          'Fix: Add policy language', 'Fix: confirm that the quoted policy text meets it; if it does not, add policy language')
        WHERE {WHERE}""").bindparams(k=KEYWORD_ONLY))


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE policy_requirement_coverage SET status = history->-1->>'status', confidence = history->-1->>'confidence',
          reason = history->-1->>'reason', needs = history->-1->>'needs'
        WHERE history IS NOT NULL AND history->-1->>'why' = 'keyword-only result relabelled (0037)'"""))
    op.drop_column("policy_requirement_coverage", "history")
