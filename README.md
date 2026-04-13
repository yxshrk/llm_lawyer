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
