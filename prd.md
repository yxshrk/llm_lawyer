# LexAgent — Product Requirements Document
**AI-Powered eDiscovery & Litigation Prep | v0.6 | April 2026**
**Status:** Final — Ready for Development

---

## 1. Overview

**Problem:** Solo and small firm lawyers spend dozens of hours manually reviewing documents for eDiscovery — sorting relevant from irrelevant, flagging privileged content for redaction, and prepping for court challenges. This is slow, expensive, and error-prone.

**Solution:** LexAgent is an agentic document intelligence tool that automates the eDiscovery pipeline — so lawyers can focus on strategy, not grunt work.

**Target User:** Solo practitioners and small firm lawyers handling civil litigation.

---

## 2. Problem Statement

In litigation, the eDiscovery phase requires lawyers to:

- Review thousands of documents to determine relevancy
- Identify and redact privileged, trade secret, or sensitive content
- Defend redaction decisions to judges and opposing counsel
- Build case chronologies for brief preparation

All of this is done manually today. For small firms without paralegal armies, it's a massive bottleneck.

---

## 3. Core Workflow

### Own Document Pipeline
```
Lawyer opens a new matter (names it, gets a matter ID)
        ↓
Lawyer uploads client documents (bulk PDF) or client uploads their own data
        ↓
Lawyer reviews what they have → writes the Case Context Memo
        ↓
AI uses memo to filter: relevant / irrelevant / uncertain
        ↓
Redaction Engine scans relevant docs + suggests redactions
        ↓
Lawyer reviews suggestions + approves ("are you sure?" confirmation)
        ↓
Every decision logged to audit trail
        ↓
Lawyer triggers Q&A Challenge Set (on demand)
        ↓
AI simulates judge / opposing counsel — generates adversarial 
challenges + suggested answers per redaction
        ↓
Lawyer identifies weak redactions → goes back and revises
        ↓
Repeat until satisfied
        ↓
Redaction set is truly finalised → ready for production
```

### Opposing Counsel Pipeline
```
Lawyer uploads opposing counsel's produced documents (separate from own docs)
        ↓
AI reviews their redactions → generates challenges with legal basis
        ↓
AI scans their production for argument + evidence gaps
        ↓
Lawyer receives: redaction challenges + gap analysis report
```

---

## 4. Features

### 4.1 Authentication & Matter Management

- Lawyers must create an account and log in before accessing any matter
- Each matter has a unique matter ID — all case context, documents, and decisions are scoped to that matter ID
- A lawyer can only access their own matters
- Session must time out after a period of inactivity (duration TBD)

### 4.2 Document Ingestion

- Lawyer uploads client documents in bulk PDF format after creating the matter
- System must handle both **native text PDFs** and **scanned/OCR'd PDFs**
  - Native text PDFs: process directly
  - Scanned PDFs: run OCR before processing; flag to lawyer if OCR quality is low
- Maximum file size per upload: TBD — must be defined before dev starts
- After upload, the lawyer is prompted to complete the Case Context Memo before AI processing begins
- Opposing counsel's produced documents are uploaded separately — clearly labelled and kept distinct from the lawyer's own document set

### 4.3 Case Context Memo

The Case Context Memo is the lawyer's briefing document for the AI. The lawyer writes it **after uploading documents** — once they've seen what they're working with. It tells every downstream AI stage what to look for, what matters, and what rules apply. It persists for the life of the matter.

The Case Context Memo must capture the following fields:

| Field | Description | Required? |
|---|---|---|
| Matter name | Short label for the case | Yes |
| Case summary | Plain-English description of what the case is about (2–5 sentences) | Yes |
| Parties | Names of all parties — client, opposing party, key third parties | Yes |
| Jurisdiction | Federal or state; if state, which state | Yes |
| Key legal issues | The primary claims or defences at play (e.g. breach of contract, trade secret misappropriation) | Yes |
| Privilege rules | Any specific privilege agreements or standing orders that apply | No |
| Key custodians | Names of individuals whose documents are most likely relevant | No |
| Key date range | Time period the case centres on | No |
| Custom rules | Any additional instructions for the AI (e.g. "flag all emails mentioning Project X") | No |

