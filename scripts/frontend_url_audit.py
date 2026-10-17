#!/usr/bin/env python3
"""Built-frontend URL audit (stdlib only). Classifies every absolute URL in the built JS/HTML:

  FAIL  real runtime/config use of a dev/preview target – localhost / 127.0.0.1 / 0.0.0.0 / *.preview.emergentagent.com /
        emergent hosts used as an API base, fetch/XHR/axios/WebSocket/EventSource target, redirect or baked REACT_APP_/VITE_ value
  INFO  known library error-message / documentation links inside vendor code (allowlisted below, with the reason), and
        URL-parsing bases such as `new URL(path, "http://localhost")` (no request is ever sent there)
  WARN  any other absolute URL (listed for review, not a failure)

    scripts/frontend_url_audit.py DIR_OR_FILE…          (exit 1 when any FAIL)
    … | scripts/frontend_url_audit.py --stdin           (concatenated files separated by '=== <path>' lines)"""
import re
import sys
from pathlib import Path

DEV = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\]|[\w.-]*preview\.emergentagent\.com|[\w.-]*emergent(agent)?\.(com|host|sh))$", re.I)
# host → why its links are harmless (library error decoders / docs; never fetched by the app)
DOC_HOSTS = {
    "react.dev": "React production error decoder links (https://react.dev/errors/N) in react-dom",
    "reactjs.org": "React legacy docs/error links in react / react-dom",
    "legacy.reactjs.org": "React legacy docs links",
    "reactrouter.com": "React Router warning/doc links (future flags, hooks outside <Router>)",
    "redux.js.org": "Redux error-message doc links (redux.js.org/Errors?code=N)",
    "redux-toolkit.js.org": "Redux Toolkit warning/doc links (serializability/immutability middleware)",
    "bit.ly": "short doc links inside vendor warnings (e.g. Redux Toolkit / Immer / React error text) – never requested",
    "immerjs.github.io": "Immer error doc links",
    "github.com": "library issue/doc links in warning strings",
    "fb.me": "React legacy warning short links",
    "www.w3.org": "XML/SVG namespace identifiers",
    "w3.org": "XML/SVG namespace identifiers",
    "mui.com": "MUI error decoder links",
    "radix-ui.com": "Radix UI accessibility warning links",
    "tanstack.com": "TanStack warning/doc links",
    "zod.dev": "Zod error doc links",
}
URL = re.compile(r"""(?:https?|wss?)://(\[[0-9a-f:]+\]|[A-Za-z0-9.-]+)(?::\d+)?[^\s"'`<>)\\]*""")
RUNTIME = re.compile(r"""(baseURL|baseUrl|BASE_URL|API_URL|apiUrl|BACKEND_URL|REACT_APP_|VITE_|fetch\(|axios|XMLHttpRequest|\.open\(|WebSocket\(|"""
                     r"""EventSource\(|io\(|location\.(href|assign|replace)|window\.open|redirect|href\s*[:=]|src\s*[:=]|endpoint|origin)""")
PARSE_BASE = re.compile(r"""new URL\([^()]{0,120},\s*["'`]$|new URL\(\s*["'`]$""")
LOC_FALLBACK = re.compile(r"""location\.(origin|href)""")


def classify(text: str, start: int, end: int, host: str) -> tuple[str, str]:
    before, after = text[max(0, start - 160):start], text[end:end + 40]
    h = host.lower().strip("[]")
    if DEV.match(h) or h == "::1":
        exact = re.fullmatch(r"https?://localhost/?", text[start:end]) is not None
        if exact and PARSE_BASE.search(before):
            return "INFO", "URL-parsing base `new URL(…, \"http://localhost\")` (router/axios internals) – no request is sent"
        if exact and (LOC_FALLBACK.search(before[-60:]) or LOC_FALLBACK.search(text[end:end + 120])):
            return "INFO", "library fallback for window.location (replaced by location.origin/href in the browser) – no request is sent"
        if RUNTIME.search(before[-100:]) or re.match(r"""\s*["'`]?\s*[,;)}]""", after) and RUNTIME.search(before):
            return "FAIL", "dev/preview host used as a runtime target (API base / request / redirect / env value)"
        return "FAIL", "dev/preview host baked into the bundle (no library allowlist applies)"
    if h in DOC_HOSTS:
        return "INFO", DOC_HOSTS[h]
    return "WARN", "unclassified absolute URL – review"


def audit(files: list[tuple[str, str]]) -> list[dict]:
    hits = []
    for path, text in files:
        for m in URL.finditer(text):
            lvl, why = classify(text, m.start(), m.end(), m.group(1))
            hits.append({"level": lvl, "file": path, "url": m.group(0)[:120], "why": why,
                         "context": text[max(0, m.start() - 60):m.end() + 30].replace("\n", " ")})
    return hits


def read_inputs(argv: list[str]) -> list[tuple[str, str]]:
    if argv == ["--stdin"]:
        files, cur, buf = [], "<stdin>", []
        for line in sys.stdin.read().splitlines(keepends=True):
            if line.startswith("=== "):
                if buf:
                    files.append((cur, "".join(buf)))
                cur, buf = line[4:].strip(), []
            else:
                buf.append(line)
        if buf:
            files.append((cur, "".join(buf)))
        return files
    out = []
    for a in argv:
        p = Path(a)
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and f.suffix in (".js", ".html", ".mjs", ".json") and not f.name.endswith(".map"):
                out.append((str(f), f.read_text(errors="replace")))
    return out


def main(argv: list[str]) -> int:
    hits = audit(read_inputs(argv))
    seen = set()
    for h in sorted(hits, key=lambda x: ({"FAIL": 0, "WARN": 1, "INFO": 2}[x["level"]], x["url"])):
        k = (h["level"], h["url"], h["file"])
        if k in seen:
            continue
        seen.add(k)
        print(f"  {h['level']:<4} {h['url']}  [{Path(h['file']).name}] {h['why']}" + (f"\n         …{h['context']}…" if h["level"] != "INFO" else ""))
    n = {lv: len({(h['url'], h['file']) for h in hits if h["level"] == lv}) for lv in ("FAIL", "WARN", "INFO")}
    print(f"  frontend URL audit: {n['FAIL']} FAIL, {n['WARN']} WARN, {n['INFO']} INFO (allowlisted library/doc links)")
    return 1 if n["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
