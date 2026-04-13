# LexAgent — Product Requirements Document
**AI-Powered eDiscovery & Litigation Prep | v0.7 | April 2026**
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

## 3. System Architecture — Three Pipelines

LexAgent operates as three distinct pipelines. Each is independent, uses separate document sets, and serves a different strategic purpose.

```
┌─────────────────────────────────────────────────────────────────┐
│  PIPELINE 1 — Own Document Redaction                            │
│  Ingest client docs → filter relevancy → suggest redactions     │
│  → lawyer review & sign-off → audit trail                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │  Draft redaction set ready
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PIPELINE 2 — Defense Q&A (Iterative Loop)                      │
│  Lawyer triggers → AI simulates judge & opposing counsel →      │
│  challenges every redaction → lawyer fixes weak ones →          │
│  re-trigger → repeat until satisfied → finalise                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PIPELINE 3 — Offense Q&A on Opposing Counsel's Production      │
│  Lawyer uploads their docs → AI challenges their redactions +   │
│  finds argument/evidence gaps → lawyer gets attack report       │
└─────────────────────────────────────────────────────────────────┘
```

Pipelines 1 and 2 are sequential — Pipeline 2 runs on the output of Pipeline 1. Pipeline 3 is fully independent and runs on a separate document set.

---

## 4. Authentication & Matter Management

- Lawyers must create an account and log in before accessing any matter
- Each matter has a unique matter ID — all case context, documents, and decisions are scoped to that matter ID
- A lawyer can only access their own matters
- Session must time out after a period of inactivity (duration TBD)

---

## 5. Pipeline 1 — Own Document Redaction

### 5.1 Document Ingestion

- Lawyer uploads client documents in bulk PDF format after creating the matter
- System must handle both **native text PDFs** and **scanned/OCR'd PDFs**
  - Native text PDFs: process directly
  - Scanned PDFs: run OCR before processing; flag to lawyer if OCR quality is low
- Maximum file size per upload: TBD — must be defined before dev starts
- After upload, the lawyer is prompted to complete the Case Context Memo before AI processing begins

### 5.2 Case Context Memo

The Case Context Memo is the lawyer's briefing document for the AI. Written after uploading documents — once the lawyer has seen what they're working with. It drives every downstream AI stage: what to look for, what matters, what rules apply. It persists for the life of the matter.

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

- Editable at any time — changes persist immediately and apply to all subsequent AI calls
- Edits are logged in the audit trail
- Missing required fields block AI processing until complete
- Passed as system-level context to every AI call across all three pipelines

### 5.3 Relevancy Filtering

- AI classifies each document as: **Relevant / Irrelevant / Uncertain**
- Shows plain-English reasoning per classification
- Uncertain documents flagged for mandatory manual review — lawyer must make final call
- Irrelevant documents excluded from the redaction pipeline

### 5.4 Redaction Engine

- Scans relevant documents for: attorney-client privilege, trade secrets, PII, other sensitive content
- Suggests specific redactions with highlighted passages
- Each redaction suggestion includes:
  - Category (e.g. attorney-client privilege, trade secret, PII)
  - Confidence score (low / medium / high)
  - Plain-English reasoning
- Lawyer reviews each suggestion in a queue
- "Are you sure?" confirmation required before finalising any redaction — this is the lawyer's legally meaningful sign-off, not just a UX speed bump
- Lawyer can reject any suggestion or add manual redactions the AI missed

**Pipeline 1 output:** A draft redaction set — all approved redactions, ready to be stress-tested in Pipeline 2.

---

## 6. Pipeline 2 — Defense Q&A (Iterative Loop)

The Q&A Challenge Set is a rehearsal tool that stress-tests the lawyer's redactions before production. The AI plays adversary — simulating the questions a judge or opposing counsel would ask about each redaction. The lawyer uses this to find and fix weak redactions *before* production, not after.

**This is an iterative loop, not a one-way step:**

```
Lawyer triggers Q&A
        ↓
AI challenges every approved redaction
(harder questions for low-confidence, inconsistencies flagged first)
        ↓
Lawyer reviews — marks each: Prepared / Needs Work / Will Revise
        ↓
"Will Revise" → back to redaction queue → fix it
        ↓
Re-trigger Q&A (only revised redactions re-challenged)
        ↓
Repeat until satisfied
        ↓
Lawyer finalises → ready for production
```