- The Case Context Memo is editable at any time — changes persist immediately and apply to all subsequent AI calls
- Edits to the Case Context Memo are logged in the audit trail
- The AI must use the Case Context Memo as the primary input for relevancy filtering, redaction categorisation, Q&A generation, and opposing counsel analysis
- If the Case Context Memo is incomplete (missing required fields), the system must block AI processing and prompt the lawyer to complete it

### 4.4 Relevancy Filtering

- AI classifies each document as: **Relevant / Irrelevant / Uncertain**
- Shows plain-English reasoning per classification
- Uncertain documents flagged for mandatory manual review — lawyer must make final call
- Irrelevant documents excluded from redaction pipeline

### 4.5 Redaction Engine

- Scans relevant documents for: attorney-client privilege, trade secrets, PII, other sensitive content
- Suggests specific redactions with highlighted passages
- Each redaction suggestion includes:
  - Category (e.g. attorney-client privilege, trade secret, PII)
  - Confidence score (low / medium / high)
  - Plain-English reasoning
- Lawyer reviews each suggestion in a queue
- "Are you sure?" confirmation required before finalising any redaction — this is the lawyer's legally meaningful sign-off, not just a UX speed bump
- Lawyer can reject any suggestion or add manual redactions the AI missed

### 4.6 Q&A Challenge Set

The Q&A Challenge Set is a rehearsal tool — not the end of the workflow. The lawyer triggers it when they think they're done with redactions. The AI then plays adversary — simulating the questions a judge or opposing counsel would ask about each redaction in court. The lawyer uses this to find and fix weak redactions *before* production, not after.

This is an **iterative loop**, not a one-way step:

```
Trigger Q&A → Review challenges → Fix weak redactions → 
Trigger Q&A again → Repeat until satisfied → Finalise
```

**Trigger:**
- Lawyer manually triggers the Q&A Challenge Set from the matter dashboard
- The system must not auto-generate Q&A — it runs only when the lawyer decides they are ready
- The lawyer can re-trigger Q&A as many times as needed after revising redactions

**What gets challenged:**
- Every approved redaction is included in the Q&A set
- Low confidence redactions receive harder, more aggressive questions than high confidence ones
- Inconsistent redactions (similar passages treated differently) are flagged as a priority challenge at the top of the set

**Output format per redaction:**

| Field | Description |
|---|---|
| Redacted passage | The specific text that was redacted |
| Redaction category | e.g. attorney-client privilege, trade secret |
| Confidence score | Low / Medium / High |
| Challenge question | The adversarial question a judge or opposing counsel would ask |
| Suggested answer | A plain-English answer the lawyer can use or adapt in court |
| Legal basis | The specific privilege doctrine or case law supporting the redaction |
| Risk flag | For low confidence redactions: plain-English warning about why this redaction is vulnerable |

**Consistency check:**
- Before generating questions, the AI scans all approved redactions for inconsistencies
- Inconsistencies are surfaced at the top of the Q&A set as: "Potential Inconsistencies — Review Before Production"

**Lawyer actions:**
- Lawyer can mark each entry as: **Prepared** / **Needs Work** / **Will Revise Redaction**
- Selecting "Will Revise Redaction" takes the lawyer back to that specific redaction in the review queue
- After revising, the lawyer can re-trigger the Q&A — the AI re-challenges only the revised redactions
- Q&A entries and lawyer notes are saved to the matter and logged in the audit trail

### 4.7 Opposing Counsel Review

The Opposing Counsel Review runs on the documents produced *by* opposing counsel — a completely separate pipeline from the lawyer's own documents. The goal is to find holes in the other side's production: bad redactions they made, arguments they haven't addressed, and evidence gaps the lawyer can exploit.

This feature is triggered on demand after the lawyer uploads opposing counsel's produced documents.

---

**4.7.1 Redaction Challenge Generator**

The AI reviews opposing counsel's redactions and generates legal challenges the lawyer can use to contest them.

Output per challenged redaction:

