"""Render OSCAL catalog structures into flat rows."""
import re

PARAM_RE = re.compile(r"\{\{\s*insert:\s*param,\s*([^\s}]+)\s*\}\}")


def prop(obj: dict, name: str) -> str | None:
    for p in obj.get("props", []) or []:
        if p.get("name") == name and p.get("class") != "zero-padded":
            return p.get("value")
    return None


def param_text(param: dict | None, params: dict, depth: int = 0) -> str:
    if param is None or depth > 3:
        return "[Assignment: organization-defined value]"
    if "select" in param:
        sel = param["select"]
        choices = [render_prose(c, params, depth + 1) for c in sel.get("choice", [])]
        qualifier = " (one or more)" if sel.get("how-many") == "one-or-more" else ""
        return f"[Selection{qualifier}: {'; '.join(choices)}]"
    label = param.get("label")
    if not label and param.get("guidelines"):
        label = param["guidelines"][0].get("prose")
    return f"[Assignment: {label or param.get('id')}]"


def render_prose(text: str | None, params: dict, depth: int = 0) -> str:
    if not text:
        return ""
    return PARAM_RE.sub(lambda m: param_text(params.get(m.group(1)), params, depth), text)


def render_statement(part: dict, params: dict, depth: int = 0) -> list[str]:
    lines = []
    label = prop(part, "label")
    prose = render_prose(part.get("prose"), params)
    if prose or label:
        lines.append(("    " * depth) + " ".join(x for x in (label, prose) if x))
    for child in part.get("parts", []) or []:
        if child.get("name") == "item":
            lines.extend(render_statement(child, params, depth + (1 if (prose or label) else 0)))
    return lines


def flatten_objectives(part: dict, params: dict, parent: str | None = None, depth: int = 0, out: list | None = None) -> list:
    out = [] if out is None else out
    out.append({
        "objective_id": part.get("id") or f"{parent}-{len(out)}",
        "parent_objective_id": parent,
        "label": prop(part, "label"),
        "prose": render_prose(part.get("prose"), params) or None,
        "depth": depth,
        "sort_order": len(out),
    })
    for child in part.get("parts", []) or []:
        if child.get("name") == "assessment-objective":
            flatten_objectives(child, params, part.get("id"), depth + 1, out)
    return out


def assessment_methods(parts: list) -> list:
    methods = []
    for p in parts:
        if p.get("name") != "assessment-method":
            continue
        objects = [o.get("prose") for o in p.get("parts", []) or [] if o.get("name") == "assessment-objects"]
        methods.append({"method": prop(p, "method"), "objects": objects})
    return methods