### 6.1 Trigger Rules

- Lawyer manually triggers Q&A from the matter dashboard — never auto-generated
- Can be re-triggered as many times as needed
- Cannot be triggered with zero approved redactions

### 6.2 Challenge Logic

- Every approved redaction is included
- Low confidence redactions receive harder, more aggressive questions
- Inconsistent redactions (similar passages treated differently) are flagged as a priority challenge at the top of the set — before standard challenges

### 6.3 Output Format

| Field | Description |
|---|---|
| Redacted passage | The specific text that was redacted |
| Redaction category | e.g. attorney-client privilege, trade secret |
| Confidence score | Low / Medium / High |
| Challenge question | The adversarial question a judge or opposing counsel would ask |
| Suggested answer | A plain-English answer the lawyer can use or adapt in court |
| Legal basis | The specific privilege doctrine or case law supporting the redaction |
| Risk flag | For low confidence: plain-English warning about why this redaction is vulnerable |

### 6.4 Lawyer Actions

- Mark each entry: **Prepared** / **Needs Work** / **Will Revise Redaction**
- "Will Revise Redaction" navigates back to that specific redaction in the review queue
- After revising, lawyer re-triggers Q&A — only revised redactions are re-challenged
- All Q&A entries and lawyer notes saved to the matter and logged in the audit trail

---

## 7. Pipeline 3 — Offense Q&A on Opposing Counsel's Production

Pipeline 3 runs on the documents produced *by* opposing counsel — completely separate from the lawyer's own documents. The goal: find holes in the other side's production. Bad redactions they made, arguments they haven't addressed, evidence gaps the lawyer can exploit.

Triggered on demand after the lawyer uploads opposing counsel's produced documents. Opposing counsel's documents are **never mixed** with the lawyer's own document set.

### 7.1 Redaction Challenge Generator

The AI reviews opposing counsel's redactions and generates legal challenges the lawyer can use to contest them.

Output per challenged redaction:

| Field | Description |
|---|---|
| Redacted passage (if visible) | The surrounding context around the redaction |
| Stated redaction category | What privilege they claimed |
| Challenge | The specific legal argument for why the redaction is improper |
| Legal basis | The doctrine or case law that supports the challenge |
| Strength | Strong / Moderate / Speculative |
| Recommended action | e.g. "File motion to compel", "Request privilege log entry", "Flag for deposition" |

The AI must specifically look for:
- Redactions where privilege is likely waived (third parties on communications, non-legal subject matter, etc.)
- Overbroad redactions where only part of the passage is privileged
- Inconsistent redactions — similar content produced unredacted elsewhere in their production
- Redactions with no plausible legal basis given the case context

### 7.2 Argument Gap Finder

The AI reviews the full set of opposing counsel's produced documents and identifies what claims, arguments, or evidence appear to be missing.

Output:

| Field | Description |
|---|---|
| Expected topic | What the lawyer would expect to see given the case context |
| Gap description | What is absent from the production |
| Significance | Why this matters to the case |
| Recommended action | e.g. "Serve targeted document request", "Raise at deposition", "Include in spoliation argument" |

Gaps are assessed relative to what the Case Context Memo says the case requires — not in the abstract.

### 7.3 Pipeline 3 Rules

- Lawyer must explicitly label an upload as "Opposing Counsel Production" at time of upload
- Opposing counsel's documents stored and processed in a completely separate pipeline from the lawyer's own documents — must never be mixed
- All outputs saved to the matter and logged in the audit trail
- Lawyer can export the Redaction Challenge report and Gap Analysis report as PDF

---

## 8. Audit Trail

Every action in the system must be logged automatically:

- Document upload (timestamp, filename, uploader, document type: own / opposing counsel)
- Case Context Memo creation and any edits (timestamp)
- Relevancy classification (AI decision + reasoning, timestamp)
- Redaction suggestion (AI suggestion + confidence + reasoning, timestamp)
- Lawyer approval or rejection of each suggestion (timestamp, lawyer ID)
- Manual redactions added by lawyer (timestamp, lawyer ID)
- Q&A triggered (timestamp)
- Lawyer's Q&A responses and notes (timestamp)
- Redactions revised after Q&A (timestamp, what changed)
- Pipeline 3 triggered and outputs generated (timestamp)
- Final redaction set confirmation (timestamp, lawyer ID)

