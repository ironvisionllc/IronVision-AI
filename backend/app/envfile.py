"""Env-file reading, linting and safe fixing – stdlib only, never evaluates anything.

Parsing follows Docker Compose `--env-file` / python-dotenv semantics, so every reader (backend, scripts/envget.py,
scripts/check_env.py, Compose) gets the same value:
  KEY=value            unquoted; a ` #` starts an inline comment; surrounding whitespace is trimmed
  KEY="value"          double quotes: \\" \\\\ \\n \\t escapes (Compose also interpolates ${VAR} inside – avoid `$` here)
  KEY='value'          single quotes: literal
Env files are DATA, never shell scripts: do not `source` / `. ` them (`OIDC_SCOPES=openid email profile` would run `email`)."""
import re

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHELL_SPECIAL = set(" \t$#;&|<>()*`'\"\\!?{}[]~")
_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _split_line(raw: str) -> tuple[str, str, bool] | None:
    """(key, value-part, had_export) for a KEY=... line, None for blank/comment lines."""
    s = raw.strip()
    if not s or s.startswith("#"):
        return None
    had_export = s.startswith("export ")
    if had_export:
        s = s[len("export "):].lstrip()
    if "=" not in s:
        return ("", s, had_export)
    k, v = s.split("=", 1)
    return (k.strip(), v.lstrip(), had_export)


def parse_value(raw: str) -> tuple[str, bool, str | None, str]:
    """(value, ok, quote_char, trailing_comment) for the text after `=`."""
    if raw[:1] in ('"', "'"):
        q, out, i = raw[0], [], 1
        while i < len(raw):
            c = raw[i]
            if q == '"' and c == "\\" and i + 1 < len(raw):
                out.append(_ESC.get(raw[i + 1], "\\" + raw[i + 1]))
                i += 2
                continue
            if c == q:
                rest = raw[i + 1:].strip()
                return "".join(out), rest == "" or rest.startswith("#"), q, rest
            out.append(c)
            i += 1
        return raw, False, q, ""
    m = re.search(r"\s+#.*$", raw)
    comment = m.group(0).strip() if m else ""
    return (raw[:m.start()] if m else raw).strip(), True, None, comment


def parse_env_text(text: str) -> dict[str, str]:
    env = {}
    for raw in text.replace("\r\n", "\n").split("\n"):
        parts = _split_line(raw)
        if parts and parts[0]:
            env[parts[0]] = parse_value(parts[1])[0]
    return env


def parse_env_file(path) -> dict[str, str]:
    from pathlib import Path
    return parse_env_text(Path(path).read_text())


def quote(value: str) -> str:
    """Quote so Compose, python-dotenv and (if someone still sources it) a POSIX shell all read the same literal."""
    if "'" not in value and any(c in value for c in "$`\\\""):
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$") + '"'


def needs_quotes(value: str) -> str | None:
    return next((c for c in value if c in SHELL_SPECIAL), None)


def lint_env_text(text: str) -> list[dict]:
    """Issues: {line, message, suggestion|None}. Callers decide error vs warning (error in staging/production)."""
    issues, seen = [], {}
    if "\r\n" in text:
        issues.append({"line": 1, "message": "CRLF (Windows) line endings", "suggestion": "convert to LF (check_env.py --fix)"})
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if raw != raw.rstrip():
            issues.append({"line": n, "message": "trailing whitespace", "suggestion": raw.rstrip()})
        parts = _split_line(raw)
        if not parts:
            continue
        key, val, had_export = parts
        if not key:
            issues.append({"line": n, "message": f"not a KEY=value line: {raw.strip()[:60]!r}", "suggestion": None})
            continue
        if had_export:
            issues.append({"line": n, "message": "`export ` prefix (env files are not shell scripts)", "suggestion": f"{key}={val}"})
        if not KEY_RE.match(key):
            issues.append({"line": n, "message": f"invalid variable name {key!r} (letters, digits, _; not starting with a digit)",
                           "suggestion": None})
        if key in seen:
            issues.append({"line": n, "message": f"duplicate key {key} (also on line {seen[key]}; the last one wins)",
                           "suggestion": f"delete line {seen[key]}"})
        seen[key] = n
        value, ok, q, comment = parse_value(val)
        if not ok:
            issues.append({"line": n, "message": f"{key}: unbalanced quote or text after the closing quote", "suggestion": None})
        elif q is None and (c := needs_quotes(value)):
            what = "whitespace" if c.isspace() else f"shell metacharacter {c!r}"
            issues.append({"line": n, "message": f"{key}: unquoted value contains {what}",
                           "suggestion": f"{key}={quote(value)}" + (f"  {comment}" if comment else "")})
        elif q == '"' and ("$" in value or "`" in value):
            issues.append({"line": n, "message": f"{key}: `$`/backtick inside double quotes is interpolated by Docker Compose",
                           "suggestion": f"{key}={quote(value)}"})
    return issues


def fix_env_text(text: str) -> tuple[str, list[str], list[str]]:
    """(new_text, changes, unfixable). Preserves comments, blank lines and order."""
    lines = text.replace("\r\n", "\n").split("\n")
    changes = ["CRLF → LF"] if "\r\n" in text else []
    unfixable, last = [], {}
    for n, raw in enumerate(lines):
        parts = _split_line(raw)
        if parts and parts[0]:
            last[parts[0]] = n
    out = []
    for n, raw in enumerate(lines):
        parts = _split_line(raw)
        line = raw.rstrip()
        if line != raw:
            changes.append(f"line {n + 1}: trailing whitespace removed")
        if not parts:
            out.append(line)
            continue
        key, val, had_export = parts
        if not key or not KEY_RE.match(key):
            unfixable.append(f"line {n + 1}: {line.strip()[:60]!r} – fix by hand")
            out.append(line)
            continue
        if last[key] != n:
            out.append(f"# [check_env --fix] duplicate, overridden on line {last[key] + 1}: {line.strip()}")
            changes.append(f"line {n + 1}: duplicate {key} commented out")
            continue
        value, ok, q, comment = parse_value(val.rstrip())
        if not ok:
            unfixable.append(f"line {n + 1}: {key} has an unbalanced quote – fix by hand")
            out.append(line)
            continue
        new = f"{key}={val.rstrip()}"
        if (q is None and needs_quotes(value)) or (q == '"' and ("$" in value or "`" in value)):
            new = f"{key}={quote(value)}" + (f"  {comment}" if comment else "")
            changes.append(f"line {n + 1}: {key} quoted")
        if had_export:
            changes.append(f"line {n + 1}: `export ` removed from {key}")
        indent = raw[: len(raw) - len(raw.lstrip())]
        out.append(indent + new if new != line.strip() else line)
    return "\n".join(out), changes, unfixable