| Field | Description |
|---|---|
| Redacted passage (if visible) | The surrounding context around the redaction |
| Stated redaction category | What privilege they claimed |
| Challenge | The specific legal argument for why the redaction is improper |
| Legal basis | The doctrine or case law that supports the challenge (e.g. "Privilege waived — third party CC'd on email chain") |
| Strength | Strong / Moderate / Speculative |
| Recommended action | e.g. "File motion to compel", "Request privilege log entry", "Flag for deposition" |

The AI must specifically look for:
- Redactions where privilege is likely waived (third parties on communications, non-legal subject matter, etc.)
- Overbroad redactions where only part of the passage is privileged
- Inconsistent redactions — similar content produced unredacted elsewhere in their production
- Redactions with no plausible legal basis given the case context

---

**4.7.2 Argument Gap Finder**

The AI reviews the full set of opposing counsel's produced documents and identifies what claims, arguments, or evidence appear to be missing — gaps the lawyer can exploit at deposition, in motions, or at trial.

Output:

| Field | Description |
|---|---|
| Expected topic | What the lawyer would expect to see given the case context |
| Gap description | What is absent from the production |
| Significance | Why this matters to the case |
| Recommended action | e.g. "Serve targeted document request", "Raise at deposition", "Include in spoliation argument" |

The AI must use the Case Context Memo (key legal issues, parties, date range) to determine what a complete production should look like — gaps are assessed relative to what the case requires, not in the abstract.

---

**General rules for Opposing Counsel Review:**
- Opposing counsel's documents are stored and processed separately from the lawyer's own documents — they must never be mixed in the same pipeline
- The lawyer must explicitly label an upload as "Opposing Counsel Production" at the time of upload
- All Opposing Counsel Review outputs are saved to the matter and logged in the audit trail
- The lawyer can export the Redaction Challenge report and Gap Analysis report as PDF for use in motion practice

### 4.8 Audit Trail

- Every action in the system must be logged automatically, including:
  - Document upload (timestamp, filename, uploader, document type: own / opposing counsel)
  - Case Context Memo creation and any edits (timestamp)
  - Relevancy classification (AI decision + reasoning, timestamp)
  - Redaction suggestion (AI suggestion + confidence + reasoning, timestamp)
  - Lawyer approval or rejection of each suggestion (timestamp, lawyer ID)
  - Manual redactions added by lawyer (timestamp, lawyer ID)
  - Q&A Challenge Set triggered (timestamp)
  - Lawyer's Q&A responses and notes (timestamp)
  - Redactions revised after Q&A (timestamp, what changed)
  - Opposing Counsel Review triggered and outputs generated (timestamp)
  - Final redaction set confirmation (timestamp, lawyer ID)
- Audit log must be viewable by the lawyer at any time
- Audit log must be exportable as PDF or CSV for court submission
- Audit log cannot be edited or deleted by the lawyer

### 4.9 Data Privacy & Document Handling

- Client documents are stored encrypted at rest and in transit
- Documents are stored only for the duration of the matter — retention policy TBD
- Client documents are **never** used to train or fine-tune AI models
- No document content is shared with third parties
- Lawyer must be shown a clear data handling disclosure before uploading documents for the first time

---

## 5. User Stories

- As a lawyer, I want to upload my client's documents and instantly know which are relevant to my case
- As a lawyer, I want to brief the AI on my case once — after I've seen the documents — and have it remember everything for the life of the matter
- As a lawyer, I want AI to flag what needs redacting and tell me why, so I can review rather than find
- As a lawyer, I want to see the adversarial questions opposing counsel would ask about my redactions, so I can prepare before it matters
- As a lawyer, I want the AI to tell me which of my redactions are inconsistent with each other, before opposing counsel does
- As a lawyer, I want to upload opposing counsel's production and get a list of their bad redactions I can challenge in court
- As a lawyer, I want to know what arguments and evidence are missing from opposing counsel's production, so I know where to push
- As a lawyer, I want every decision I make to be logged so I can defend my process in court
- As a lawyer, I want to know my clients' documents are stored securely and never used to train AI

---

## 6. Non-Goals (Out of Scope for MVP)

