from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/public", tags=["public"])
DIR = Path(__file__).resolve().parents[2] / "static" / "whitepaper"
FILES = {"pdf": ("application/pdf", "IronVision_AI_Whitepaper.pdf"),
         "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "IronVision_AI_Whitepaper.docx")}


@router.api_route("/whitepaper.{ext}", methods=["GET", "HEAD"])
def whitepaper(ext: str) -> FileResponse:
    """Public (no auth) download of the product whitepaper. PDF inline (opens in iOS Safari's viewer), DOCX as attachment."""
    if ext not in FILES:
        raise HTTPException(404, "Available formats: pdf, docx")
    media, name = FILES[ext]
    return FileResponse(DIR / name, media_type=media, filename=name, content_disposition_type="inline" if ext == "pdf" else "attachment",
                        headers={"Cache-Control": "public, max-age=3600", "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'"})
