"""3:10 cut v3: re-renders the closing card (high-contrast CTA) and adds a small on-screen scene label at the start of each app scene
so same-chrome transitions are visible. Source: archive/2026-10-29-3m10-v2 (unlinked). No boundary moves; same encode settings."""
import asyncio
import json
import subprocess
from pathlib import Path

from playwright.async_api import async_playwright

DEMO = Path("/app/backend/app/static/demo")
SRC = DEMO / "archive" / "2026-10-29-3m10-v2" / "ironvision_ai_rmf_demo.mp4"
OUT = DEMO / "ironvision_ai_rmf_demo.mp4"
CARDS = Path(__file__).resolve().parent / "cards"
WORK = Path("/tmp/mkt_v3")
CLOSE_AT, END, FADE = 185.0, 190.0, 0.8
LABEL_S, LABEL_FADE = 2.2, 0.25
LABELS = [(8, "RMF dashboard"), (30, "Import Center"), (57, "Import management"), (65, "Control Workbench"), (85, "AI Policy Auditor"),
          (120, "Mapping Review"), (130, "SCA workspace"), (150, "Authorization & exports"), (170, "Continuous monitoring")]
LABEL_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Jakarta;src:url('%s/frontend/public/fonts/PlusJakartaSans-700.woff2');font-weight:700}
html,body{margin:0;background:transparent}
.l{position:absolute;left:350px;top:986px;display:flex;align-items:center;gap:14px;padding:12px 26px 12px 18px;border-radius:999px;
background:#0A3540;color:#fff;font-family:Jakarta,Arial,sans-serif;font-weight:700;font-size:28px;box-shadow:0 8px 24px rgba(0,0,0,.28)}
.d{width:12px;height:12px;border-radius:50%%;background:#5FD0E6}
</style></head><body><div class="l"><span class="d"></span>%s</div></body></html>"""


async def render():
    WORK.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await (await b.new_context(viewport={"width": 1920, "height": 1080})).new_page()
        await pg.goto((CARDS / "closing_mkt.html").as_uri())
        await pg.evaluate("document.body.style.opacity = '1'")
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=str(WORK / "closing.png"))
        for i, (_, name) in enumerate(LABELS):
            (WORK / f"label{i}.html").write_text(LABEL_HTML % ("/app", name))
            await pg.goto((WORK / f"label{i}.html").as_uri())
            await pg.wait_for_timeout(300)
            await pg.screenshot(path=str(WORK / f"label{i}.png"), omit_background=True)
        await b.close()


def encode():
    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(SRC), "-loop", "1", "-t", str(END - CLOSE_AT), "-framerate", "30", "-i", str(WORK / "closing.png")]
    for i in range(len(LABELS)):
        args += ["-loop", "1", "-t", str(LABEL_S), "-framerate", "30", "-i", str(WORK / f"label{i}.png")]
    fc = [f"[0:v]trim=0:{CLOSE_AT},setpts=PTS-STARTPTS[b0]"]
    for i, (t, _) in enumerate(LABELS):
        fc.append(f"[{i + 2}:v]format=rgba,fade=in:st=0:d={LABEL_FADE}:alpha=1,fade=out:st={LABEL_S - LABEL_FADE}:d={LABEL_FADE}:alpha=1,setpts=PTS-STARTPTS+{t}/TB[l{i}]")
        fc.append(f"[b{i}][l{i}]overlay=0:0:eof_action=pass:enable='between(t,{t},{t + LABEL_S})'[b{i + 1}]")
    fc.append(f"[1:v]format=yuv420p,fade=in:st=0:d={FADE},setpts=PTS-STARTPTS[c]")
    fc.append(f"[b{len(LABELS)}][c]concat=n=2:v=1:a=0,fps=30,format=yuv420p[v]")
    tmp = OUT.with_suffix(".v3.mp4")
    subprocess.run(args + ["-filter_complex", ";".join(fc), "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high",
                           "-level", "4.1", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", "-map_metadata", "-1", str(tmp)], check=True)
    tmp.replace(OUT)
    print(json.dumps({"out": str(OUT), "bytes": OUT.stat().st_size}))


if __name__ == "__main__":
    asyncio.run(render())
    encode()
