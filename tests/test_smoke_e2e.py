"""End-to-end smoke test — one pass through the whole product.

Walks the exact API surface the frontend uses: create case → case context
memo → ingest documents → relevancy → our redactions → Q&A defence →
opposing counsel review → consolidated case brief + PDF export.

It is intentionally light (a few documents, not the full corpus) so it runs
in a CI-ish timeframe; the exhaustive scored validation lives in
``python -m llm_lawyer.bench``. Auto-skips when live infra is unavailable.
"""
from __future__ import annotations

import time

import pytest

from llm_lawyer.bench.dataset import (
    DATA_DIR,
    collapse_mbox,
    load_ground_truth,
    parse_mbox,
)
from llm_lawyer.bench.harness import AppHarness

pytestmark = pytest.mark.e2e


async def test_full_pipeline_smoke(require_live):
    gt = load_ground_truth()

    async with AppHarness() as h:
        assert await h.health(), "GET /health should return 200"

        case_id = await h.create_case(f"SMOKE {int(time.time())}")
        assert case_id
        await h.set_memory(gt["case_context"])

        # A relevant PII email, an irrelevant one, and the waiver email.
        pii = parse_mbox(DATA_DIR / "synthetic/email4_pii.mbox")[0]
        golf = parse_mbox(DATA_DIR / "irrelevant/golf_invite.mbox")[0]
        waiver = parse_mbox(
            DATA_DIR / "synthetic/email1_privilege_waiver.mbox"
        )[0]

        _, pii_doc = await h.ingest(pii, "own")
        _, golf_doc = await h.ingest(golf, "own")
        _, _ = await h.ingest(waiver, "own")
        assert pii_doc and golf_doc, "emails must materialise as documents"

        # --- relevancy ---
        rel = await h.run_relevancy()
        assert pii_doc in rel, "PII email should be classified"
        assert rel[pii_doc]["label"] in {"relevant", "uncertain"}
        # Content-based: a golf invite is not relevant to the cyberattack.
        assert rel.get(golf_doc, {}).get("label") in {
            "irrelevant",
            "uncertain",
        }, "golf invite must not be classified relevant"

        # --- our redactions: PII must be caught ---
        reds = await h.run_redactions(pii_doc)
        assert reds, "PII email must yield at least one redaction"
        spans = " ".join(r.get("text_span", "").lower() for r in reds)
        assert "412-67-3901" in spans, "SSN must be redacted"

        accepted = await h.accept_redactions(reds)
        assert accepted >= 1

        # --- Q&A defence of accepted redactions ---
        challenges = await h.run_qa()
        assert challenges, "Q&A must produce challenges for accepted redactions"
        assert all(
            "challenge_question" in c for c in challenges
        )

        # --- opposing counsel review (collapsed DOJ production) ---
        doj = collapse_mbox(
            DATA_DIR / "opposing/DOJ_EmailFile.mbox", "DOJ Production"
        )
        _, opp_doc = await h.ingest(doj, "opposing")
        assert opp_doc
        opp = await h.run_opposing(opp_doc)
        assert isinstance(opp["challenges"], list)
        assert isinstance(opp["gaps"], list)

        # --- final consolidated case review + PDF ---
        cons = await h.run_consolidated()
        assert not cons.get("error"), cons.get("error")
        assert len(cons.get("brief", "")) > 200, "brief should be substantive"
        assert cons["aggregate"]["counts"]["accepted_redactions"] >= 1
        assert await h.consolidated_pdf_ok(), "PDF export must be a valid PDF"
