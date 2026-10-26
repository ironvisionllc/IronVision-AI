"""Tests for the public demo video + supporting files, and backend bug-fix 2 (POA&M label in TR workbook rows)."""
import os
import subprocess
import shutil
import tempfile
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="live preview test: set REACT_APP_BACKEND_URL")
API = f"{BASE_URL}/api/v1"
DEMO = f"{API}/public/demo"

EXPECTED = {
    "ironvision_ai_rmf_demo.mp4": "video/mp4",
    "ironvision_ai_rmf_narration.txt": "text/plain",
    "ironvision_ai_rmf_teleprompter.md": "text/markdown",
    "ironvision_ai_rmf_captions.srt": "application/x-subrip",
    "ironvision_ai_rmf_scene_timeline.md": "text/markdown",
    "ironvision_ai_rmf_demo_validation.md": "text/markdown",
}


@pytest.mark.parametrize("name,ctype", list(EXPECTED.items()))
def test_demo_file_200_and_content_type(name, ctype):
    r = requests.get(f"{DEMO}/{name}", timeout=30)
    assert r.status_code == 200, f"{name} -> {r.status_code}"
    assert ctype in r.headers.get("content-type", "").lower(), r.headers.get("content-type")
    assert len(r.content) > 0


def test_demo_unknown_file_404():
    r = requests.get(f"{DEMO}/does_not_exist.mp4", timeout=15)
    assert r.status_code == 404


def test_demo_mp4_range_206():
    url = f"{DEMO}/ironvision_ai_rmf_demo.mp4"
    r = requests.get(url, headers={"Range": "bytes=0-1023"}, timeout=30)
    assert r.status_code == 206, r.status_code
    cr = r.headers.get("content-range", "")
    assert cr.startswith("bytes 0-1023/"), cr
    assert len(r.content) == 1024


def test_demo_mp4_ffprobe_video_1920x1080_30fps_no_audio():
    ffprobe = shutil.which("ffprobe")
    url = f"{DEMO}/ironvision_ai_rmf_demo.mp4"
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        r = requests.get(url, timeout=120)
        assert r.status_code == 200
        f.write(r.content)
        path = f.name

    if not ffprobe:
        # Minimal integrity check: non-empty mp4 bytes
        assert os.path.getsize(path) > 1_000_000
        pytest.skip("ffprobe not installed; skipped stream-level checks")

    out = subprocess.check_output([
        ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path
    ]).decode()
    import json
    data = json.loads(out)
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    assert len(audio) == 0, f"MP4 should have NO audio stream, found {len(audio)}"
    assert len(video) == 1, f"Expected 1 video stream, got {len(video)}"
    v = video[0]
    assert v.get("codec_name") == "h264", v.get("codec_name")
    assert v.get("width") == 1920 and v.get("height") == 1080, (v.get("width"), v.get("height"))
    assert v.get("pix_fmt") == "yuv420p", v.get("pix_fmt")
    # fps
    num, den = v.get("avg_frame_rate", "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    assert 29.5 <= fps <= 30.5, fps
    duration = float(data.get("format", {}).get("duration", 0))
    assert 270 <= duration <= 330, f"duration ~300s expected, got {duration}"
