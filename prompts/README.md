# Prompts

System prompts and context documents injected into LLM calls.

| File | Pipeline | Purpose |
|---|---|---|
| `case_context_memo.md` | All pipelines | Lawyer's briefing — injected as system context into every LLM call. Drives relevancy filtering, redaction categorisation, Q&A challenges, and opposing counsel analysis. |

## How the Case Context Memo works

Per PRD §5.2: the lawyer fills this out once after uploading documents. It is then passed as system-level context to every AI call across all three pipelines. Without it, AI processing is blocked.

For new matters, copy `case_context_memo.md` and fill in each section.
