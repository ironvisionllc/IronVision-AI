"""Running code version: BUILD_SHA / BUILD_TIME baked into the Docker image at build time (ARG → ENV); in dev falls back to git."""
import os
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache
def build_info() -> dict:
    sha, built = os.environ.get("BUILD_SHA", "").strip(), os.environ.get("BUILD_TIME", "").strip()
    if sha:
        return {"git_sha": sha[:40], "build_time": built or None, "source": "image build args"}
    root = Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%H|%cI"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        h, t = out.split("|")
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True,
                                    timeout=5).stdout.strip())
        return {"git_sha": h, "build_time": None, "commit_time": t, "dirty": dirty, "source": "git checkout (dev)"}
    except Exception:  # noqa: BLE001 – no git and no build args: say so rather than guess
        return {"git_sha": None, "build_time": None, "source": "unknown – image built without BUILD_SHA"}
