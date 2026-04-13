# LLM Lawyer

AI-driven legal document review platform. Stanford LLM x Hackathon.

Case-scoped workspace with:
- Persistent per-case memory (lawyer rules, client context, judge orders, firm KB) injected into every LLM call
- AI-driven redaction suggestions with industry labels (PRIV, WP, PII, PHI, TS) + confidence + reasoning
- Per-document memo generation and strengths/weaknesses analysis
- Grounded, citation-backed chat per document
- Multi-LLM backend with automatic fallback (OpenAI → Gemini → Groq)

## Stack

- **Backend**: FastAPI (async), SQLAlchemy 2 + asyncpg, Alembic
- **Database**: Supabase Postgres + pgvector (hosted)
- **File storage**: Supabase Storage
- **LLM**: OpenAI (`gpt-5.2`) primary, Gemini + Groq fallback (all via OpenAI-compatible API)
- **Embeddings**: Voyage `voyage-law-2` (legal-domain)
- **PDF**: PyMuPDF; **DOCX**: python-docx
- **Frontend**: Vite + React + TypeScript + Tailwind + `@uiw/react-md-editor`
- **Package manager**: `uv` (backend), `npm` (frontend)

## Prerequisites

- Python 3.11+
- Node 20+
- `uv` (`brew install uv`)
- Supabase project with:
  - `vector` extension enabled (`create extension if not exists vector;` in SQL editor)
  - Storage bucket `docs` created
- At least one LLM API key (OpenAI, Gemini, or Groq)
- Voyage AI key for embeddings

## Setup

### 1. Backend

```bash
cd llm_lawyer
cp .env.example .env
# fill in SUPABASE_URL, SUPABASE_KEY (service role), DATABASE_URL (session pooler,
#   with scheme postgresql+asyncpg://), OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY,
#   VOYAGE_API_KEY

uv sync
uv run alembic upgrade head
uv run uvicorn llm_lawyer.main:app --reload
# → http://localhost:8000 (Swagger: /docs)
```

### 2. Frontend

```bash
cd web
cp .env.example .env     # optional; default points at localhost:8000
npm install
npm run dev
# → http://localhost:5173
```

## Demo flow

1. **Create a case** at `/` — e.g. "Acme v. Widget Corp".
2. **Add persistent memory** on the Memory tab (four rich-text editors):
   - *Lawyer rules* — "flag SSN/DOB as PII; privileged as PRIV; pricing algorithms as TS"
   - *Client context*, *Judge orders*, *Firm KB* — all injected into every prompt.
3. **Upload a PDF or DOCX** on the Documents tab → auto-parsed, chunked, embedded, stored.
4. **Open the document** → 3-column review workspace:
   - Left: PDF preview (signed URL from Supabase Storage)
   - Middle: Redaction suggestions — click **Run Redaction Analysis** to populate. Each card shows label color (PRIV=rose, PII=amber, TS=indigo), confidence %, reasoning; Accept / Reject / Modify.
   - Right tabs: **Chat** (grounded Q&A with citations), **Memo** (on-demand map-reduce summary), **Strengths / Weaknesses** (structured JSON analysis).

## Architecture highlights

**Persistent memory injection.** `llm/memory_ctx.py` fetches all memories for a case, groups by kind, formats as stable markdown, and injects at the head of every LLM call (chat, redaction, memo, S/W). Stable prefix → OpenAI's automatic prompt cache hits across follow-ups.

**Multi-provider LLM client.** `llm/client.py` iterates `LLM_PROVIDERS` list (`openai,gemini,groq`), trying each and falling back on `RateLimitError` / `AuthenticationError` / `APIConnectionError`. All three providers use the same OpenAI Chat Completions protocol (Gemini + Groq via OpenAI-compatible endpoints).

**Token-efficient analysis pipelines.**
- *Redaction*: chunks are batched (5 per call) with structured JSON output.
- *Memo / Strengths-Weaknesses*: map (one call to summarise all chunks) → reduce (one synthesis call). O(1) LLM calls per doc, not O(N).
- *Case memory* is injected once per call; stable prefix benefits from prompt caching across a batch.

