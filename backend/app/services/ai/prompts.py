from dataclasses import dataclass

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthCheckOutput(BaseModel):
    status: str = Field(pattern="^ok$")
    nonce: str
    summary: str = Field(max_length=300)


class ImplementationStatementOutput(BaseModel):
    narrative: str = Field(min_length=20, max_length=8000)
    citations: list[str] = Field(default_factory=list, max_length=50)
    verified_facts: list[str] = Field(default_factory=list, max_length=30)
    interpretation: list[str] = Field(default_factory=list, max_length=30)
    suggested_actions: list[str] = Field(default_factory=list, max_length=30)
    missing_information: list[str] = Field(default_factory=list, max_length=30)


class PolicyAuditItem(BaseModel):
    control_id: str = Field(max_length=30)
    description: str = Field(max_length=2000)
    quote: str | None = Field(None, max_length=1000)


class PolicyAuditOutput(BaseModel):
    findings: list[PolicyAuditItem] = Field(default_factory=list, max_length=15)


class MappingSuggestion(BaseModel):
    control_id: str = Field(max_length=30)
    rationale: str = Field(max_length=1000)
    confidence: str = Field(pattern="^(low|medium|high)$")


class MappingSuggestOutput(BaseModel):
    suggestions: list[MappingSuggestion] = Field(default_factory=list, max_length=5)


class CoverageRefineItem(BaseModel):
    requirement_id: str
    status: str = Field(pattern="^(met|partial|missing)$")
    quote: str = ""
    rationale: str = ""


class CoverageRefineOutput(BaseModel):
    items: list[CoverageRefineItem]


class CoverageBatchItem(BaseModel):
    control_id: str
    requirement_id: str
    status: str = Field(pattern="^(met|partial|missing)$")
    quote: str = ""
    section: str = ""
    rationale: str = ""
    suggestion: str = ""


class CoverageBatchOutput(BaseModel):
    items: list[CoverageBatchItem]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvSource(_Strict):
    id: str
    verdict: Literal["supports", "contradicts", "does_not_establish"]
    reason: str
    quote: str = ""


class EvConflict(_Strict):
    ids: list[str]
    reason: str


class CorrRank(_Strict):
    asset_id: str
    confidence: float
    explanation: str
    identifiers: list[str] = []


class CorrelationRankOutput(_Strict):
    ranking: list[CorrRank]
    summary: str


class DiscRank(_Strict):
    record_id: str
    score: float
    reason: str


class DiscrepancyExplainOutput(_Strict):
    explanation: str
    ranking: list[DiscRank] = []
    refs: list[str] = []


class EvidenceAnalysisOutput(_Strict):
    """No compliance_status / tested_by / date_tested fields exist; extra keys fail validation."""
    sources: list[EvSource]
    missing: list[str] = []
    stale: list[str] = []
    conflicts: list[EvConflict] = []
    unsupported: list[str] = []
    explanation: str
    explanation_refs: list[str] = []


class EmassFieldSuggestion(_Strict):
    field: str = Field(max_length=40)
    value: str = Field(max_length=4000)
    reason: str = Field(max_length=600)


class EmassFieldsSuggestOutput(_Strict):
    """No compliance_status / test result keys exist; extra keys fail validation."""
    suggestions: list[EmassFieldSuggestion] = Field(default_factory=list, max_length=25)


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    system: str
    user_template: str
    output_model: type[BaseModel]
    max_tokens: int = 300
    reasoning_effort: str | None = None

    def render(self, **variables: str) -> str:
        return self.user_template.format(**variables)


