from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/public", tags=["public"])
DIR = Path(__file__).resolve().parents[2] / "static" / "whitepaper"
FILES = {"pdf": ("application/pdf", "IronVision_AI_Whitepaper.pdf"),
         "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "IronVision_AI_Whitepaper.docx")}


@router.get("/whitepaper.{ext}")
def whitepaper(ext: str) -> FileResponse:
    """Public (no auth) download of the product whitepaper."""
    if ext not in FILES:
        raise HTTPException(404, "Available formats: pdf, docx")
    media, name = FILES[ext]
    return FileResponse(DIR / name, media_type=media, filename=name, headers={"Cache-Control": "public, max-age=3600"})