**pgvector RAG.** `rag/retriever.py` runs cosine similarity in Postgres (`Chunk.embedding.cosine_distance`). Filtered by `document_id` for scoped chat.

## Data model

- `cases` (id, name, client_name, matter_type, description)
- `memories` (case_id, kind: rule|client_context|judge_order|firm_kb, content markdown)
- `documents` (case_id FK, title, source_type, storage_path, sha256, ...)
- `chunks` (document_id FK, ordinal, page, text, bbox, embedding vector(1024))
- `memos` (document_id FK, content, model)
- `redactions` (document_id FK, chunk_id FK, page, bbox, text_span, label, confidence, reasoning, status)
- `document_analyses` (document_id FK, kind, content JSONB, model)
- `conversations` + `messages` (chat history)

## Key endpoints

```
POST   /cases                              create case
GET    /cases                              list cases
GET    /cases/{id}/documents               docs in case
POST   /cases/{id}/memories                add memory
PUT    /cases/{id}/memories/{mid}          update memory

POST   /documents (multipart: file, case_id)   upload+ingest
GET    /documents/{id}                         metadata + signed URL

POST   /documents/{id}/redactions/run          run LLM redaction analysis
GET    /documents/{id}/redactions              list suggestions
PATCH  /redactions/{id} {status, modified_span} review

POST   /documents/{id}/memo                    generate memo
POST   /documents/{id}/strengths_weaknesses    S/W JSON analysis

POST   /chat {message, document_id, conversation_id}  grounded chat
```

## Cuts / not yet shipped

- Redacted-PDF export (PyMuPDF supports it; wire Monday)
- Responsiveness tagging (responsive/non-responsive/questionable — legally distinct from redaction; separate feature)
- PDF overlay for redaction bboxes (today we scroll-to-page via iframe; can upgrade to `react-pdf-viewer` with highlight plugin)
- Auth (service is single-tenant for the demo)

## Troubleshooting

- **`TimeoutError` on migration**: your network blocks Postgres ports. Use VPN or phone hotspot — Supabase session pooler needs outbound port 5432.
- **`insufficient_quota`**: add billing at platform.openai.com or paste a Gemini / Groq key.
- **`socket.gaierror` on DB**: you're probably using the direct `db.*.supabase.co` host (IPv6-only). Switch to the session pooler URI (`aws-*.pooler.supabase.com`) and keep the scheme as `postgresql+asyncpg://`.
- **Stale uvicorn state** after the two-Claude-sessions workflow: if a new symbol in `prompts.py` errors as `AttributeError` at runtime even though grep confirms it exists, uvicorn cached the half-applied module. `pkill -f uvicorn` and restart; clear `__pycache__` if it persists.

---

# Technical Architecture

This section is the onboarding map: what runs where, how a request flows, and which pieces to touch for a given change.

## System at a glance

```
┌──────────────────────────┐        ┌──────────────────────────────────────┐
│  Web (Vite + React + TS) │   ──▶  │  FastAPI (async) — llm_lawyer.main   │
│  web/src/{pages,         │  HTTP  │  Routers: cases, documents,          │
│   components, lib/api.ts}│ NDJSON │   redactions, relevancy, qa,         │
└──────────────────────────┘        │   opposing, analyses, chat,          │
                                    │   emails, audit_events, health       │
                                    └───┬──────────────┬───────────────┬───┘
                                        │              │               │
                                        ▼              ▼               ▼
                            ┌───────────────┐ ┌─────────────┐ ┌─────────────┐
                            │ Supabase      │ │ Voyage (or  │ │ OpenAI /    │
                            │  Postgres     │ │  OpenAI)    │ │  Gemini /   │
                            │  + pgvector   │ │  embeddings │ │  Groq LLMs  │
                            │ Supabase      │ │             │ │ (multi-     │
                            │  Storage      │ │             │ │  provider   │
                            │  (PDF/DOCX)   │ │             │ │  fallback)  │
                            └───────────────┘ └─────────────┘ └─────────────┘
```

