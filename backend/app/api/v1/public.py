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


DEMO_DIR = DIR.parent / "demo"
DEMO = {"ironvision_ai_rmf_demo.mp4": ("video/mp4", "inline"),
        "ironvision_ai_rmf_narration.txt": ("text/plain; charset=utf-8", "inline"),
        "ironvision_ai_rmf_teleprompter.md": ("text/markdown; charset=utf-8", "inline"),
        "ironvision_ai_rmf_captions.srt": ("application/x-subrip", "attachment"),
        "ironvision_ai_rmf_scene_timeline.md": ("text/markdown; charset=utf-8", "inline"),
        "ironvision_ai_rmf_demo_validation.md": ("text/markdown; charset=utf-8", "inline")}


@router.api_route("/demo/{name}", methods=["GET", "HEAD"])
def demo_file(name: str) -> FileResponse:
    """Public (no auth) product demo video and its narration/caption/timeline/validation files. Range requests supported (MP4 seeking)."""
    if name not in DEMO:
        raise HTTPException(404, "Unknown demo file")
    media, disp = DEMO[name]
    return FileResponse(DEMO_DIR / name, media_type=media, filename=name, content_disposition_type=disp,
                        headers={"Cache-Control": "public, max-age=3600", "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'"})
