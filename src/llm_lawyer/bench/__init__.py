"""Benchmark + validation harness for the LLM Lawyer pipelines.

Runs the demo dataset through the real API (in-process ASGI) and scores
actual output against the structured ground truth at
``data/benchmark/ground_truth.json`` (encoded from ``data/EXPECTED_OUTPUTS.md``).

Covers all four product surfaces:
  * relevancy filtering
  * our redaction engine + the Q&A defence of our redactions
  * opposing counsel redaction challenges + gap analysis
  * the final consolidated case review

Entry point::

    uv run python -m llm_lawyer.bench --check     # preflight only
    uv run python -m llm_lawyer.bench             # full run + report
"""
