"""xx-1 (policy/procedure) controls: stored checklist-only "missing" rows → "partial"/Low "AI unavailable – policy-element checklist only,
needs manual review"; originals kept in history (column from 0037). Downgrade restores them.

Revision ID: 0038
Revises: 0037
"""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

LEAD = "AI unavailable for this control – policy-element checklist only, needs manual review."
WHY = "xx-1 checklist-only result relabelled (0038)"


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE policy_requirement_coverage SET
          history = COALESCE(history, '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
              'status', status, 'confidence', confidence, 'reason', reason, 'needs', needs,
              'at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'why', :why)),
          status = 'partial', confidence = 'Low', reason = left(:k || ' ' || COALESCE(reason, ''), 2000),
          needs = CASE WHEN needs IS NULL THEN NULL ELSE left('Manual review needed (checklist only): ' || needs, 2000) END
        WHERE status = 'missing' AND concept <> 'profile-ai' AND control_id ~ '^[a-z]{2}-1$'""").bindparams(k=LEAD, why=WHY))


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE policy_requirement_coverage SET status = history->-1->>'status', confidence = history->-1->>'confidence',
          reason = history->-1->>'reason', needs = history->-1->>'needs', history = history - (jsonb_array_length(history) - 1)
        WHERE history IS NOT NULL AND history->-1->>'why' = :why""").bindparams(why=WHY))