Three product pipelines (per PRD), all running against the same Postgres and sharing the same Case Context Memo:

1. **Own-doc review** — upload → chunk → embed → relevancy classify → redaction suggest → lawyer accept/reject/modify.
2. **Defense Q&A** — adversarial rehearsal over accepted redactions (iterative; priority-inconsistency + hard-low-confidence surfaced first).
3. **Offense on opposing production** — redaction challenges + argument-gap finder, scoped strictly to `production_type='opposing'` docs.

## Request flow (representative: redaction run)

```
User clicks "Run Redaction Analysis" in ReviewPage
  ↓
POST /documents/{id}/redactions/stream   (NDJSON)
  ↓  src/llm_lawyer/api/routes/redactions.py::stream_redactions
  │    1. Load Document + Chunks (scoped by document_id)
  │    2. PROMPTS.load_memory_context(case_id) — pulls all Memory rows, maps kind → placeholder
  │    3. PROMPTS.render(REDACTION_SYSTEM, memory_ctx) — stable system prefix
  │    4. For each batch of 5 chunks:
  │         a. llm_client.chat_completion(...)  (OpenAI → Gemini → Groq fallback)
  │         b. extract_json → verify span exists in chunk text
  │         c. INSERT redaction row, flush, yield NDJSON event
  ↓
Frontend streams cards into the review queue
  ↓
PATCH /redactions/{id} {status, modified_span}
  ↓ audit.log_event("redaction_accepted"|"rejected"|"modified")
```

Same shape for relevancy, opposing, Q&A — each uses a streaming NDJSON generator with its own system prompt and per-row audit events.

## Layers

| Layer | Path | Responsibility |
|---|---|---|
| HTTP routes | `src/llm_lawyer/api/routes/*.py` | Request/response, validation, orchestration, audit logging |
| Prompts | `src/llm_lawyer/llm/prompts.py` + `prompts/rules.md` | System prompts with named placeholders, `load_memory_context`, `render()` |
| LLM client | `src/llm_lawyer/llm/client.py` | Multi-provider fallback (OpenAI Chat-Completions protocol for all three) |
| Embeddings / retrieval | `src/llm_lawyer/rag/{embeddings,retriever,reranker,chunker}.py` | Voyage `voyage-law-2` → pgvector cosine → Voyage reranker |
| Document ingest | `src/llm_lawyer/documents/{pdf,docx,storage}.py` | Parse, chunk, upload to Supabase Storage |
| DB | `src/llm_lawyer/db/{models,session,base}.py` + `alembic/versions/` | SQLAlchemy 2 async + Alembic migrations |
| Audit | `src/llm_lawyer/audit.py` | Single `log_event()` helper called from every mutating route |
| Frontend | `web/src/pages/*`, `web/src/components/*`, `web/src/lib/api.ts` | Vite + React + TS; `api.ts` is the one network boundary |

## Data model (abridged)

- `cases` — matter root. Every AI feature is scoped by `case_id`.
- `memories(kind, content)` — the Case Context Memo. `kind ∈ {case_summary, parties, jurisdiction, key_legal_issues, privilege_rules, key_custodians, key_date_range, custom_rules}`. Rendered into every LLM system prompt via `PROMPTS.load_memory_context`.
- `documents(case_id, production_type, storage_path, relevancy_label, ...)` — `production_type ∈ {own, opposing}` is the hard boundary that keeps Pipelines 1/2 and Pipeline 3 separated.
- `chunks(document_id, page, ordinal, text, bbox, embedding vector(1024))` — pgvector index.
- `redactions(document_id, chunk_id, text_span, label, confidence, status, modified_span)` — Pipeline 1 output; `status ∈ {pending, accepted, rejected, modified}`.
- `redaction_challenges(case_id, redaction_id, run_id, challenge_question, suggested_answer, legal_basis, risk_flag, difficulty, inconsistency_peer_id, lawyer_status)` — Pipeline 2 output; `lawyer_status ∈ {pending, prepared, needs_work, will_revise}`.
- `document_analyses(document_id, kind, content JSONB)` — kind ∈ {`memo`, `strengths_weaknesses`, `opposing_review`}.
- `audit_events(case_id, document_id, actor, action, target_type, target_id, summary, metadata)` — append-only.
- `conversations + messages` — chat history.

