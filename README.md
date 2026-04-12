# LexAgent

AI-powered eDiscovery and litigation prep for solo and small firm lawyers.

Built at the Stanford LLM x Hackathon (April 2026).

---

## What it does

eDiscovery is brutal for small firms — thousands of documents, manual review, redaction decisions that have to hold up in court. LexAgent automates the pipeline so lawyers can focus on strategy, not grunt work.

**Core workflows:**

1. **Relevancy filtering** — upload client documents, brief the AI on your case, get every doc classified as Relevant / Irrelevant / Uncertain with plain-English reasoning
2. **Redaction engine** — AI scans relevant docs and suggests redactions (privilege, trade secrets, PII) with confidence scores and legal reasoning per suggestion
3. **Q&A challenge set** — before production, simulate the questions a judge or opposing counsel would ask about your redactions; find and fix weak ones before it matters
4. **Opposing counsel review** — upload their production, get a list of challengeable redactions + an argument gap analysis you can use at deposition or in motions

---

## How it works

- Lawyer creates a matter and uploads documents
- Writes a **Case Context Memo** (case summary, parties, jurisdiction, key legal issues) — this briefs every AI stage
- AI processes documents through the pipeline stages above
- Every decision is logged to an immutable audit trail, exportable for court

---

## Tech

- RAG over uploaded PDFs
- Separate LLM prompts per pipeline stage
- Structured JSON outputs for all AI responses
- OCR pipeline for scanned PDFs
- Per-matter persistent storage (case context, Q&A notes, audit trail)

Stack: TBD

---

## Docs

- [Product Requirements Document](prd.md) — full feature spec, user stories, error handling, success metrics

---

## Status

Hackathon project — in active development.
