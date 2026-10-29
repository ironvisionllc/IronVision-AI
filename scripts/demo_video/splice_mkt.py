"""Splices the pick-up recording (scenes_mkt_fix.py → /tmp/fix.mp4) into the 3:10 cut at exact scene boundaries; hard cuts as before.
Final = v1[0,85) + fix[0,45) (Policy Auditor + Mapping Review) + v1[130,150) + fix[45,65) (Authorization) + v1[170,190]."""
import json
import subprocess
from pathlib import Path

OUT = Path("/app/backend/app/static/demo/ironvision_ai_rmf_demo.mp4")
V1 = OUT.parent / "archive" / "2026-10-29-3m10-v1" / OUT.name
FIX = Path("/tmp/fix.mp4")
PARTS = [(0, 0, 85), (1, 0, 45), (0, 130, 150), (1, 45, 65), (0, 170, 190)]  # (input, start, end)


def main():
    fc = "".join(f"[{i}:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[p{n}];" for n, (i, a, b) in enumerate(PARTS))
    fc += "".join(f"[p{n}]" for n in range(len(PARTS))) + f"concat=n={len(PARTS)}:v=1:a=0,fps=30,format=yuv420p[v]"
    tmp = OUT.with_suffix(".splice.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(V1), "-i", str(FIX), "-filter_complex", fc, "-map", "[v]", "-an",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                    "-r", "30", "-movflags", "+faststart", "-map_metadata", "-1", str(tmp)], check=True)
    tmp.replace(OUT)
    print(json.dumps({"out": str(OUT), "bytes": OUT.stat().st_size}))


if __name__ == "__main__":
    main()
