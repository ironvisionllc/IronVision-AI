"""Requirement profiles for non-XX-1 controls: each 800-53A objective / CCI is reduced to the concepts it names (and the
organization-defined values it needs); a policy sentence (or two adjacent sentences) must contain all of them to be MET.
Precision first: a false MET is worse than a false MISSING."""
import re

NUMW = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|thirty|sixty|ninety)"
DUR = rf"\b{NUMW}\s*(?:-\s*)?(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b"
FREQ_ANY = (rf"\b(?:daily|weekly|monthly|quarterly|annually|yearly|semi-?annually|biennially|every\s+{NUMW}\s+(?:hours?|days?|weeks?|months?|years?)"
            r"|at least (?:once )?(?:a |per |every )?(?:day|week|month|quarter|year|annually|weekly|monthly))\b")
NUM = rf"\b{NUMW}\b"

LEX = {
    "account_type": r"account types?|types? of (?:system )?accounts?|(?:individual|shared|group|guest|emergency|temporary|service|privileged) accounts?",
    "account_manager": r"account managers?",
    "group_membership": r"group membership|membership in groups?",
    "logon_attempts": r"(?:invalid|unsuccessful|failed|consecutive|incorrect) (?:(?:logon|login|log-on|sign-in|authentication|password) )?attempts?",
    "lock": r"\block(?:s|ed|ing|out)?\b|lockout",
    "inactivity": r"inactiv\w*|\bidle\b|period of inactivity",
    "device_lock": r"(?:device|session|screen|workstation) lock|screen ?saver",
    "reestablish": r"re-?establish\w*|re-?authenticat\w*|(?:identification and )?authentication procedures",
    "audit_record": r"audit (?:records?|logs?|trails?|data)|security logs?|event logs?",
    "review_analyze": r"\breview\w*|\banaly[sz]\w*",
    "report": r"\breport\w*",
    "indications": r"indications?|anomal\w*|suspicious|inappropriate or unusual|unusual activity",
    "retain": r"\bretain\w*|retention|kept for|stored for|preserved for",
    "investigation": r"investigat\w*",
    "baseline_config": r"baseline configurations?|configuration baselines?|secure baselines?|\bbaselines?\b",
    "config_control": r"configuration control|change control|configuration management (?:board|process)|version control",
    "installed": r"\binstall\w*|upgrad\w*",
    "incident": r"\bincidents?\b",
    "ir_capability": r"incident response (?:team|capabilit\w*|function)|\bCSIRT\b|\bCIRT\b|security operations cent\w*|\bSOC\b",
    "authorities": r"\bauthorit\w*|US-CERT|\bCISA\b|law enforcement|regulators?|cyber ?command",
    "backup": r"\bbackups?\b|back(?:ed)? up",
    "user_level": r"user(?:-level)? (?:data|information|files)",
    "system_level": r"system(?:-level)? (?:data|information|images?|state|configuration)",
    "documentation": r"\bdocumentation\b",
    "confidentiality": r"confidential\w*|encrypt\w*",
    "integrity": r"\bintegrity\b|checksums?|\bhash\w*",
    "availability": r"availab\w*|off-?site|alternate (?:storage )?(?:site|location)",
    "authenticator": r"authenticators?|passwords?|passphrases?|\bPINs?\b|credentials?|\btokens?\b",
    "identity_verify": r"identity (?:is |must be |shall be )?(?:verif\w*|proof\w*|confirm\w*)|verif\w* (?:the )?identity|identity proofing",
    "initial_content": r"initial (?:authenticator|password|credential)s?|temporary passwords?",
    "strength": r"\bstrength\b|complexity|minimum (?:length|of \d+ characters)|\d+ characters",
    "default_auth": r"default (?:authenticators?|passwords?|credentials?)",
    "change_refresh": r"\bchang\w*|refresh\w*|rotat\w*|expir\w*",
    "protect_content": r"unauthorized disclosure|protect\w* (?:from|against)|encrypt\w*|hash\w*",
    "personnel": r"personnel|\bstaff\b|employees|\busers?\b|workforce",
    "findings": r"\bfindings?\b",
    "account": r"\baccounts?\b",
    "assign": r"\bassign\w*|\bdesignat\w*|\bappoint\w*",
    "approval": r"\bapprov\w*",
    "create": r"\bcreat\w*|\bprovision\w*",
    "disable": r"\bdisabl\w*",
    "notify": r"\bnotif\w*",
    "authorize": r"\bauthori[sz]\w*",
    "prohibit": r"\bprohibit\w*|not permitted|forbidden",
    "in_accordance": r"in accordance with|according to|as defined in|per the (?:policy|procedures?)",
    "monitor": r"\bmonitor\w*",
    "termination": r"\bterminat\w*|\bseparat\w*|offboard\w*",
    "transfer": r"\btransfer\w*|\breassign\w*",
    "aligned": r"\balign\w*|integrat\w* with|coordinat\w* with",
    "membership": r"\bmembership\b",
    "group_role_accounts": r"(?:group|role|shared)(?: or (?:group|role|shared))? accounts?",
    "develop_doc": r"\bdevelop\w*|\bdocument(?:ed|s)?\b|\bdefin(?:e|es|ed|ing)\b",
    "update": r"\bupdat\w*",
    "maintain": r"\bmaintain\w*",
    "when_required": r"when required|as required|due to|in response to|following|whenever",
}
PARAMS = {"frequency": FREQ_ANY, "time period": DUR, "time": DUR, "number": NUM, "period": DUR, "authorities": LEX["authorities"]}
TECH = re.compile(r"\b(enforc\w*|employ\w*|implement\w*|automatic\w*|prevent\w*|lock\w*|retain\w*|protect\w*|conducted|monitor\w*|detect\w*|initiat\w*|configur\w*)\b", re.I)
PH = re.compile(r"\[(?:Assignment|Selection)[^\[\]]*(?:\[[^\]]*\][^\[\]]*)*\]", re.I)


