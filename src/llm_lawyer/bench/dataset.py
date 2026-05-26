"""Demo-dataset loading + ground-truth access.

Parses the ``.mbox`` / ``.txt`` fixtures under ``data/`` into the structured
shape the ingestion API expects, and loads the machine-readable ground truth.
"""
from __future__ import annotations

import json
import mailbox
import tempfile
from dataclasses import dataclass, field
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

# repo/  (…/llm_lawyer/llm_lawyer)
_PKG_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = _PKG_ROOT / "data"
GROUND_TRUTH = DATA_DIR / "benchmark" / "ground_truth.json"


@dataclass
class ParsedEmail:
    from_addr: str | None
    to_addrs: str | None
    subject: str | None
    body: str
    timestamp: str | None = None  # ISO 8601 or None


@dataclass
class DatasetItem:
    """One fixture file + its ground-truth expectations."""

    rel_path: str
    kind: str  # "email" | "text"
    production_type: str  # "own" | "opposing"
    email: ParsedEmail
    expected_relevancy: str | None = None
    extra: dict = field(default_factory=dict)


def _decode(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return str(part.get_payload() or "")
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return str(part.get_payload() or "")


def _msg_body(msg: Message) -> str:
    if msg.is_multipart():
        chunks = [
            _decode(p)
            for p in msg.walk()
            if p.get_content_type() == "text/plain"
        ]
        return "\n".join(c for c in chunks if c).strip()
    return _decode(msg).strip()


def _msg_to_email(msg: Message) -> ParsedEmail:
    ts = None
    raw_date = msg.get("Date")
    if raw_date:
        try:
            ts = parsedate_to_datetime(raw_date).isoformat()
        except Exception:
            ts = None
    return ParsedEmail(
        from_addr=msg.get("From"),
        to_addrs=msg.get("To"),
        subject=msg.get("Subject"),
        body=_msg_body(msg),
        timestamp=ts,
    )


def parse_mbox(path: Path) -> list[ParsedEmail]:
    """Return every message in an mbox. ``mailbox`` needs a real path, so we
    copy into a temp file to stay robust against odd permissions."""
    with tempfile.NamedTemporaryFile(
        suffix=".mbox", delete=True
    ) as tmp:
        tmp.write(path.read_bytes())
        tmp.flush()
        box = mailbox.mbox(tmp.name)
        try:
            return [_msg_to_email(m) for m in box]
        finally:
            box.close()


def collapse_mbox(path: Path, subject: str) -> ParsedEmail:
    """Flatten a multi-message mbox (e.g. the 72-message DOJ production) into
    a single reviewable document so opposing review runs once over the whole
    production rather than 72 times."""
    msgs = parse_mbox(path)
    blocks = []
    for i, m in enumerate(msgs, 1):
        blocks.append(
            f"===== Document {i} =====\n"
            f"From: {m.from_addr or '(unknown)'}\n"
            f"To: {m.to_addrs or '(unknown)'}\n"
            f"Subject: {m.subject or '(no subject)'}\n"
            f"Date: {m.timestamp or '(unknown)'}\n\n"
            f"{m.body}".strip()
        )
    return ParsedEmail(
        from_addr="doj-production@justice.gov",
        to_addrs="ellingson-counsel@example.com",
        subject=subject,
        body="\n\n".join(blocks),
        timestamp=msgs[0].timestamp if msgs else None,
    )


def read_text_fixture(path: Path) -> ParsedEmail:
    """A .txt fixture (memo, transcript) ingested as an email body so it
    flows through the same Pipeline-1 path as the mbox fixtures."""
    return ParsedEmail(
        from_addr=None,
        to_addrs=None,
        subject=path.stem,
        body=path.read_text(errors="replace").strip(),
        timestamp=None,
    )


def load_ground_truth() -> dict:
    return json.loads(GROUND_TRUTH.read_text())


def build_dataset(gt: dict) -> list[DatasetItem]:
    """Turn the ground-truth relevancy list into ingestible items. Opposing
    production is handled separately by the runner (collapsed)."""
    items: list[DatasetItem] = []
    for entry in gt["relevancy"]:
        rel = entry["file"]
        path = DATA_DIR / rel
        if not path.exists():
            continue
        if path.suffix == ".mbox":
            msgs = parse_mbox(path)
            email = msgs[0] if msgs else ParsedEmail(None, None, path.stem, "")
            kind = "email"
        else:
            email = read_text_fixture(path)
            kind = "text"
        items.append(
            DatasetItem(
                rel_path=rel,
                kind=kind,
                production_type="own",
                email=email,
                expected_relevancy=entry["expected"],
                extra=entry,
            )
        )
    return items
