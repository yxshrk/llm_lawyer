"""Orchestrates a full benchmark run: ingest demo data, drive every
pipeline through the real API, score the output, write reports."""
from __future__ import annotations

import sys
import time

from llm_lawyer.bench import scorers
from llm_lawyer.bench.dataset import (
    DATA_DIR,
    build_dataset,
    collapse_mbox,
    load_ground_truth,
)
from llm_lawyer.bench.harness import AppHarness


def _log(msg: str) -> None:
    print(f"[bench] {msg}", flush=True)


async def run_benchmark() -> tuple[list[scorers.Check], dict]:
    gt = load_ground_truth()
    items = build_dataset(gt)
    all_checks: list[scorers.Check] = []

    async with AppHarness() as h:
        assert await h.health(), "health check failed"
        case = await h.create_case(
            f"BENCH Ellingson v. DOJ {int(time.time())}"
        )
        _log(f"case {case}")
        await h.set_memory(gt["case_context"])
        _log(f"case context memo set ({len(gt['case_context'])} fields)")

        # --- ingest own production -----------------------------------------
        doc_by_path: dict[str, str] = {}
        for it in items:
            _eid, did = await h.ingest(it.email, "own")
            if did:
                doc_by_path[it.rel_path] = did
        _log(f"ingested {len(doc_by_path)} own documents")

        # --- relevancy -----------------------------------------------------
        _log("running relevancy filter…")
        rel = await h.run_relevancy()  # doc_id -> {label,...}
        predicted = {
            path: rel.get(did, {}).get("label")
            for path, did in doc_by_path.items()
        }
        all_checks += scorers.score_relevancy(gt["relevancy"], predicted)

        # --- our redactions ------------------------------------------------
        body_by_path = {it.rel_path: it.email.body for it in items}
        red_by_path: dict[str, list[dict]] = {}
        for r_gt in gt["redactions"]:
            path = r_gt["file"]
            did = doc_by_path.get(path)
            if not did:
                all_checks.append(
                    scorers.Check("redaction", f"{path}: ingested", False,
                                  "critical", "document not materialised")
                )
                continue
            _log(f"redactions: {path}")
            reds = await h.run_redactions(did)
            red_by_path[path] = reds
            all_checks += scorers.score_redactions(
                r_gt, body_by_path.get(path, ""), reds
            )

        # --- Q&A defence of our redactions ---------------------------------
        accepted = 0
        for reds in red_by_path.values():
            accepted += await h.accept_redactions(reds)
        _log(f"accepted {accepted} redactions; running Q&A…")
        challenges = await h.run_qa()
        all_checks += scorers.score_qa(gt["qa_defense"], challenges)

        # --- opposing counsel review ---------------------------------------
        opp_gt = gt["opposing_review"]
        opp_path = DATA_DIR / opp_gt["file"]
        if opp_path.exists():
            _log("ingesting opposing (DOJ) production…")
            collapsed = collapse_mbox(opp_path, "DOJ Production — Ellingson")
            _eid, opp_doc = await h.ingest(collapsed, "opposing")
            if opp_doc:
                _log("running opposing counsel review…")
                opp_result = await h.run_opposing(opp_doc)
                all_checks += scorers.score_opposing(opp_gt, opp_result)
            else:
                all_checks.append(
                    scorers.Check("opposing", "DOJ production ingested",
                                  False, "critical", "no document id")
                )
        else:
            all_checks.append(
                scorers.Check("opposing", "DOJ fixture present", False,
                              "normal", f"missing {opp_path}")
            )

        # --- final consolidated case review --------------------------------
        _log("running consolidated case brief…")
        cons = await h.run_consolidated()
        pdf_ok = False
        if not cons.get("error"):
            pdf_ok = await h.consolidated_pdf_ok()
        all_checks += scorers.score_consolidated(
            gt["consolidated_brief"], cons, pdf_ok
        )

    summary = scorers.summarize(all_checks)
    return all_checks, summary


def print_summary(summary: dict) -> None:
    _log("=" * 56)
    _log(f"VERDICT: {summary['verdict']}")
    _log(
        f"{summary['passed']}/{summary['total_checks']} checks passed "
        f"({summary['pass_rate']:.0%}), "
        f"{summary['critical_failures']} critical failures"
    )
    for name, p in summary["by_pipeline"].items():
        _log(
            f"  {name:<14} "
            f"{p['passed']:>2} ✓  {p['failed']:>2} ✗  "
            f"({p['critical_failed']} critical)"
        )
    _log("=" * 56)


def fail_exit_code(summary: dict) -> int:
    return 0 if summary["verdict"] == "PASS" else 1


def die(problems: list[str]) -> None:
    _log("PREFLIGHT FAILED — cannot run live benchmark:")
    for p in problems:
        _log(f"  - {p}")
    _log(
        "Set DATABASE_URL / OPENAI_API_KEY / VOYAGE_API_KEY in .env and "
        "run `uv run alembic upgrade head`, then retry."
    )
    sys.exit(2)
