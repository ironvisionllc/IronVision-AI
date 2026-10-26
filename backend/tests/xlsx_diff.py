"""Independent cell-by-cell workbook diff used by the TR export-mode guard tests (does not reuse the exporter's own verify())."""
import io
import re
import zipfile

import openpyxl


def _sheet(ws) -> dict:
    cells = {}
    for (r, c), cell in ws._cells.items():
        cells[cell.coordinate] = (cell.value, cell.data_type, tuple(cell._style) if cell.has_style else None, cell.number_format)
    return {
        "cells": cells,
        "merged": sorted(str(m) for m in ws.merged_cells.ranges),
        "validations": [(d.type, d.operator, d.formula1, d.formula2, str(d.sqref), d.allow_blank, d.showErrorMessage) for d in ws.data_validations.dataValidation],
        "conditional_formatting": sorted((str(cf.sqref), tuple(repr(r.formula) + r.type for r in cf.rules)) for cf in ws.conditional_formatting),
        "col_widths": {k: (v.width, v.hidden, v.min, v.max) for k, v in ws.column_dimensions.items()},
        "row_heights": {k: (v.height, v.hidden) for k, v in ws.row_dimensions.items() if v.height is not None or v.hidden},
        "freeze": str(ws.freeze_panes), "state": ws.sheet_state, "dims": ws.dimensions,
        "names": sorted((n, d.attr_text) for n, d in ws.defined_names.items()),
    }


def snapshot(data: bytes) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(data))
    return {"sheets": wb.sheetnames, "defined_names": sorted((n, d.attr_text) for n, d in wb.defined_names.items()),
            "sheet": {ws.title: _sheet(ws) for ws in wb.worksheets}}


def _split(ref: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return m.group(1), int(m.group(2))


def diff(a: bytes, b: bytes) -> dict:
    sa, sb = snapshot(a), snapshot(b)
    out = {"sheet_order_changed": sa["sheets"] != sb["sheets"], "defined_names_changed": sa["defined_names"] != sb["defined_names"],
           "structure": [], "cells": {}}
    za, zb = zipfile.ZipFile(io.BytesIO(a)), zipfile.ZipFile(io.BytesIO(b))
    out["zip_parts_changed"] = sorted(n for n in set(za.namelist()) | set(zb.namelist())
                                      if n not in za.namelist() or n not in zb.namelist() or za.read(n) != zb.read(n))
    for title in sa["sheets"]:
        x, y = sa["sheet"][title], sb["sheet"].get(title)
        if y is None:
            out["structure"].append(f"{title}: sheet missing")
            continue
        for k in ("merged", "validations", "conditional_formatting", "col_widths", "row_heights", "freeze", "state", "names"):
            if x[k] != y[k]:
                out["structure"].append(f"{title}: {k} changed")
        changed = []
        for ref in sorted(set(x["cells"]) | set(y["cells"]), key=lambda r: (_split(r)[1], len(_split(r)[0]), _split(r)[0])):
            ca, cb = x["cells"].get(ref), y["cells"].get(ref)
            if ca == cb:
                continue
            ea = ca is None or (ca[0] is None and ca[2] is None)
            eb = cb is None or (cb[0] is None and cb[2] is None)
            if ea and eb:
                continue
            kinds = [n for i, n in enumerate(("value", "type", "style", "number_format")) if (ca or (None,) * 4)[i] != (cb or (None,) * 4)[i]]
            changed.append({"cell": ref, "changed": kinds, "before": None if ca is None else _j(ca[0]), "after": None if cb is None else _j(cb[0])})
        if changed:
            out["cells"][title] = changed
    return out


def _j(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def by_column(d: dict, sheet: str) -> dict:
    cols: dict = {}
    for c in d["cells"].get(sheet, []):
        col, row = _split(c["cell"])
        e = cols.setdefault(col, {"cells": 0, "first_row": row, "last_row": row, "kinds": set()})
        e["cells"] += 1
        e["first_row"], e["last_row"] = min(e["first_row"], row), max(e["last_row"], row)
        e["kinds"].update(c["changed"])
    return {k: {**v, "kinds": sorted(v["kinds"])} for k, v in sorted(cols.items(), key=lambda x: (len(x[0]), x[0]))}


def violations(d: dict, sheet: str, allowed: dict[str, set[int]]) -> list[str]:
    """allowed = {column: set of permitted rows}. Anything else that changed – any cell, any other sheet, any structure – is a violation."""
    bad = list(d["structure"])
    bad += [f"{s}: {len(v)} cell(s) changed" for s, v in d["cells"].items() if s != sheet]
    if d["sheet_order_changed"]:
        bad.append("sheet list/order changed")
    if d["defined_names_changed"]:
        bad.append("defined names changed")
    for c in d["cells"].get(sheet, []):
        col, row = _split(c["cell"])
        if row not in allowed.get(col, set()):
            bad.append(f"{sheet}!{c['cell']} changed ({', '.join(c['changed'])}) – outside the permitted columns/rows")
    return bad
