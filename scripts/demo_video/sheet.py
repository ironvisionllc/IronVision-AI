"""Contact sheet of recorded frames at given virtual times: python3 sheet.py out.png t1 t2 ... (uses /tmp/demo_rec or the MP4 with --mp4)."""
import json
import subprocess
import sys
from bisect import bisect_right
from pathlib import Path

from PIL import Image, ImageDraw

REC = Path("/tmp/demo_rec")
out, ts = sys.argv[1], [a for a in sys.argv[2:] if a != "--mp4"]
W, H = 640, 360
ims = []
for t in map(float, ts):
    if "--mp4" in sys.argv:
        p = f"/tmp/mp4_{t:.1f}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", "/app/backend/app/static/demo/ironvision_ai_rmf_demo.mp4",
                        "-frames:v", "1", p], check=True)
        im = Image.open(p)
    else:
        fr = json.loads((REC / "timeline.json").read_text())["frames"]
        i = max(0, bisect_right([f[0] for f in fr], t) - 1)
        im = Image.open(REC / "frames" / fr[i][1])
    im = im.convert("RGB").resize((W, H))
    ImageDraw.Draw(im).rectangle([0, 0, 70, 22], fill="black")
    ImageDraw.Draw(im).text((4, 4), f"{t:.1f}s", fill="white")
    ims.append(im)
cols = 3
sheet = Image.new("RGB", (W * cols, H * ((len(ims) + cols - 1) // cols)), "white")
for i, im in enumerate(ims):
    sheet.paste(im, ((i % cols) * W, (i // cols) * H))
sheet.save(out)
