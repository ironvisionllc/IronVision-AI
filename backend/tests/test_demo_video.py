"""Tests for the public demo video + supporting files, and backend bug-fix 2 (POA&M label in TR workbook rows)."""
import os
import subprocess
import shutil
import tempfile
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
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


# -------- Bug fix 2: POA&M label on TR rows --------
SYSTEM_ID = "53ce70f2-6c09-4c0e-a7e5-03770d64e81a"
WORKBOOK_ID = "f7fc7110-5c55-478e-98e6-19712935ad13"


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/demo-login", json={}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token")
    assert tok
    return tok


def test_tr_workbooks_lists_generated(demo_token):
    r = requests.get(f"{API}/systems/{SYSTEM_ID}/tr/workbooks",
                     headers={"Authorization": f"Bearer {demo_token}"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    wb = next((w for w in items if w.get("id") == WORKBOOK_ID), None)
    assert wb is not None, f"workbook {WORKBOOK_ID} not found"
    assert wb.get("status") == "generated", wb.get("status")


def test_tr_workbook_row_has_poam_source_label(demo_token):
    r = requests.get(f"{API}/tr/workbooks/{WORKBOOK_ID}/rows",
                     params={"page_size": 2000},
                     headers={"Authorization": f"Bearer {demo_token}"}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = data.get("items", data if isinstance(data, list) else [])
    assert rows, "no rows returned"
    # Find any row with a poam-type source and a 'POA&M P-' label (bug fix 2)
    hits = []
    for row in rows:
        for src in (row.get("sources") or []):
            if src.get("type") == "poam" and str(src.get("label", "")).startswith("POA&M P-"):
                hits.append((row.get("row"), row.get("control_id"), src.get("label")))
    assert hits, "no poam source with 'POA&M P-' label found (bug-fix 2 regression)"
