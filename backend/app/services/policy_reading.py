"""Reading report for the policy page: extraction stats (computed once from the stored original and kept on the policy) plus the coverage
guard and second-look/prompt-cache counters of the last AI analysis."""
from sqlalchemy.orm import Session

from app.models import Policy


def reading_for(db: Session, p: Policy) -> dict | None:
    an = p.analysis or {}
    rep = an.get("reading")
    if rep is None and p.storage_key and p.text_content:
        try:
            from app.services import rmf
            from app.services.storage import get_storage
            rep = rmf.reading_report(p.file_name or "", get_storage().get(p.storage_key), p.text_content)
            p.analysis = {**an, "reading": rep}
            db.commit()
        except Exception:  # noqa: BLE001 – original unavailable: report what we know
            rep = {"chars_read": len(p.text_content or ""), "warnings": ["Original file unavailable – extraction details unknown."]}
    if rep is None:
        return None
    v2 = an.get("v2") or {}
    keys = ("whole_document", "chunks_total", "chunks_covered", "uncovered_sections", "index_chunks", "index_reused", "tokens_in", "tokens_out",
            "tokens_cached", "prompt_cache_hits", "calls", "second_look_candidates", "second_look_ai", "second_look_found", "second_look_confirmed_absent")
    return {**rep, "sections": v2.get("sections"), **{k: v2.get(k) for k in keys if k in v2}}
