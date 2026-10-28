# 6 · Workflow diagrams

## Standard flows
```mermaid
flowchart LR
  subgraph Import
    U[Upload any file] --> D{Detect type} --> P[Preview: counts, conflicts, warnings] --> I[Import: audited, revertible] --> C[Completed: where it went + next action]
  end
  subgraph Analyze
    U2[Upload policy / scan] --> A[Analyze: AI suggests, deterministic fallback] --> R[Review findings] --> AC[Approve / Correct / Reject - human only]
  end
  subgraph Assess
    S[Select control from SCA queue] --> E[Review evidence + implementation + historical eMASS results] --> DET[Record determination] --> SV[Save and next control]
  end
  subgraph Documents
    G[Generate SSP] --> V[Review validation - each issue links to its field] --> DL[Download DOCX / PDF / OSCAL]
  end
```

## Connected system authorization record
```mermaid
flowchart TB
  REC[(System authorization record - one per system, tenant-scoped)]
  REG[Register: name, acronym, owner] --> REC
  CAT[Categorize: info types, PII, AO approval] --> REC
  REC -- categorization changed --> BR[Select: baseline review notice]
  SEL[Select: baseline, tailoring, ISCM strategy] --> REC
  IMP[eMASS Implementation Plan import] --> WB[Workbench: status + statements] --> REC
  SLCM[SLCM import] --> STRAT[Strategy draft -> ISSM approval] --> SCHED[Monitor schedules] --> REC
  POL[Policy upload] --> MAP[Mapping suggestions] -- approved --> COV[Policy coverage only] --> REC
  ACAS[ACAS / Nessus / STIG] --> FIND[Findings] --> AST[Assets]
  FIND --> POAM[POA&M] --> REC
  TR[eMASS Test Results - historical] --> SCAQ[SCA queue]
  EVD[Evidence] --> WB & SCAQ & FIND
  SCAQ --> DETS[SCA determinations] --> REC
  REC --> READY[Package readiness - live blockers] --> PKG[SSP / SAR / RAR / POA&M package] --> AO[AO decision] --> REC
```

The arrows that are missing or partial today are listed in `CONNECTEDNESS.md`. The backlog in `BACKLOG.md` closes them:
- TR → SCA queue
- ACAS → POA&M suggestion
- readiness meter
- import next action