- Audit log viewable by the lawyer at any time
- Exportable as PDF or CSV for court submission
- Cannot be edited or deleted by the lawyer

---

## 9. Data Privacy & Document Handling

- Client documents stored encrypted at rest and in transit
- Documents stored only for the duration of the matter — retention policy TBD
- Client documents **never** used to train or fine-tune AI models
- No document content shared with third parties
- Lawyer shown a clear data handling disclosure before uploading documents for the first time

---

## 10. User Stories

- As a lawyer, I want to upload my client's documents and instantly know which are relevant to my case
- As a lawyer, I want to brief the AI on my case once — after I've seen the documents — and have it remember everything for the life of the matter
- As a lawyer, I want AI to flag what needs redacting and tell me why, so I can review rather than find
- As a lawyer, I want to see the adversarial questions opposing counsel or a judge would ask about my redactions, so I can prepare before it matters
- As a lawyer, I want the AI to tell me which of my redactions are inconsistent with each other, before opposing counsel does
- As a lawyer, I want to re-trigger the challenge set after fixing weak redactions, and only have the revised ones re-challenged
- As a lawyer, I want to upload opposing counsel's production and get a list of their bad redactions I can challenge in court
- As a lawyer, I want to know what arguments and evidence are missing from opposing counsel's production, so I know where to push
- As a lawyer, I want every decision I make to be logged so I can defend my process in court
- As a lawyer, I want to know my clients' documents are stored securely and never used to train AI

---

## 11. Non-Goals (Out of Scope for MVP)

- Privilege log generation — post-MVP (flagged as high priority for v2)
- Inadvertent production / clawback workflow — post-MVP
- Chronology extraction
- Multi-user / law firm collaboration
- Integration with existing eDiscovery platforms (Relativity, DISCO)
- Actual document production / export to opposing counsel
- Billing / matter management
- Multi-language document support

---

## 12. Error Handling

| Error | What the UI must show |
|---|---|
| AI call fails or times out | "Something went wrong — please try again. Your documents are safe." + retry button |
| OCR quality too low to process | "This document may be a low-quality scan. Results may be inaccurate — please review carefully." |
| File upload fails | "Upload failed. Please check the file and try again." with specific file flagged |
| File type not supported | "Only PDF files are supported at this time." |
| Session timeout | Lawyer returned to login screen with "Your session expired. Please log in again." — no data lost |
| AI returns no redaction suggestions | "No redaction candidates found in this document." — not treated as an error, shown as a result |
| Q&A generation fails | "Could not generate challenge questions. Please try again." — redactions are unaffected |
| Q&A triggered with no approved redactions | "No finalised redactions found. Please complete your redaction review before generating challenge questions." |

---

## 13. Technical Notes

- RAG over uploaded PDFs for all AI features
- Separate LLM system prompts per pipeline stage: relevancy filter, redaction engine, Pipeline 2 Q&A challenge generator, Pipeline 3 redaction challenger, Pipeline 3 gap finder
- Pipeline 2 prompt must be explicitly adversarial — simulate a judge or opposing counsel, not a neutral reviewer
- Pipeline 3 prompts scoped to the Case Context Memo — gaps assessed relative to what the case requires, not in the abstract
- Case Context Memo passed as system-level context to every AI call across all three pipelines
- Own documents and opposing counsel documents stored and processed in completely separate pipelines — must never be mixed
- Confidence scoring via LLM self-evaluation
- Persistent memory: case context, Q&A notes, and opposing counsel analysis stored per matter ID in database
- OCR pipeline required for scanned PDFs
- All AI outputs must be structured (JSON) for reliable frontend rendering

---

## 14. Success Metrics

| Metric | Target |
|---|---|
| Time to first redaction suggestion | < 60 seconds after upload |
| Redaction Engine accuracy | Lawyer agrees with AI suggestion > 70% of the time |
| Q&A usefulness | Lawyer marks > 60% of Q&A entries as "Prepared" without revising the redaction |
| Q&A consistency catch rate | AI catches > 80% of inconsistent redactions that lawyer later agrees are inconsistent |
| Audit trail completeness | 100% of lawyer decisions logged with no gaps |
| Data privacy | Zero client documents used in model training |
| Lawyer review time reduction | > 25% faster than manual review baseline |