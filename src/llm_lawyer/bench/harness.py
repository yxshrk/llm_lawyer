"""In-process driver for the real FastAPI app.

Exercises the exact HTTP surface the frontend uses (via httpx ASGI transport,
no network/uvicorn) so the benchmark and the smoke test validate the same
code paths a browser would hit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from llm_lawyer.bench.dataset import ParsedEmail
from llm_lawyer.config import get_settings

# LLM + embedding + RAG calls are slow; never let httpx time them out.
_NO_TIMEOUT = httpx.Timeout(None)


@dataclass
class Preflight:
    ok: bool
    problems: list[str]


async def preflight() -> Preflight:
    """Check everything the live pipelines need before we spend tokens."""
    problems: list[str] = []
    s = get_settings()
    if not s.database_url:
        problems.append("DATABASE_URL is not set")
    if not (s.openai_api_key or s.gemini_api_key or s.groq_api_key):
        problems.append("no LLM provider key set (openai/gemini/groq)")
    if not s.voyage_api_key:
        problems.append("VOYAGE_API_KEY is not set (embeddings/relevancy)")

    if s.database_url:
        try:
            from sqlalchemy import text

            from llm_lawyer.db.session import engine

            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("SELECT 1 FROM case_analyses LIMIT 1"))
        except Exception as e:
            msg = str(e).splitlines()[-1][:200]
            problems.append(f"database unreachable / not migrated: {msg}")

    return Preflight(ok=not problems, problems=problems)


class AppHarness:
    """Async context manager wrapping the ASGI app + a scratch case."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self.case_id: str | None = None

    async def __aenter__(self) -> "AppHarness":
        from llm_lawyer.main import app

        transport = httpx.ASGITransport(app=app)
        self._client = httpx.AsyncClient(
            transport=transport,
            base_url="http://bench",
            timeout=_NO_TIMEOUT,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()

    @property
    def c(self) -> httpx.AsyncClient:
        assert self._client is not None
        return self._client

    # --- streaming helper -------------------------------------------------
    async def _ndjson(self, method: str, url: str) -> list[dict]:
        events: list[dict] = []
        async with self.c.stream(method, url) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    # --- setup ------------------------------------------------------------
    async def health(self) -> bool:
        r = await self.c.get("/health")
        return r.status_code == 200

    async def create_case(self, name: str) -> str:
        r = await self.c.post(
            "/cases",
            json={"name": name, "client_name": "Ellingson Mineral Company",
                  "matter_type": "Insider fraud / eDiscovery"},
        )
        r.raise_for_status()
        self.case_id = r.json()["id"]
        return self.case_id

    async def set_memory(self, context: dict[str, str]) -> None:
        for kind, content in context.items():
            if not content:
                continue
            r = await self.c.post(
                f"/cases/{self.case_id}/memories",
                json={"kind": kind, "content": content},
            )
            r.raise_for_status()

    async def ingest(
        self, email: ParsedEmail, production_type: str = "own"
    ) -> tuple[str, str | None]:
        """POST an email; return (email_id, materialized_document_id)."""
        payload = {
            "from_addr": email.from_addr,
            "to_addrs": email.to_addrs,
            "subject": email.subject,
            "body": email.body,
            "production_type": production_type,
        }
        if email.timestamp:
            payload["timestamp"] = email.timestamp
        r = await self.c.post(
            f"/cases/{self.case_id}/emails", json=payload
        )
        r.raise_for_status()
        email_id = r.json()["id"]

        docs = (
            await self.c.get(f"/cases/{self.case_id}/documents")
        ).json()
        doc_id = next(
            (d["id"] for d in docs if d.get("email_id") == email_id), None
        )
        return email_id, doc_id

    # --- pipelines --------------------------------------------------------
    async def run_relevancy(self) -> dict[str, dict]:
        events = await self._ndjson(
            "POST", f"/cases/{self.case_id}/relevancy/stream"
        )
        out: dict[str, dict] = {}
        for ev in events:
            if ev.get("type") == "doc":
                out[ev["document_id"]] = {
                    "label": ev.get("label"),
                    "score": ev.get("score"),
                    "title": ev.get("title"),
                }
        return out

    async def run_redactions(self, doc_id: str) -> list[dict]:
        r = await self.c.post(
            f"/documents/{doc_id}/redactions/run?batch_size=5"
        )
        r.raise_for_status()
        lst = await self.c.get(f"/documents/{doc_id}/redactions")
        lst.raise_for_status()
        return lst.json()

    async def accept_redactions(self, redactions: list[dict]) -> int:
        n = 0
        for red in redactions:
            resp = await self.c.patch(
                f"/redactions/{red['id']}", json={"status": "accepted"}
            )
            if resp.status_code < 300:
                n += 1
        return n

    async def run_qa(self) -> list[dict]:
        events = await self._ndjson(
            "POST", f"/cases/{self.case_id}/qa/run"
        )
        challenges = [
            ev["challenge"] for ev in events if ev.get("type") == "challenge"
        ]
        if not challenges:
            got = await self.c.get(f"/cases/{self.case_id}/qa")
            if got.status_code < 300:
                challenges = got.json()
        return challenges

    async def run_opposing(self, doc_id: str) -> dict:
        events = await self._ndjson(
            "POST", f"/documents/{doc_id}/opposing_review/stream"
        )
        return {
            "challenges": [
                e["challenge"] for e in events if e.get("type") == "challenge"
            ],
            "gaps": [e["gap"] for e in events if e.get("type") == "gap"],
        }

    async def run_consolidated(self) -> dict:
        events = await self._ndjson(
            "POST", f"/cases/{self.case_id}/consolidated/stream"
        )
        out: dict = {"brief": "", "aggregate": {}, "error": None}
        for ev in events:
            t = ev.get("type")
            if t == "aggregate":
                out["aggregate"] = ev.get("aggregate", {})
            elif t == "brief":
                out["brief"] = ev.get("content", "")
            elif t == "error":
                out["error"] = ev.get("message")
        return out

    async def consolidated_pdf_ok(self) -> bool:
        r = await self.c.get(f"/cases/{self.case_id}/consolidated.pdf")
        return (
            r.status_code == 200
            and r.headers.get("content-type") == "application/pdf"
            and r.content[:5] == b"%PDF-"
        )
