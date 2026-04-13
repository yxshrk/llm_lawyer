# Demo Guide

## The Story

Ellingson Mineral Company has been hit by an insider cyberattack. Eugene Belford, Head of IT Security, planted the Da Vinci virus to siphon $25.1M from the company's financial systems — with inside help from VP Operations Margo Wallace. CEO Hal Benson is cooperating with investigators but needs legal counsel to protect privileged communications while producing thousands of documents. The DOJ has their own production of seized Ellingson emails.

LexAgent runs both sides: helping Ellingson's lawyers protect what should be protected, and attacking the DOJ's production for what they got wrong.

For the full narrative and stakeholder profiles, see `data/NARRATIVE.md`.

---

## Redaction Rules

These are the categories LexAgent flags. Knowing these helps frame each demo moment to judges.

| Category | What it protects | What it looks like |
|---|---|---|
| **Attorney-client privilege** | Confidential communications between a lawyer and client for the purpose of legal advice | Email from lawyer to client (or vice versa) discussing legal strategy, exposure, what to say/not say |
| **Work product doctrine** | Documents prepared by lawyers in anticipation of litigation | Legal memos, risk assessments, strategy notes drafted by counsel after a dispute arises |
| **Trade secret** | Proprietary technical or business information that would harm the company if disclosed | Virus code, internal algorithms, financial models, access credentials |
| **PII** | Personal identifying information | SSN, bank account numbers, routing numbers, passport numbers |

**Key edge cases the demo surfaces:**
- Privilege is **waived** when a non-lawyer is CC'd on an attorney-client communication (Email 1)
- A single email can be **partially privileged** — factual content stays, legal advice is redacted (Email 2 + Email 5)
- **Consistency matters** — the same passage must be treated the same way across all documents or the redaction set is indefensible (Email 3)
- **PII is always redacted** regardless of context — it is not privileged, just sensitive (Email 4)

---

## Dataset

### Source
EMC-2 by jur1st — https://github.com/jur1st/EMC-2
Fully synthetic, CC-BY-4.0, ~204 documents, October 15-25 1995 timeline.

### Client pipeline (`data/client/`)

| File | Custodian | Why included |
|---|---|---|
| `ebelford.mbox` | Eugene Belford | Primary defendant — planning emails, ROT13 hacker comms, Oct 17 confession |
| `hbenson.mbox` | Hal Benson (CEO) | Victim — board comms, receives all the legal/factual mixed content |
| `schen.mbox` | Sarah Chen (CTO) | Whistleblower — detection timeline, FBI contact, forwarded confession (inconsistency source) |
| `rgill.mbox` | Richard Gill (IT) | Witness — access log summary with one buried legal observation (overbroad target) |
| `mwallace.mbox` | Margo Wallace | Co-conspirator — cover story emails, coordination with Belford's offshore account |
| `Da_Vinci_virus_analys.txt` | — | Technical evidence — obviously relevant |
| `plague_voicemail_transcript.txt` | — | Obviously relevant |
| `memo_10101995.txt` | — | Obviously relevant |

Also load all 5 synthetic emails from `data/synthetic/`.

### Opposing counsel pipeline (`data/opposing/`)

| File | What it is |
|---|---|
| `DOJ_EmailFile.mbox` | Internal Ellingson emails seized by DOJ — board meeting, legal risk assessment with probability/damage estimates, PR strategy, system status reports |

**Keep strictly separate from client pipeline.**

---

## Synthetic Emails (`data/synthetic/`)

Five emails covering every redaction category and demo moment EMC-2 doesn't provide on its own.

| File | Scenario | Redaction category | Demo moment |
|---|---|---|---|
| `email1_privilege_waiver.mbox` | Belford emails attorney re: legal strategy — CC's Margo Wallace | Attorney-client privilege → **waived** | Q&A challenge: "non-lawyer CC'd, privilege likely waived" |
| `email2_mixed_content.mbox` | Legal team to Benson — half factual access log summary, half legal advice | Partial privilege | AI redacts Section 2 only, leaves Section 1 visible — surgical precision |
| `email3_inconsistency_a.mbox` | Belford confesses full Da Vinci scope to Wallace | Harmful/incriminating content | Redacted in Belford's mailbox |
| `email3_inconsistency_b.mbox` | Chen forwards same passage to Gill — unreviewed, not yet redacted | — | Q&A consistency checker flags: same passage treated differently across documents |
| `email4_pii.mbox` | Wallace sends offshore account + SSN to Belford | PII (SSN, account number, routing number) | AI flags PII regardless of context — always redacted |
| `email5_overbroad.mbox` | Gill to Benson — access log summary with one sentence of legal observation buried at the end | Overbroad redaction risk | AI should redact only the final observation, not the whole email |

---

## Suggested Demo Flow

1. **Relevancy filtering** — show obvious relevant docs (Belford emails, Da Vinci analysis) vs. obvious noise. Fast, judges get it.
2. **Redaction: privilege waiver** (`email1`) — AI flags privilege, Q&A immediately challenges the CC. Wow moment.
3. **Redaction: mixed content** (`email2`) — show surgical redaction. Section 1 stays visible, Section 2 goes.
4. **Redaction: PII** (`email4`) — quick, clean. Shows the third redaction category.
5. **Redaction: overbroad** (`email5`) — AI redacts one sentence, not the whole email. Shows precision.
6. **Q&A consistency catch** (`email3a` + `email3b`) — trigger Q&A, show the cross-document flag. Best closer before opposing counsel.
7. **Opposing counsel review** — upload DOJ folder. Challenge their redactions + argument gap analysis. End on this.

---

## What to Skip

IRC logs, hacker custodians (Libby, Murphy, Mack, Rivera), journalist emails, traffic reports, jur1st mailbox.
Too noisy. Confuses the story. The judge won't follow it.

---

## Pre-Demo Checklist

- [ ] EMC-2 files in `data/client/` and `data/opposing/` (already included in this branch)
- [ ] Synthetic emails loaded into client pipeline
- [ ] DOJ pipeline ingested and smoke-tested — know which 2-3 emails produce the best output
- [ ] Demo flow rehearsed end-to-end at least once
- [ ] Fallback: pre-compute at least Steps 2 and 6 in case of live model latency
