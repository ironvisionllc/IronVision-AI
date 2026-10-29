"""Removes the light/dark switch and the phone-width segment from the full caption-free recording without re-recording.
Keeps [0, CUT_A) (through monitoring/traceability) and [CUT_B, end] (closing card), joined with a 0.5 s crossfade. Same encode settings as assemble.py."""
import json
import subprocess
from pathlib import Path

OUT = Path("/app/backend/app/static/demo/ironvision_ai_rmf_demo.mp4")
SRC = OUT.parent / "archive" / "2026-10-29-with-phone" / OUT.name  # full 300 s caption-free cut (archived, unlinked)
CUT_A, CUT_B, XF = 244.0, 284.2, 0.5  # last traceability frame (7319) / first closing-card frame (8526) / crossfade


def main():
    src = SRC
    tmp = OUT.with_suffix(".cut.mp4")
    fc = (f"[0:v]trim=0:{CUT_A},setpts=PTS-STARTPTS[a];[0:v]trim=start={CUT_B},setpts=PTS-STARTPTS[b];"
          f"[a][b]xfade=transition=fade:duration={XF}:offset={CUT_A - XF},fps=30,format=yuv420p[v]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-filter_complex", fc, "-map", "[v]", "-an",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                    "-r", "30", "-movflags", "+faststart", "-map_metadata", "-1", str(tmp)], check=True)
    tmp.replace(OUT)
    print(json.dumps({"out": str(OUT), "bytes": OUT.stat().st_size, "archived": str(src)}))


if __name__ == "__main__":
    main()