- Court prep simulation (Judge / Opposing Counsel / Special Master personas) — post-MVP
- Privilege log generation — post-MVP (flagged as high priority for v2)
- Inadvertent production / clawback workflow — post-MVP
- Chronology extraction
- Multi-user / law firm collaboration
- Integration with existing eDiscovery platforms (Relativity, DISCO)
- Actual document production / export to opposing counsel
- Billing / matter management
- Multi-language document support

---

## 7. Error Handling

The system must handle the following failure states gracefully:

| Error | What the UI must show |
|---|---|
| AI call fails or times out | "Something went wrong — please try again. Your documents are safe." + retry button |
| OCR quality too low to process | "This document may be a low-quality scan. Results may be inaccurate — please review carefully." |
| File upload fails | "Upload failed. Please check the file and try again." with specific file flagged |
| File type not supported | "Only PDF files are supported at this time." |
| Session timeout | Lawyer is returned to login screen with "Your session expired. Please log in again." — no data lost |
| AI returns no redaction suggestions | "No redaction candidates found in this document." — not treated as an error, shown as a result |
| Q&A generation fails | "Could not generate challenge questions. Please try again." — redactions are unaffected |
| Q&A triggered with no approved redactions | "No finalised redactions found. Please complete your redaction review before generating challenge questions." |

---

## 8. Technical Notes

- RAG over uploaded PDFs for all AI features
- Separate LLM system prompts per pipeline stage: relevancy filter, redaction engine, Q&A challenge generator, opposing counsel redaction challenger, opposing counsel gap finder
- Q&A Challenge Set prompt must be explicitly adversarial — simulate a judge or opposing counsel, not a neutral reviewer
- Opposing Counsel Review prompts must be scoped to the Case Context Memo — gaps are assessed relative to what the case requires, not in the abstract
- Case Context Memo passed as system-level context to every AI call in the pipeline
- Own documents and opposing counsel documents stored and processed in completely separate pipelines — must never be mixed
- Confidence scoring via LLM self-evaluation
- Persistent memory: case context, Q&A notes, and opposing counsel analysis stored per matter ID in database
- OCR pipeline required for scanned PDFs — library TBD
- All AI outputs must be structured (JSON) for reliable frontend rendering
- Stack: TBD — must be decided before development starts

---

## 9. Success Metrics

| Metric | Target |
|---|---|
| Time to first redaction suggestion | < 60 seconds after upload |
| Redaction Engine accuracy | Lawyer agrees with AI suggestion > 70% of the time |
| Q&A usefulness | Lawyer marks > 60% of Q&A entries as "Prepared" without revising the redaction |
| Q&A consistency catch rate | AI catches > 80% of inconsistent redactions that lawyer later agrees are inconsistent |
| Audit trail completeness | 100% of lawyer decisions logged with no gaps |
| Data privacy | Zero client documents used in model training |
| Lawyer review time reduction | > 25% faster than manual review baseline |

---

## 10. Open Questions

These must be resolved before or during development:

1. **Maximum file size / batch size:** What is the upload limit per document and per batch? Needs a decision before dev starts.
2. **Session timeout duration:** How long before an inactive session expires?
3. **Document retention policy:** How long are client documents stored after a matter is closed?
4. **Privilege log generation:** High priority for v2 — required under FRCP 26(b)(5) for federal litigation. Should be scoped into the next sprint after MVP.
5. **Jurisdiction-specific privilege rules:** Does the AI adapt its privilege evaluation based on the jurisdiction the lawyer sets in case context? Not in MVP but needs a design decision early.
6. **Inadvertent production / clawback:** If a lawyer accidentally produces a privileged document, what is the workflow? Not in MVP but must be flagged to users.
7. **Vendor liability model:** What is LexAgent's legal position if an AI error causes a privilege waiver? Needs legal review before public launch.
8. **Ethics compliance:** Has the tool been reviewed against ABA Formal Opinion 512 and applicable state bar AI guidance? Required before marketing to lawyers.
9. **Stack decision:** "TBD" is a blocker for the junior developer — must be decided immediately.
10. **Clawback workflow:** Post-MVP but needs to be in the roadmap — lawyers need to know it's coming.