MASK = re.compile(r"\b[A-Z]{2}-\d+(?:\s*\(\d+\))?(?:\.\d+)?\b|^\s*(?:section\s+)?\d+(?:\.\d+)*\.?(?=\s)", re.I | re.M)


def mask(s: str) -> str:
    """Blank control IDs (AC-7) and section numbering (4.2) with spaces – same length, so offsets stay valid – before reading values."""
    return MASK.sub(lambda m: " " * len(m.group(0)), s)


def req_kind(text: str) -> str:
    """policy = satisfiable by documentation (define/document/review/report); technical = needs implementation evidence."""
    return "technical" if TECH.search(PH.sub(" ", text or "")) else "policy"


def profile(text: str) -> dict:
    """Concepts named outside placeholders + the first option of each Selection (one-or-more → first option is the default reading)."""
    plain = PH.sub(" ", text or "")
    sels = [re.split(r";", ph.split(":", 1)[1] if ":" in ph else ph)[0] for ph in PH.findall(text or "") if ph.lower().startswith("[selection")]
    plain += " " + " ".join(PH.sub(" ", x) + " " + " ".join(re.findall(r"\[Assignment[^\]]*\]", x, re.I)) for x in sels)
    concepts = [k for k, rx in LEX.items() if re.search(rx, PH.sub(" ", plain), re.I)]
    if "device_lock" in concepts and "lock" in concepts:
        concepts.remove("lock")
    if "account_type" in concepts and "account_manager" in concepts and "group_membership" in concepts:
        concepts.remove("account_type")
    params = []
    for ph in PH.findall(text or "") + re.findall(r"\[Assignment[^\[\]]*\]", " ".join(sels), re.I):
        low = ph.lower()
        if low.startswith("[assignment"):
            p = next((k for k in PARAMS if k in low), None)
            if p and PARAMS[p] not in params:
                params.append(PARAMS[p])
    return {"concepts": concepts, "params": params}


def _cid_rx(control_id: str) -> str:
    fam, num = control_id.split("-", 1)
    return rf"\b{fam}-0?{re.escape(num.split('.')[0])}\b"


