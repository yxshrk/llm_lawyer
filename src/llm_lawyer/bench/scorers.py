"""Pure scoring functions: actual pipeline output vs structured ground truth.

Every scorer returns a list of :class:`Check`. Matching is deliberately
tolerant (case-insensitive substring, loose category normalisation) because
the ground truth describes *what must be true*, not exact model phrasing —
the goal is to catch real regressions, not punish wording.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Check:
    pipeline: str
    name: str
    passed: bool
    severity: str  # "critical" | "normal" | "soft"
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _norm(s: str | None) -> str:
    return (s or "").lower()


def _band(conf: float | None) -> str:
    if conf is None:
        return "unknown"
    if conf >= 0.7:
        return "high"
    if conf >= 0.4:
        return "medium"
    return "low"


# --------------------------------------------------------------------------
# 1. Relevancy
# --------------------------------------------------------------------------
def score_relevancy(
    gt: list[dict], predicted: dict[str, str]
) -> list[Check]:
    """predicted: rel_path -> predicted label ('relevant'|'uncertain'|...)."""
    checks: list[Check] = []
    correct = 0
    total = 0
    for entry in gt:
        rel = entry["file"]
        exp = entry["expected"]
        pred = predicted.get(rel)
        if pred is None:
            checks.append(
                Check("relevancy", f"{rel}", False, "normal",
                      "no prediction (not ingested/classified)")
            )
            total += 1
            continue
        # "uncertain" counts as not-a-miss for relevant docs (lawyer reviews),
        # but a relevant doc predicted "irrelevant" is a hard miss.
        ok = (
            pred == exp
            or (exp == "relevant" and pred == "uncertain")
        )
        total += 1
        correct += 1 if ok else 0
        sev = "critical" if entry.get("critical_false_positive") else "normal"
        # Critical: the Wallace vacation email must NOT be relevant.
        if entry.get("critical_false_positive"):
            ok = pred != "relevant"
        checks.append(
            Check("relevancy", rel, ok, sev,
                  f"expected={exp} predicted={pred}")
        )
    acc = correct / total if total else 0.0
    checks.append(
        Check("relevancy", "accuracy", acc >= 0.85, "normal",
              f"{correct}/{total} = {acc:.0%} (threshold 85%)")
    )
    return checks


# --------------------------------------------------------------------------
# 2. Our redactions
# --------------------------------------------------------------------------
_CATEGORY_ALIASES = {
    "attorney-client privilege": ["attorney", "privilege", "priv", "a-c"],
    "harmful/incriminating content": [
        "harmful", "incriminat", "damaging", "adverse"
    ],
    "pii": ["pii", "personal", "ssn", "financial", "sensitive"],
}


def _category_matches(expected: str, labels: list[str]) -> bool:
    aliases = _CATEGORY_ALIASES.get(expected.lower(), [expected.lower()])
    joined = " ".join(_norm(x) for x in labels)
    return any(a in joined for a in aliases)


def score_redactions(
    gt_item: dict, body: str, redactions: list[dict]
) -> list[Check]:
    f = gt_item["file"]
    checks: list[Check] = []
    spans = [_norm(r.get("text_span")) for r in redactions]
    labels = [r.get("label", "") for r in redactions]
    all_spans = " \n ".join(spans)
    body_l = _norm(body)

    if gt_item.get("expect_redaction") is False:
        # email1: privilege waived -> produce, don't redact (or only low conf)
        high_conf = [
            r for r in redactions if (r.get("confidence") or 0) >= 0.7
        ]
        ok = len(redactions) == 0 or len(high_conf) == 0
        checks.append(
            Check("redaction", f"{f}: no confident redaction (waiver)",
                  ok, "critical",
                  f"{len(redactions)} redactions, "
                  f"{len(high_conf)} high-confidence")
        )
        return checks

    if redactions:
        ok_cat = _category_matches(gt_item["expected_category"], labels)
        checks.append(
            Check("redaction", f"{f}: category ~ "
                  f"{gt_item['expected_category']}", ok_cat, "normal",
                  f"labels={sorted(set(labels))}")
        )
    else:
        checks.append(
            Check("redaction", f"{f}: produced at least one redaction",
                  False, "critical", "no redactions returned")
        )

    for sub in gt_item.get("must_redact_substrings", []):
        present = _norm(sub) in all_spans
        checks.append(
            Check("redaction", f"{f}: redacts '{sub[:40]}'", present,
                  "critical",
                  "found in a redaction span" if present
                  else "NOT covered by any redaction span")
        )

    for sub in gt_item.get("must_not_redact_substrings", []):
        # Substring present in body but must remain outside every span.
        leaked = _norm(sub) in all_spans
        in_body = _norm(sub) in body_l
        passed = (not leaked) if in_body else True
        checks.append(
            Check("redaction", f"{f}: keeps '{sub[:40]}' unredacted",
                  passed, "critical",
                  "OVERBROAD: factual text was redacted" if leaked
                  else "factual text preserved")
        )

    if gt_item.get("overbroad_if_full_body") and redactions and body.strip():
        longest = max(len(r.get("text_span") or "") for r in redactions)
        ratio = longest / max(len(body), 1)
        ok = ratio < 0.8
        checks.append(
            Check("redaction", f"{f}: not whole-body overbroad", ok,
                  "normal",
                  f"largest span = {ratio:.0%} of body "
                  f"(overbroad if >=80%)")
        )

    if "expected_confidence" in gt_item and redactions:
        bands = {_band(r.get("confidence")) for r in redactions}
        ok = gt_item["expected_confidence"] in bands
        checks.append(
            Check("redaction", f"{f}: confidence band includes "
                  f"{gt_item['expected_confidence']}", ok, "soft",
                  f"observed bands={sorted(bands)}")
        )
    return checks


# --------------------------------------------------------------------------
# 3. Q&A defence of our redactions
# --------------------------------------------------------------------------
def score_qa(gt: dict, challenges: list[dict]) -> list[Check]:
    checks: list[Check] = []
    if not challenges:
        checks.append(
            Check("qa_defense", "challenges generated", False, "critical",
                  "Q&A produced zero challenges")
        )
        return checks
    blob = " \n ".join(
        _norm(c.get("challenge_question")) + " " + _norm(c.get("risk_flag"))
        + " " + _norm(c.get("difficulty"))
        for c in challenges
    )
    for exp in gt["expected_challenges"]:
        toks = [t.lower() for t in exp["challenge_must_match_any"]]
        hit = any(t in blob for t in toks)
        checks.append(
            Check("qa_defense",
                  f"{exp['kind']} challenge ({exp['for_file']})",
                  hit, "critical",
                  f"looked for any of {toks}")
        )
        if "difficulty_should_be" in exp:
            d_hit = any(
                _norm(c.get("difficulty")) == exp["difficulty_should_be"]
                for c in challenges
            )
            checks.append(
                Check("qa_defense",
                      f"{exp['kind']}: difficulty="
                      f"{exp['difficulty_should_be']}", d_hit, "soft",
                      "consistency flagged as priority"
                      if d_hit else "not tagged priority_inconsistency")
            )
        if "risk_flag_must_match_any" in exp:
            r_hit = any(
                t.lower() in blob for t in exp["risk_flag_must_match_any"]
            )
            checks.append(
                Check("qa_defense", f"{exp['kind']}: risk flag present",
                      r_hit, "normal", "")
            )
    return checks


# --------------------------------------------------------------------------
# 4. Opposing counsel review
# --------------------------------------------------------------------------
def score_opposing(gt: dict, result: dict) -> list[Check]:
    checks: list[Check] = []
    challenges = result.get("challenges", [])
    gaps = result.get("gaps", [])
    checks.append(
        Check("opposing", "challenges generated",
              len(challenges) >= gt.get("min_challenges", 1), "normal",
              f"{len(challenges)} challenges, {len(gaps)} gaps")
    )
    blob = " \n ".join(
        _norm(g.get("expected_topic")) + " " + _norm(g.get("gap_description"))
        + " " + _norm(g.get("significance"))
        for g in gaps
    ) + " \n " + " \n ".join(
        _norm(c.get("challenge")) + " " + _norm(c.get("legal_basis"))
        for c in challenges
    )
    for finding in gt["expected_findings"]:
        toks = [t.lower() for t in finding["must_match_any"]]
        hit = any(t in blob for t in toks)
        checks.append(
            Check("opposing", f"{finding['kind']}: {finding['topic']}",
                  hit, "normal", f"looked for any of {toks}")
        )
    return checks


# --------------------------------------------------------------------------
# 5. Final consolidated case review
# --------------------------------------------------------------------------
def score_consolidated(
    gt: dict, result: dict, pdf_ok: bool
) -> list[Check]:
    checks: list[Check] = []
    if result.get("error"):
        checks.append(
            Check("consolidated", "brief generated", False, "critical",
                  f"error: {result['error']}")
        )
        return checks
    brief = _norm(result.get("brief"))
    checks.append(
        Check("consolidated", "brief non-empty", len(brief) > 200,
              "critical", f"{len(brief)} chars")
    )
    head_hit = any(
        _norm(h) in brief for h in gt["must_contain_headings_any"]
    )
    checks.append(
        Check("consolidated", "has a strategic-section heading",
              head_hit, "normal",
              f"any of {gt['must_contain_headings_any']}")
    )
    ref_hit = any(_norm(k) in brief for k in gt["must_reference_any"])
    checks.append(
        Check("consolidated", "references privilege/exposure", ref_hit,
              "normal", "")
    )
    agg = result.get("aggregate", {})
    counts = agg.get("counts", {}) if isinstance(agg, dict) else {}
    for k, minimum in gt["aggregate_min"].items():
        v = counts.get(k, 0)
        checks.append(
            Check("consolidated", f"aggregate.{k} >= {minimum}",
                  v >= minimum, "normal", f"actual={v}")
        )
    checks.append(
        Check("consolidated", "PDF export valid", pdf_ok, "normal",
              "%PDF header + application/pdf")
    )
    return checks


def summarize(all_checks: list[Check]) -> dict:
    by_pipeline: dict[str, dict] = {}
    crit_fail = 0
    for c in all_checks:
        p = by_pipeline.setdefault(
            c.pipeline, {"passed": 0, "failed": 0, "critical_failed": 0}
        )
        if c.passed:
            p["passed"] += 1
        else:
            p["failed"] += 1
            if c.severity == "critical":
                p["critical_failed"] += 1
                crit_fail += 1
    total = len(all_checks)
    passed = sum(1 for c in all_checks if c.passed)
    return {
        "total_checks": total,
        "passed": passed,
        "failed": total - passed,
        "critical_failures": crit_fail,
        "pass_rate": (passed / total) if total else 0.0,
        "by_pipeline": by_pipeline,
        "verdict": "PASS" if crit_fail == 0 and passed / max(total, 1) >= 0.8
        else "FAIL",
    }
