"""3:45 cut (v4): replaces the closing 7 s with the v3 high-contrast card (fade-in) and overlays the scene-label pill at each app scene start.
Source: /tmp/v4_raw.mp4 (assemble.py output). Same encode settings as v3. Publishes ironvision_ai_rmf_demo.mp4 (silent)."""
import asyncio
import json
import subprocess
from pathlib import Path

import finish_mkt as f3

SRC = Path("/tmp/v4_raw.mp4")
OUT = f3.DEMO / "ironvision_ai_rmf_demo.mp4"
CLOSE_AT, END = 218.0, 225.0
f3.LABELS[:] = [(7, "RMF dashboard"), (25, "CNSSI 1253 categorization"), (37, "Import Center – eMASS round-trip"), (62, "Import management"),
                (68, "Control Workbench"), (84, "AI Policy Auditor"), (116, "Mapping Review"), (125, "SCA workspace"), (142, "POA&M"),
                (162, "Tamper-evident audit log"), (172, "Continuous monitoring"), (185, "Authorization package"), (192, "AO decision")]
f3.WORK = Path("/tmp/v4_finish")


def encode():
    L, S, FD = f3.LABELS, f3.LABEL_S, f3.LABEL_FADE
    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(SRC), "-loop", "1", "-t", str(END - CLOSE_AT), "-framerate", "30", "-i", str(f3.WORK / "closing.png")]
    for i in range(len(L)):
        args += ["-loop", "1", "-t", str(S), "-framerate", "30", "-i", str(f3.WORK / f"label{i}.png")]
    fc = [f"[0:v]trim=0:{CLOSE_AT},setpts=PTS-STARTPTS[b0]"]
    for i, (t, _) in enumerate(L):
        fc.append(f"[{i + 2}:v]format=rgba,fade=in:st=0:d={FD}:alpha=1,fade=out:st={S - FD}:d={FD}:alpha=1,setpts=PTS-STARTPTS+{t}/TB[l{i}]")
        fc.append(f"[b{i}][l{i}]overlay=0:0:eof_action=pass:enable='between(t,{t},{t + S})'[b{i + 1}]")
    fc.append(f"[1:v]format=yuv420p,fade=in:st=0:d={f3.FADE},setpts=PTS-STARTPTS[c]")
    fc.append(f"[b{len(L)}][c]concat=n=2:v=1:a=0,fps=30,format=yuv420p[v]")
    tmp = OUT.with_suffix(".v4.mp4")
    subprocess.run(args + ["-filter_complex", ";".join(fc), "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high",
                           "-level", "4.1", "-pix_fmt", "yuv420p", "-r", "30", "-t", str(END), "-movflags", "+faststart", "-map_metadata", "-1", str(tmp)], check=True)
    tmp.replace(OUT)
    print(json.dumps({"out": str(OUT), "bytes": OUT.stat().st_size}))


if __name__ == "__main__":
    asyncio.run(f3.render())
    encode()