class _Index:
    """Per-document match index: each concept/value regex is run once over the masked sentences and 2-sentence windows (was once per
    requirement × sentence – 140 s for a 284-control policy). Results are identical to the per-call re.search."""

    def __init__(self, sents: list):
        self.sents = sents
        self.ms = [mask(x[2]) for x in sents]
        self.mw = [mask(" ".join(x[2] for x in sents[i:i + 2])) for i in range(len(sents))]
        self.cache: dict = {}
        self.cid: dict = {}

    def hits(self, need: list, window: bool) -> dict:
        src = self.mw if window else self.ms
        out = {}
        for _, rx in need:
            key = (rx, window)
            if key not in self.cache:
                c = re.compile(rx, re.I)
                self.cache[key] = {i for i, w in enumerate(src) if c.search(w)}
            out[rx] = self.cache[key]
        return out

    def cited(self, control_id: str) -> set:
        if control_id not in self.cid:
            c = re.compile(_cid_rx(control_id), re.I)
            self.cid[control_id] = {i for i, (_, _, x) in enumerate(self.sents) if c.search(x)}
        return self.cid[control_id]


_IX: dict = {}


def _index(text: str, sents: list) -> _Index:
    import hashlib
    k = (hashlib.sha256(text.encode()).hexdigest(), len(sents))
    if k not in _IX:
        _IX.clear()  # one document at a time – no long-lived cache of customer content
        _IX[k] = _Index(sents)
    return _IX[k]


LABEL = {  # readable wording for gap/met reasons (was the raw concept key: "does not state: in accordance, develop doc")
    "in_accordance": "that it follows a defined process or standard (“in accordance with …”)", "develop_doc": "that it is developed or documented",
    "when_required": "when it is required (triggering conditions)", "review_analyze": "review or analysis", "change_refresh": "changing or refreshing",
    "protect_content": "protection of the content", "aligned": "alignment or coordination with related processes", "create": "creation",
    "disable": "disabling", "notify": "notification", "authorize": "authorization", "prohibit": "prohibition", "monitor": "monitoring",
    "update": "updating", "maintain": "maintenance", "report": "reporting", "assign": "assignment of responsibility", "approval": "approval",
    "termination": "termination", "transfer": "transfer or reassignment", "installed": "installation", "reestablish": "re-establishing access",
    "personnel": "the personnel or roles involved", "findings": "the findings", "account": "the accounts concerned", "membership": "membership",
}


def _lbl(k: str) -> str:
    return "the organization-defined value" if k.startswith("value") else LABEL.get(k, k.replace("_", " "))


