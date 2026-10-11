#!/usr/bin/env bash
# Downloads Inter + Plus Jakarta Sans (latin, woff2) from Google Fonts into frontend/public/fonts and writes fonts.css.
# For air-gapped deployments, replace the Google Fonts <link> tags in frontend/deploy/index.html with
#   <link rel="stylesheet" href="/fonts/fonts.css" />
# (or simply remove them – the CSS stacks fall back to system-ui fonts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/frontend/public/fonts"
mkdir -p "$OUT"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
: > "$OUT/fonts.css"
for spec in "Inter:300;400;500;600;700;800" "Plus+Jakarta+Sans:400;500;600;700;800"; do
  css=$(curl -fsS -A "$UA" "https://fonts.googleapis.com/css2?family=${spec%%:*}:wght@${spec#*:}&display=swap")
  # keep only the latin subset blocks
  echo "$css" | python3 -c "
import re,sys,subprocess,os
css=sys.stdin.read(); out=os.environ['OUT']
for comment,block in re.findall(r'/\* (\S+) \*/\s*(@font-face \{.*?\})', css, re.S):
    if comment!='latin': continue
    url=re.search(r'url\((https://[^)]+)\)', block).group(1)
    fam=re.search(r\"font-family: '([^']+)'\", block).group(1).replace(' ','')
    w=re.search(r'font-weight: (\d+)', block).group(1)
    name=f'{fam}-{w}.woff2'
    subprocess.run(['curl','-fsS','-o',f'{out}/{name}',url],check=True)
    print(block.replace(url,f'/fonts/{name}'))
" >> "$OUT/fonts.css"
done
ls "$OUT"
