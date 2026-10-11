#!/usr/bin/env bash
# Regenerates favicons from the single swappable brand file frontend/src/assets/brand/logo.svg.
# Requires: pip install cairosvg (dev-only tool; not an app dependency). Run after replacing logo.svg with the official vector.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/frontend/src/assets/brand/logo.svg"
PUB="$ROOT/frontend/public"
cp "$SRC" "$PUB/favicon.svg"
python3 - "$SRC" "$PUB" <<'EOF'
import sys, cairosvg
src, pub = sys.argv[1], sys.argv[2]
for size, name in ((16, "favicon-16.png"), (32, "favicon-32.png"), (180, "apple-touch-icon.png"), (512, "logo-512.png")):
    bg = "#FFFFFF" if name == "apple-touch-icon.png" else None
    cairosvg.svg2png(url=src, write_to=f"{pub}/{name}", output_width=size, output_height=size, background_color=bg)
    print("wrote", name)
EOF