def evaluate(text: str, sents: list, control_id: str, req_text: str, snip) -> dict | None:
    """MET/PARTIAL/MISSING with confidence + basis, or None when the requirement has too few concepts to judge."""
    prof = profile(req_text)
    need = [(k, LEX[k]) for k in prof["concepts"]] + [(f"value:{i}", rx) for i, rx in enumerate(prof["params"])]
    if len(prof["concepts"]) < 1 or len(need) < 2:
        return None
    ix = _index(text, sents)
    cited = ix.cited(control_id)
    hs, hw = ix.hits(need, False), ix.hits(need, True)  # same matches as re.search(rx, mask(sentence|2-sentence window)) – precomputed per rx
    single = [(i, [k for k, rx in need if i in hs[rx]]) for i in range(len(sents))]
    best_i, best = max(single, key=lambda x: len(x[1]), default=(None, []))
    pair_i, pair = max(((i, [k for k, rx in need if i in hw[rx]]) for i in range(len(sents))), key=lambda x: len(x[1]), default=(None, []))
    r = {"parameter": None, "value": None, "needs": None}
    missing = [k for k, _ in need if k not in (best if len(best) == len(need) else pair)]
    label = "; ".join(_lbl(k) for k, _ in need)
    if len(best) == len(need) or len(pair) == len(need):
        i = best_i if len(best) == len(need) else pair_i
        hits = sents[i:i + (1 if len(best) == len(need) else 2)]
        expl = bool(cited & set(range(max(0, i - 3), i + 2)))
        conf = "High" if expl or (len(best) == len(need) and len(need) >= 3) else "Medium"
        val, vhits = None, hits
        if prof["params"]:  # each value is read from the one sentence that states it (never a neighbour, ID or section number)
            for h in hits:
                got_v = [m.group(0) for rx in prof["params"] for m in [re.search(rx, mask(h[2]), re.I)] if m]
                if got_v:
                    val, vhits = "; ".join(got_v), [h]
                    break
        r.update(status="met", confidence=conf, snippets=snip(vhits), reason=f"One policy passage covers every element of the requirement: {label}.", basis="id" if expl else "concept",
                 value=val, parameter="organization-defined value" if val else None)
        return r
    got = max(best, pair, key=len)
    if len(got) * 2 >= len(need):
        hits = sents[pair_i:pair_i + 2] if got is pair else sents[best_i:best_i + 1]
        r.update(status="partial", confidence="Medium" if len(need) - len(got) == 1 else "Low", snippets=snip(hits), basis="concept",
                 reason=f"Related text found, but the policy does not state {'; '.join(_lbl(m) for m in missing)}.",
                 needs=f"Add a statement covering {'; '.join(_lbl(m) for m in missing)}.")
        return r
    r.update(status="missing", confidence="High" if not got else "Medium", snippets=[], basis="concept",
             reason="No sentence addresses this requirement." if not got else f"Only {len(got)} of {len(need)} required elements appear near each other.",
             needs=f"Add a statement covering: {label}.")
    return r


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def verify_quote(text: str, quote: str | None) -> bool:
    return bool(quote and len(quote.strip()) >= 12 and _norm(quote) in _norm(text))


def apply_ai(text: str, row: dict, ai: dict | None) -> dict:
    """Merge an AI verdict into a deterministic result. AI may only raise to MET with an exact quote; disagreement → Low (review needed)."""
    if not ai:
        return row
    if ai.get("status") == "met":
        if not verify_quote(text, ai.get("quote")):
            row["reason"] = (row.get("reason") or "") + " AI suggested MET but its quote is not in the policy text – AI result discarded."
            row["ai_discarded"] = True
            return row
        if row["status"] == "met":  # both say met: keep the quote that actually addresses the requirement's subject
            from app.services.policy_coverage import relevant
            cur = (row.get("snippets") or [{}])[0].get("text") if row.get("snippets") else None
            if row.get("_req") and not relevant(cur, *row["_req"]) and relevant(ai.get("quote"), *row["_req"]):
                row.update(basis="ai", snippets=[{"text": ai["quote"][:300], "location": ""}], reason=f"AI-verified quote: {ai.get('rationale', '')[:300]}")
            return row
        if row["status"] != "met":
            row.update(status="met" if row["status"] == "partial" else "partial", confidence="Medium" if row["status"] == "partial" else "Low",
                       basis="ai", snippets=[{"text": ai["quote"][:300], "location": row.get("snippets", [{}])[0].get("location", "") if row.get("snippets") else ""}],
                       reason=f"AI-verified quote: {ai.get('rationale', '')[:300]}", needs=None if row["status"] == "partial" else row.get("needs"))
        return row
    if row["status"] == "missing" and ai.get("status") == "partial" and verify_quote(text, ai.get("quote")):  # evidence exists → manual review, not "missing"
        row.update(status="partial", confidence="Low", basis="ai", snippets=[{"text": ai["quote"][:300], "location": ""}],
                   reason=f"AI found related text, but it does not fully meet the requirement: {ai.get('rationale', '')[:300]} – manual review.")
        return row
    if row["status"] == "met" and ai.get("status") in ("partial", "missing"):
        row.update(status="partial", confidence="Low", basis="ai", reason=row["reason"] + f" AI disagrees ({ai['status']}): {ai.get('rationale', '')[:200]} – review needed.")
    return row