PROMPTS: dict[tuple[str, str], PromptTemplate] = {
    ("inventory.correlation_rank", "1.0.0"): PromptTemplate(
        "inventory.correlation_rank", "1.0.0",
        "You help an ISSO decide which inventory asset a scanned host (STIG checklist / ACAS scan) belongs to. Use ONLY the supplied observed facts and "
        "candidate assets. Rank the candidates by how likely they are the same machine, with a confidence between 0 and 1, a one-sentence explanation and the "
        "identifier kinds (hostname, fqdn, ip, mac, serial) that support it. Shared or re-used IPs are weak evidence. You never link assets and never create "
        "assets or findings – a human confirms. Reference candidates ONLY by their exact asset_id. "
        "Return ONLY JSON: {\"ranking\": [{\"asset_id\": str, \"confidence\": number, \"explanation\": str, \"identifiers\": [str]}], \"summary\": str}.",
        "Observed host facts (JSON):\n{observed}\n\nCandidate inventory assets (JSON):\n{candidates}",
        CorrelationRankOutput, 1200),
    ("inventory.discrepancy_explain", "1.0.0"): PromptTemplate(
        "inventory.discrepancy_explain", "1.0.0",
        "You explain one hardware/software inventory discrepancy to an ISSO in plain language (max 80 words), using ONLY the supplied records. "
        "If records may be duplicates, rank them (score 0-1) with a reason. Reference records ONLY by their exact id. You never change inventory data. "
        "Return ONLY JSON: {\"explanation\": str, \"ranking\": [{\"record_id\": str, \"score\": number, \"reason\": str}], \"refs\": [id]}.",
        "Discrepancy: {title}\nDeterministic recommendation: {recommendation}\nRecords (JSON):\n{records}",
        DiscrepancyExplainOutput, 900),
    ("tr.evidence_analysis", "1.1.0"): PromptTemplate(
        "tr.evidence_analysis", "1.1.0",
        "You review the evidence bundle for ONE eMASS Test Result row (one NIST SP 800-53 control / DISA CCI). Use ONLY the supplied records. "
        "For every record decide whether it supports, contradicts or does_not_establish that the CCI is implemented, with a one-sentence reason. "
        "A quote, if given, MUST be an exact contiguous substring of that record's text. Reference records ONLY by their exact \"id\". "
        "Report missing evidence, stale evidence ids, conflicts (ids + reason) and unsupported conclusions. Policy text cannot prove technical implementation. "
        "Write a factual Test Results explanation (max 120 words) for an eMASS reviewer, describing the records by what they are (e.g. STIG V-number and state, policy title) – "
        "never put record ids in the explanation; list the ids you relied on in explanation_refs. You do NOT decide Compliance Status, tester or test date. "
        "Return ONLY JSON: {\"sources\": [{\"id\": str, \"verdict\": \"supports\"|\"contradicts\"|\"does_not_establish\", \"reason\": str, \"quote\": str}], "
        "\"missing\": [str], \"stale\": [id], \"conflicts\": [{\"ids\": [id], \"reason\": str}], \"unsupported\": [str], "
        "\"explanation\": str, \"explanation_refs\": [id]}.",
        "Control: {control}\nCCI: {cci}\nRecords (JSON):\n{records}",
        EvidenceAnalysisOutput, 2500),
    ("control.emass_fields_suggest", "1.0.0"): PromptTemplate(
        "control.emass_fields_suggest", "1.0.0",
        "You suggest eMASS Implementation Plan and Risk Assessment field values for ONE NIST SP 800-53 control of ONE system (SYNTHETIC demo data). "
        "Use ONLY the supplied records (categorization, inheritance, evidence, open findings, POA&Ms, policies, people). Never invent tools, people, "
        "dates or evidence. Each suggestion gets a short reason (max 30 words) naming the records it is based on. Enumerated fields MUST use one of the "
        "listed values exactly. Dates are YYYY-MM-DD. Free-text fields: plain text, max 400 characters. You do NOT set compliance status, test results, "
        "assessment results or approvals; a human reviews and saves every value. Only suggest the requested fields. "
        "Return ONLY JSON: {\"suggestions\": [{\"field\": str, \"value\": str, \"reason\": str}]}.",
        "Implementation Status: {status}\nFields to suggest: {fields}\nAllowed values (JSON): {enums}\nRecords (JSON):\n{context}",
        EmassFieldsSuggestOutput, 2500),
    ("policy.coverage_refine", "1.0.0"): PromptTemplate(
        "policy.coverage_refine", "1.0.0",
        "You assess whether an organizational policy document addresses each NIST SP 800-53A assessment objective / DISA CCI of one control. "
        "A requirement is MET only if the policy explicitly states it, including any organization-defined value it asks for. "
        "Policy text cannot prove technical implementation; judge only whether the policy states the requirement. "
        "For MET or PARTIAL you MUST copy an exact, contiguous quote from the policy (no paraphrase). If unsure, answer missing. "
        "Return ONLY JSON: {\"items\": [{\"requirement_id\": str, \"status\": \"met\"|\"partial\"|\"missing\", \"quote\": str, \"rationale\": str}]}.",
        "Control: {control_id}\nRequirements (with the deterministic result):\n{requirements}\n\nPolicy text:\n<<<\n{policy}\n>>>",
        CoverageRefineOutput, 3000),
    ("policy.coverage_refine", "2.0.0"): PromptTemplate(
        "policy.coverage_refine", "2.0.0",
        "You assess whether an organizational policy addresses each listed NIST SP 800-53A assessment objective / DISA CCI. "
        "You see only the policy SECTIONS retrieved for these requirements, each labelled [S<n> | heading | page]. "
        "A requirement is MET only if a section explicitly states it, including any organization-defined value it asks for; PARTIAL if it is "
        "stated without the required value/scope; otherwise MISSING. Policy text cannot prove technical implementation. "
        "For MET or PARTIAL copy an exact, contiguous quote (no paraphrase) and give its section label (e.g. S3). If unsure, answer missing. "
        "Answer EVERY listed requirement exactly once. rationale: one plain sentence, max 25 words, naming what is stated or missing. "
        "Return ONLY JSON: {\"items\": [{\"control_id\": str, \"requirement_id\": str, \"status\": \"met\"|\"partial\"|\"missing\", "
        "\"quote\": str, \"section\": str, \"rationale\": str}]}.",
        "Requirements (JSON, with the deterministic result):\n{requirements}\n\nRetrieved policy sections:\n<<<\n{sections}\n>>>",
        CoverageBatchOutput, 6000),
    ("policy.coverage_refine", "2.1.0"): PromptTemplate(
        "policy.coverage_refine", "2.1.0",
        "You assess whether an organizational policy addresses each listed NIST SP 800-53A assessment objective / DISA CCI. "
        "You see only the policy SECTIONS retrieved for these requirements, each labelled [S<n> | heading | page]. "
        "A requirement is MET only if a section explicitly states it, including any organization-defined value it asks for; PARTIAL if it is "
        "stated without the required value/scope; otherwise MISSING. Policy text cannot prove technical implementation. "
        "For MET or PARTIAL copy an exact, contiguous quote of at most 40 words (no paraphrase) and give its section label (e.g. S3); for MISSING leave quote empty. If unsure, answer missing. "
        "Answer EVERY listed requirement exactly once. rationale: one plain sentence, max 15 words, naming what is stated or missing. "
        "Return ONLY JSON: {\"items\": [{\"control_id\": str, \"requirement_id\": str, \"status\": \"met\"|\"partial\"|\"missing\", "
        "\"quote\": str, \"section\": str, \"rationale\": str}]}.",
        "Requirements (JSON, with the deterministic result):\n{requirements}\n\nRetrieved policy sections:\n<<<\n{sections}\n>>>",
        CoverageBatchOutput, 6000),
    ("policy.coverage_refine", "2.2.0"): PromptTemplate(
        "policy.coverage_refine", "2.2.0",
        "You assess whether an organizational policy addresses each listed NIST SP 800-53A assessment objective / DISA CCI. "
        "You see only the policy SECTIONS retrieved for these requirements, each labelled [S<n> | heading | page]. "
        "A requirement is MET only if a section explicitly states it, including any organization-defined value it asks for; PARTIAL if it is "
        "stated without the required value/scope; otherwise MISSING. Policy text cannot prove technical implementation. "
        "For MET or PARTIAL copy an exact, contiguous quote of at most 40 words (no paraphrase) and give its section label (e.g. S3); for MISSING leave quote empty. If unsure, answer missing. "
        "Answer EVERY listed requirement exactly once. rationale: one plain sentence, max 15 words, naming what is stated or missing. "
        "suggestion: for PARTIAL or MISSING only, ONE complete grammatical policy sentence (max 35 words, using 'shall') that would meet the "
        "requirement, in the policy's own terms; write any value the organization must choose as [organization-defined <name>]; empty for MET. "
        "Return ONLY JSON: {\"items\": [{\"control_id\": str, \"requirement_id\": str, \"status\": \"met\"|\"partial\"|\"missing\", "
        "\"quote\": str, \"section\": str, \"rationale\": str, \"suggestion\": str}]}.",
        "Requirements (JSON, with the deterministic result):\n{requirements}\n\nRetrieved policy sections:\n<<<\n{sections}\n>>>",
        CoverageBatchOutput, 6000),
    ("mapping.suggest", "1.0.0"): PromptTemplate(
        prompt_id="mapping.suggest", version="1.0.0",
        system=("You map security findings to NIST SP 800-53 Rev 5 controls. Respond ONLY with one JSON object, no markdown. "
                "Suggest at most 3 controls. Use lowercase OSCAL ids such as ac-2, ac-2.3, sc-13."),
        user_template=('Finding title: {title}\nSource: {source}\nRule/plugin: {rule}\nCVEs: {cves}\nCCIs: {ccis}\n'
                       'Return {{"suggestions": [{{"control_id": "...", "rationale": "...", "confidence": "low|medium|high"}}]}}'),
        output_model=MappingSuggestOutput, max_tokens=600),
    ("ai.health_check", "1.0.0"): PromptTemplate(
        prompt_id="ai.health_check",
        version="1.0.0",
        system=(
            "You are the AegisRMF connectivity probe. Respond ONLY with a single JSON object, "
            "no markdown, no code fences."
        ),
        user_template=(
            'Return exactly this JSON shape: {{"status": "ok", "nonce": "{nonce}", '
            '"summary": "<one sentence (max 25 words) describing NIST RMF>"}}'
        ),
        output_model=HealthCheckOutput,
    ),
    ("control.implementation_statement", "1.0.0"): PromptTemplate(
        prompt_id="control.implementation_statement",
        version="1.0.0",
        system=(
            "You draft NIST SP 800-53 Rev 5 control implementation statements for a federal RMF package (SYNTHETIC demo data). "
            "Use ONLY the supplied context. Never invent tools, configurations, dates or evidence. Every factual claim about the "
            "system must cite an evidence_id from context.evidence. Passing technical checks do not prove compliance; say what the "
            "evidence shows. Separate verified facts (directly supported by cited evidence) from interpretation. List missing "
            "information honestly. Respond ONLY with one JSON object, no markdown."
        ),
        user_template=(
            "Context (JSON):\n{context}\n\nReturn JSON with keys: "
            '{{"narrative": "<implementation statement, 80-200 words, third person, summarize hosts by count (do not list every host), cite evidence as [EV:<evidence_id>]>", '
            '"citations": ["<evidence_id>", ...], "verified_facts": ["..."], "interpretation": ["..."], '
            '"suggested_actions": ["..."], "missing_information": ["..."]}}. Each list: at most 5 items, each under 25 words.'
        ),
        output_model=ImplementationStatementOutput,
        max_tokens=4000,
    ),
    ("policy.audit", "1.0.0"): PromptTemplate(
        prompt_id="policy.audit",
        version="1.0.0",
        system=("You review an organizational security policy (SYNTHETIC demo) against NIST SP 800-53 Rev 5. Identify requirements that are vague, "
                "contradictory, or missing. NIST organization-defined parameters have NO universal threshold – never claim a value is wrong by "
                "itself. Use Rev 5 control IDs like ac-2.3 or ac-17. Respond ONLY with JSON."),
        user_template=("Policy text:\n{text}\n\nReturn {{\"findings\": [{{\"control_id\": \"ac-17\", \"description\": \"...\", "
                       "\"quote\": \"<short exact quote or null>\"}}]}} with at most 8 findings, each description under 40 words."),
        output_model=PolicyAuditOutput,
        max_tokens=2500,
    ),
    ("policy.audit", "1.1.0"): PromptTemplate(
        prompt_id="policy.audit",
        version="1.1.0",
        system=("You review an organizational security policy (SYNTHETIC demo) against NIST SP 800-53 Rev 5. Identify requirements of the controls "
                "THIS policy addresses that are vague, contradictory, or missing. Only report on control families the policy itself declares or "
                "clearly implements – never report controls from other families (a policy that does not mention a topic is not deficient for it). "
                "Controls the policy states are not selected, withdrawn, or inherited are not gaps – skip them. NIST organization-defined "
                "parameters have NO universal threshold – never claim a value is wrong by itself. Respond ONLY with JSON."),
        user_template=("Policy text:\n{text}\n\nReturn {{\"findings\": [{{\"control_id\": \"<Rev 5 control ID addressed by this policy, e.g. xx-1 or xx-2.3>\", "
                       "\"description\": \"...\", \"quote\": \"<short exact quote from the policy, or null>\"}}]}} with at most 8 findings, "
                       "each description under 40 words."),
        output_model=PolicyAuditOutput,
        max_tokens=4000,
        reasoning_effort="low",  # 1.0.0/first 1.1.0 runs: ~3.9k of the 4k budget went to hidden reasoning → "reply cut off"
    ),
}


def get_prompt(prompt_id: str, version: str) -> PromptTemplate:
    try:
        return PROMPTS[(prompt_id, version)]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt {prompt_id}@{version}") from exc