## Case Context Memo — how it reaches the LLM

The memo is the single source of truth for what the case is about. Every AI call gets it as a stable system-prompt prefix:

```python
# in every pipeline route:
memory_ctx = await PROMPTS.load_memory_context(session, case_id)
system    = PROMPTS.render(PROMPTS.<PIPELINE>_SYSTEM, memory_ctx)
messages  = [{"role": "system", "content": system}, ...]
```

`load_memory_context` groups `Memory` rows by `kind → placeholder`, concatenating multi-row kinds. Missing kinds render as `"(none)"` so templates never `KeyError`. The same prefix across calls is what lets OpenAI's automatic prompt cache hit.

> `prompts/case_context_memo.md` is **reference for humans only** — nothing loads it at runtime. The live memo is the `memories` table.

## Pipeline isolation (own vs opposing)

- `documents.production_type` set at upload, never changed.
- `relevancy.stream_relevancy` filters `production_type == 'own'` at the DB query (not just retrieval).
- `opposing.py` rejects any document with `production_type != 'opposing'` at the route entry.
- `retriever.retrieve()` scopes by `document_id`; callers always pass one for own-doc flows.

This is the guarantee that opposing counsel's production never mixes into the client's own-doc chat, memo, redaction, or Q&A context.

## Multi-LLM fallback

`llm/client.py` walks `LLM_PROVIDERS` (default `openai,gemini,groq`) and retries on `RateLimitError | AuthenticationError | APIConnectionError`. Gemini and Groq are called through their OpenAI-compatible endpoints, so the `chat_completion` call site is identical across all three.

Embeddings have a parallel fallback: Voyage `voyage-law-2` primary → OpenAI `text-embedding-3-large` on rate-limit.

## Audit trail

`audit.log_event(session, action, case_id, ..., actor, metadata)` is called synchronously inside the same transaction as the mutating change. Every PRD §8 event class has a call site. Export is `GET /cases/{id}/audit.csv`. Rows are never updated or deleted by API.

**Known gaps** — memo lifecycle events and some analysis generation are not yet logged; `actor` is a static string pending auth.

## Migrations

Alembic linear history: `0001_init → 0002_cases → 0003_emails → 0004_production_type → 0005_relevancy_audit → 0006_case_cascade → 0007_qa_challenges`.

When two Claude sessions are working in parallel, **only one owns the next revision**. Generate on a branch, merge heads at the end. Never `alembic upgrade` against the shared Supabase instance from two sessions at once.

## Frontend

- `App.tsx` → `CasesPage` → `CasePage` (tabs: Our Pipeline / Opposing / Case Context / Audit / Consolidated) → `ReviewPage` (3-col doc workspace).
- `lib/api.ts` is the **only** place that calls `fetch`. Every route has a typed wrapper. NDJSON endpoints expose `async function*` generators (e.g. `streamRelevancy`, `streamRedactions`, `streamQa`).
- `components/ActivityConsole.tsx` surfaces the NDJSON event stream so the user sees progress without opening devtools.

## Known deviations from PRD

- **Auth** not implemented — single-tenant demo; `actor` is a constant string.
- **OCR** not implemented — scanned PDFs silently produce empty chunks.
- **Retention** not implemented — documents persist indefinitely; `case_id` FK cascade was tightened in migration `0006` to limit orphaning.
- **Pipeline 2 re-trigger** currently regenerates all challenges; PRD §6.4 requires re-challenging only revised redactions.
- See PR-specific review notes for the shortlist of follow-ups.
