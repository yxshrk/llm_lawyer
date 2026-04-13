# Demo Data

Everything an engineer needs to load and test LexAgent against a real case.

---

## What's here

```
data/
  README.md              ← you are here
  NARRATIVE.md           ← full case story, stakeholder profiles, timeline
  EXPECTED_OUTPUTS.md    ← ground truth: what the AI must output per document

  client/                ← Pipeline 1 + 2 input (own documents)
  irrelevant/            ← Pipeline 1 input (noise — for relevancy filtering)
  opposing/              ← Pipeline 3 input (opposing counsel's production)
  synthetic/             ← 5 hand-crafted emails that cover redaction edge cases
```

---

## The case

**Ellingson Mineral Company v. Belford et al.** — an insider cyberattack case from October 1995. Eugene Belford (Head of IT Security) planted a virus to steal $25.1M. Margo Wallace (VP Operations) was the inside co-conspirator. CEO Hal Benson is the client. The DOJ has seized internal Ellingson documents.

Full story: see [`NARRATIVE.md`](NARRATIVE.md)

---

## How to load for a demo

### Step 1 — Client pipeline (Pipelines 1 & 2)

Load everything in `client/` + `synthetic/` + `irrelevant/` as a single document set.

| Folder | What's in it | Count |
|---|---|---|
| `client/` | Real EMC-2 emails (5 custodians) + 3 standalone docs | 8 files |
| `synthetic/` | Hand-crafted emails covering redaction edge cases | 5 files |
| `irrelevant/` | Obvious noise for relevancy filtering demo | 3 files |

**Important:** `synthetic/` emails don't have a separate folder to load from — inject them alongside `client/` as if they were real documents in the case.

### Step 2 — Opposing counsel pipeline (Pipeline 3)

Load `opposing/DOJ_EmailFile.mbox` as a **separate** document set. Never mix with client documents.

### Step 3 — Case Context Memo

Load `../prompts/case_context_memo.md` as the system context. This is injected into every LLM call. Without it, AI processing should be blocked (per PRD §5.2).

---

## File details

### `client/` — own documents

| File | Custodian | Why it matters |
|---|---|---|
| `ebelford.mbox` | Eugene Belford (defendant) | Planning emails, ROT13 hacker comms, confession to Wallace |
| `mwallace.mbox` | Margo Wallace (co-conspirator) | Cover story emails, offshore coordination |
| `hbenson.mbox` | Hal Benson (CEO / client) | Board crisis comms, receives mixed factual/legal memos |
| `schen.mbox` | Sarah Chen (Acting CTO) | Detected the attack, contacted FBI, forwarded confession |
| `rgill.mbox` | Richard Gill (IT) | Access log analysis, one buried legal observation |
| `Da_Vinci_virus_analys.txt` | — | Technical analysis of the virus |
| `plague_voicemail_transcript.txt` | — | Voicemail transcript |
| `memo_10101995.txt` | — | Internal memo |

### `synthetic/` — hand-crafted edge case emails

Each email is designed to produce a specific AI behaviour. Load alongside `client/`.

| File | Scenario | What it tests |
|---|---|---|
| `email1_privilege_waiver.mbox` | Belford emails his attorney — CC's Margo Wallace (non-lawyer) | Privilege waiver detection |
| `email2_mixed_content.mbox` | Legal memo to Benson: half factual, half legal advice | Partial redaction (surgical, not whole-document) |
| `email3_inconsistency_a.mbox` | Belford confesses Da Vinci scope to Wallace | Redaction of incriminating content |
| `email3_inconsistency_b.mbox` | Chen forwards the same passage to Gill — unreviewed | Cross-document consistency check |
| `email4_pii.mbox` | Wallace sends SSN + offshore bank details to Belford | PII detection (SSN, account number, routing, SWIFT) |
| `email5_overbroad.mbox` | Gill's access log with one buried legal sentence | Overbroad redaction prevention |

### `irrelevant/` — noise documents

Load alongside `client/`. The AI must classify all three as **Irrelevant**.

| File | Why irrelevant | Edge case |
|---|---|---|
| `golf_invite.mbox` | Benson scheduling golf — no case connection | None |
| `lunch_order.mbox` | All-staff lunch order — no case connection | None |
| `hawaii_vacation.mbox` | Wallace on vacation — no operational content | **Subtle:** Wallace is a defendant. System must reason from content, not just custodian name. |

### `opposing/` — DOJ production

| File | What it is |
|---|---|
| `DOJ_EmailFile.mbox` | Internal Ellingson emails seized by DOJ: board meeting records, legal risk assessment (with lawsuit probability/damage estimates), PR strategy, system status reports |

---

## Verifying the pipeline works

See [`EXPECTED_OUTPUTS.md`](EXPECTED_OUTPUTS.md) for the ground truth — what the AI must output for each document.

Key things to verify:
- `irrelevant/hawaii_vacation.mbox` → classified **Irrelevant** (content-based, not custodian-based)
- `synthetic/email1` → privilege flagged + **waived** (non-lawyer CC'd)
- `synthetic/email2` → Section 1 produced, Section 2 redacted only
- `synthetic/email3a` + `email3b` → consistency checker fires
- `synthetic/email4` → SSN + account + routing + SWIFT all redacted
- `synthetic/email5` → one sentence redacted, not the whole email

---

## Data sources

- **EMC-2** (`client/` + `opposing/`) — fully synthetic dataset by [@jur1st](https://github.com/jur1st/EMC-2), CC-BY-4.0, ~204 documents, inspired by the 1995 film Hackers
- **Synthetic emails** (`synthetic/`) — hand-crafted for this demo to cover redaction edge cases not present in EMC-2
