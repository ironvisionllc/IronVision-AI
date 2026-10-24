"""Tiny content model shared by the whitepaper renderers (HTML→PDF and DOCX)."""


def H1(num, title):
    return ("h1", num, title)


def H2(title):
    return ("h2", title)


def H3(title):
    return ("h3", title)


def P(text):
    return ("p", text)


def UL(*items):
    return ("ul", list(items))


def OL(*items):
    return ("ol", list(items))


def TABLE(head, rows, widths=None):
    return ("table", head, rows, widths)


def IMG(path, caption, width=100):
    return ("img", path, caption, width)


def NOTE(kind, text):
    """kind: mocked | human | sme | info | never"""
    return ("note", kind, text)


def SCREEN(name, purpose, users, actions, outputs, guardrails):
    return ("screen", name, purpose, users, actions, outputs, guardrails)


PB = ("pb",)

NOTE_LABEL = {"mocked": "MOCKED", "human": "REQUIRES HUMAN VERIFICATION", "sme": "SME REVIEW REQUIRED",
              "info": "NOTE", "never": "AI IS NEVER ALLOWED TO"}
