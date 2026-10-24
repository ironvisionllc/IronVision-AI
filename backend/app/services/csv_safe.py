"""CSV export helpers: formula-injection protection, proper quoting and a UTF-8 BOM so Excel opens the file correctly."""
import csv
import io

_DANGER = ("=", "+", "-", "@", "\t", "\r")


def cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_DANGER) else s


def to_csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow([cell(h) for h in header])
    for r in rows:
        w.writerow([cell(v) for v in r])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
