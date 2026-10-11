from dataclasses import dataclass

from pydantic import BaseModel, Field


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


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    system: str
    user_template: str
    output_model: type[BaseModel]
    max_tokens: int = 300

    def render(self, **variables: str) -> str:
        return self.user_template.format(**variables)


PROMPTS: dict[tuple[str, str], PromptTemplate] = {
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
}


def get_prompt(prompt_id: str, version: str) -> PromptTemplate:
    try:
        return PROMPTS[(prompt_id, version)]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt {prompt_id}@{version}") from exc
