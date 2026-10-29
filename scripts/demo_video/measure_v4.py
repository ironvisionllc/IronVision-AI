"""Measures the published 3:45 cut for validate_v4.py: scene-score boundaries, same-chrome frame diffs, OCR privacy/closing/key checks, luma."""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenes_v4  # noqa: E402

V = "/app/backend/app/static/demo/ironvision_ai_rmf_demo.mp4"
W = Path("/tmp/v4_measure")
W.mkdir(exist_ok=True)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
HOST = re.compile(r"\b[\w-]+\.(?:preview\.)?emergentagent\.com\b|https?://\S+")
IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
SECRET = re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S+|sk-[A-Za-z0-9]{10,}")


def frame(t, name):
    p = W / f"{name}.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", V, "-frames:v", "1", str(p)], check=True)
    return p


def ocr(p):
    return subprocess.run(["tesseract", str(p), "-", "--psm", "3"], capture_output=True, text=True).stdout


def scores(a, b):
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", V, "-vf",
                          "select='gte(scene,0)',metadata=print:key=lavfi.scene_score:file=-", "-f", "null", "-"], capture_output=True, text=True).stdout
    ts, res = None, []
    for line in out.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            ts = a + float(m.group(1))
        m = re.search(r"scene_score=([\d.]+)", line)
        if m and ts is not None:
            res.append((ts, float(m.group(1))))
    return res


def main():
    targets = [scenes_v4.T[i][0] for i in range(2, 16)]
    bnd = []
    for t in targets:
        best = max(scores(t - 0.5, t + 0.5), key=lambda x: x[1])
        bnd.append((t, round(best[0], 3), round(best[1], 3), round(best[0] - t, 3)))
    content = lambda p: np.asarray(Image.open(p).convert("L"), dtype=np.float32)[170:1000, 330:1900]  # noqa: E731
    fd = []
    for i, t in enumerate(targets, 2):
        a, b, c = content(frame(t - 0.4, f"pre4_{i}")), content(frame(t - 0.1, f"pre1_{i}")), content(frame(t + 0.1, f"post_{i}"))
        fd.append({"boundary": f"{i - 1}→{i}", "t": t, "diff_across": round(float(np.abs(c - b).mean()), 1), "diff_within_prev": round(float(np.abs(b - a).mean()), 1)})
    sheet = [Image.open(W / f"{k}_{i}.png").resize((480, 270)) for i in (4, 9, 11, 12) for k in ("pre1", "post")]
    S = Image.new("RGB", (960, 270 * 4))
    for n, im in enumerate(sheet):
        S.paste(im, ((n % 2) * 480, (n // 2) * 270))
    Path("/app/docs/demo").mkdir(parents=True, exist_ok=True)
    S.save("/app/docs/demo/boundary_frames_3m45.jpg", quality=80)
    pv = {"frames": 0, "email": [], "host": [], "ip": [], "secret": [], "persona": 0}
    for t in range(2, 225, 5):
        txt = ocr(frame(t, f"ocr_{t}"))
        pv["frames"] += 1
        pv["persona"] += txt.count("Demo persona")
        for k, rx in (("email", EMAIL), ("host", HOST), ("ip", IP), ("secret", SECRET)):
            pv[k] += [f"{t}s: {m}" for m in rx.findall(txt)]
    close = ocr(frame(223.0, "closing"))
    norm = lambda x: x.lower().replace("l", "i")  # noqa: E731  (OCR reads the "I" of IronVision/AI as "l")
    pv["closing_lines"] = {k: norm(k) in norm(close) for k in ("IronVision AI", "Enterprise GRC, Made Intelligent.", "Get audit-ready. Stay audit-ready.", "Request Your Demo Today")}
    checks = {"CNSSI 1253 trigraph M-H-L on screen (0:33)": (33.5, "M-H-L"), "Select step shows CNSSI 1253 baseline (0:36)": (36.3, "CNSSI 1253"),
              "Acting as SCA badge (2:06)": (126.5, "SCA"), "Risk acceptance pending (2:41)": (160.5, "pending"),
              "Audit chain verified (2:46)": (166.0, "CHAIN VALID"), "Acting as AO badge (3:13)": (193.5, "AO"),
              "Decision recorded: ATO with conditions + expiry (3:36)": (216.0, "expires")}
    pv["checks"] = {}
    for name, (t, needle) in checks.items():
        f = frame(t, f"chk_{int(t * 10)}")
        big = W / f"chk_{int(t * 10)}_x2.png"  # 2x upscale: small pills/badges read reliably
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(f), "-vf", "scale=3840:-1:flags=lanczos", str(big)], check=True)
        pv["checks"][name] = needle.lower() in (ocr(f) + ocr(big)).lower()
    lum = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", V, "-vf", "fps=1,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
                         capture_output=True, text=True).stdout
    ys = [float(x) for x in re.findall(r"YAVG=([\d.]+)", lum)]
    dark = [i for i, y in enumerate(ys) if y < 120]
    app = [y for i, y in enumerate(ys) if 8 <= i <= 216]
    pv["min_luma"], pv["dark"] = round(min(app), 1), dark or [0, 0]
    Path("/tmp/v4_boundaries.json").write_text(json.dumps(bnd))
    Path("/tmp/v4_framediff.json").write_text(json.dumps(fd))
    Path("/tmp/v4_privacy.json").write_text(json.dumps(pv))
    print(json.dumps({"boundaries": bnd, "max_offset": max(abs(x[3]) for x in bnd), "checks": pv["checks"], "closing": pv["closing_lines"],
                      "privacy": {k: pv[k] for k in ("frames", "email", "host", "ip", "secret", "persona")}, "min_luma": pv["min_luma"], "dark": pv["dark"]}, indent=1))


if __name__ == "__main__":
    main()
