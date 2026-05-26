"""Render scored checks to JSON + Markdown."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from llm_lawyer.bench.scorers import Check


def write_reports(
    checks: list[Check], summary: dict, out_dir: Path
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    json_path = out_dir / f"benchmark_{stamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "generated_at": stamp,
                "summary": summary,
                "checks": [c.as_dict() for c in checks],
            },
            indent=2,
        )
    )

    lines: list[str] = []
    lines.append(f"# LLM Lawyer Benchmark — {stamp}")
    lines.append("")
    v = summary["verdict"]
    badge = "✅ PASS" if v == "PASS" else "❌ FAIL"
    lines.append(f"**Verdict: {badge}**")
    lines.append("")
    lines.append(
        f"- Checks: {summary['passed']}/{summary['total_checks']} passed "
        f"({summary['pass_rate']:.0%})"
    )
    lines.append(f"- Critical failures: {summary['critical_failures']}")
    lines.append("")
    lines.append("| Pipeline | Passed | Failed | Critical fails |")
    lines.append("|---|---|---|---|")
    for name, p in summary["by_pipeline"].items():
        lines.append(
            f"| {name} | {p['passed']} | {p['failed']} | "
            f"{p['critical_failed']} |"
        )
    lines.append("")

    current = None
    for c in checks:
        if c.pipeline != current:
            current = c.pipeline
            lines.append(f"\n## {current}\n")
            lines.append("| ✓ | Sev | Check | Detail |")
            lines.append("|---|---|---|---|")
        mark = "✅" if c.passed else "❌"
        sev = {"critical": "🔴", "normal": "🟡", "soft": "⚪"}.get(
            c.severity, ""
        )
        detail = c.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {mark} | {sev} | {c.name} | {detail} |")

    md_path = out_dir / f"benchmark_{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path
