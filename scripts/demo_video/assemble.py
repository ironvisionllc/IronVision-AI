"""Builds the MP4 from the recorded screencast frames: variable-duration concat → constant 30 fps H.264 yuv420p, no audio."""
import json
import subprocess
from pathlib import Path

REC = Path("/tmp/demo_rec")
OUT = Path("/app/backend/app/static/demo/ironvision_ai_rmf_demo.mp4")


def main():
    tl = json.loads((REC / "timeline.json").read_text())
    frames, end = tl["frames"], tl["end"]
    if frames[0][0] > 0.05:
        print("WARNING: first frame at", frames[0][0], "– held from 0")
        frames = [[0.0, frames[0][1]], *frames]
    lines = []
    for i, (t, name) in enumerate(frames):
        nxt = frames[i + 1][0] if i + 1 < len(frames) else end
        dur = max(nxt - t, 0.001)
        lines += [f"file '{REC / 'frames' / name}'", f"duration {dur:.4f}"]
    lines.append(f"file '{REC / 'frames' / frames[-1][1]}'")
    (REC / "concat.txt").write_text("\n".join(lines) + "\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    srt = OUT.parent / "ironvision_ai_rmf_captions.srt"  # burned-in captions (silent video); written by build_docs.py first
    style = "FontName=DejaVu Sans,FontSize=12,PrimaryColour=&H00FFFFFF,BackColour=&H99101820,BorderStyle=4,Outline=0,Shadow=0,MarginV=26"
    subs = f",subtitles={srt}:force_style='{style}'" if srt.exists() else ""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(REC / "concat.txt"),
           "-vf", f"scale=1920:1080:flags=lanczos{subs},fps=30,format=yuv420p", "-an",
           "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
           "-r", "30", "-t", f"{end:.3f}", "-movflags", "+faststart", str(OUT)]
    subprocess.run(cmd, check=True)
    print(json.dumps({"out": str(OUT), "bytes": OUT.stat().st_size, "scenes": tl["scenes"], "end": end}))


if __name__ == "__main__":
    main()
