# Expected Outputs

Ground truth for the demo dataset. Written before the model runs — not adjusted to match what the model does.

Engineers use this to verify the pipeline is working correctly. Each entry defines what LexAgent **must** output for a given document.

---

## Pipeline 1 — Relevancy Filtering

### Expected: RELEVANT

| File | Expected classification | Reasoning the AI should give |
|---|---|---|
| `client/ebelford.mbox` | **Relevant** | Contains communications from primary defendant discussing Da Vinci deployment, co-conspirator coordination, and legal exposure |
| `client/mwallace.mbox` | **Relevant** | Contains co-conspirator coordination emails and operational cover communications directly tied to the incident |
| `client/schen.mbox` | **Relevant** | Contains incident detection timeline, technical analysis, FBI contact, and the forwarded Belford confession |
| `client/hbenson.mbox` | **Relevant** | Contains CEO crisis response communications, legal team memos, and board meeting records |
| `client/rgill.mbox` | **Relevant** | Contains access log summary identifying Wallace credential session and Belford's access to cron config |
| `client/Da_Vinci_virus_analys.txt` | **Relevant** | Direct technical analysis of the virus at the centre of the case |
| `client/plague_voicemail_transcript.txt` | **Relevant** | Voicemail related to the incident |
| `client/memo_10101995.txt` | **Relevant** | Internal memo within the case date range |
| `synthetic/email1_privilege_waiver.mbox` | **Relevant** | Attorney-client communication about legal strategy directly related to Belford's exposure |
| `synthetic/email2_mixed_content.mbox` | **Relevant** | Legal team memo to CEO about the Da Vinci incident |
| `synthetic/email3_inconsistency_a.mbox` | **Relevant** | Belford confessing full scope of Da Vinci to co-conspirator |
| `synthetic/email3_inconsistency_b.mbox` | **Relevant** | Chen forwarding Belford's confession — key evidence |
| `synthetic/email4_pii.mbox` | **Relevant** | Wallace transmitting offshore banking details — financial evidence |
| `synthetic/email5_overbroad.mbox` | **Relevant** | Access log summary identifying Wallace session and Belford's cron access |

### Expected: IRRELEVANT

| File | Expected classification | Reasoning the AI should give |
|---|---|---|
| `irrelevant/golf_invite.mbox` | **Irrelevant** | Social scheduling with no connection to Da Vinci incident, Belford, Wallace, or any identified legal issue |
| `irrelevant/lunch_order.mbox` | **Irrelevant** | Administrative all-staff communication with no case connection |
| `irrelevant/hawaii_vacation.mbox` | **Irrelevant** | Personal communication from Wallace predating the incident; content has no operational or legal relevance despite custodian being a defendant |

> **Note on the Wallace vacation email:** A correctly functioning system classifies this as Irrelevant based on *content*, not custodian identity. If the system marks it Relevant solely because Wallace is a defendant, that is a false positive — flag it.

---

## Pipeline 1 — Redaction Engine

### Synthetic emails: expected redactions

**`email1_privilege_waiver.mbox`**
- Expected category: `attorney-client privilege` → **WAIVED**
- Expected confidence: `low` (waiver present)
- Expected redaction: none recommended — privilege is waived, document should be produced
- Expected Q&A challenge: *"A non-lawyer (Margo Wallace) was CC'd on this communication. Attorney-client privilege is likely waived as to all parties on this thread. On what basis do you claim this communication is protected?"*
- Risk flag: *"Non-lawyer CC'd. Privilege waiver likely. High vulnerability if challenged."*

**`email2_mixed_content.mbox`**
- Expected: **partial redaction**
- Section 1 (factual summary — access logs, timestamps, file writes): `NOT redacted`
- Section 2 (recommended actions — do not speak to investigators, retain outside counsel): `REDACTED` as `attorney-client privilege`
- Expected confidence: `high` for Section 2
- Wrong output to flag: redacting the entire email. That is an overbroad redaction.

**`email3_inconsistency_a.mbox`**
- Expected category: `harmful/incriminating content` (not attorney-client privilege — this is a co-conspirator communication)
- Expected: `REDACTED`
- Expected confidence: `high`

**`email3_inconsistency_b.mbox`**
- Expected: flagged as `Uncertain` or `Relevant — unredacted`
- **This email must trigger the Q&A consistency checker** — the identical Da Vinci passage appears in email3a (redacted) and email3b (not redacted)
- Expected Q&A output: *"The following passage appears unredacted in schen → rgill (Oct 21) but redacted in ebelford → mwallace (Oct 17). Inconsistent treatment before production: [passage]. Recommended action: review and align."*

**`email4_pii.mbox`**
- Expected category: `PII`
- Expected redactions:
  - `412-67-3901` (SSN) → **REDACTED**
  - `0094-772-883-01` (account number) → **REDACTED**
  - `026-009-593` (ABA routing) → **REDACTED**
  - `FNONBNAA` (SWIFT code) → **REDACTED**
- Expected: name and email address NOT redacted (not PII in this context)
- Expected confidence: `high`

**`email5_overbroad.mbox`**
- Expected: **partial redaction — one sentence only**
- Redact: *"You should not repeat this last observation to anyone without speaking to counsel first."*
- Do NOT redact: everything else (factual access log summary)
- Expected confidence: `medium` (single embedded legal instruction)
- Wrong output to flag: redacting the full email or the entire final paragraph. That is an overbroad redaction — demonstrate Q&A catching it.

---

## Pipeline 3 — Opposing Counsel Review

### `opposing/DOJ_EmailFile.mbox` — expected challenges

The DOJ production contains internal Ellingson documents. Key expected outputs:

| Document in DOJ production | Expected challenge type | What AI should surface |
|---|---|---|
| Legal team risk memo (potential_lawsuits.csv) | **Gap / self-incrimination** | Ellingson's own lawyers rated shareholder lawsuits at 75% probability, $50M exposure — DOJ has Ellingson's internal risk assessment. Flag as argument gap: Ellingson cannot credibly dispute knowledge of legal exposure. |
| Board meeting agenda (board_meeting_agenda.txt) | **Argument gap** | Agenda explicitly lists "Employee liability (Eugene Belford)" — board knew about Belford's potential liability at the Oct 20 meeting. |
| PR strategy draft | **Argument gap** | PR team was already managing narrative while investigation was active — could be used to argue coordinated messaging |

---

## How to use this file

1. Run each document through the pipeline
2. Compare actual output against expected classification, redaction, and reasoning
3. Flag any deviation — especially:
   - False positives on irrelevant docs (especially Wallace vacation email)
   - Overbroad redaction on email2 or email5 (whole email vs partial)
   - Missing privilege waiver flag on email1
   - Missing consistency catch across email3a + email3b
   - Missing PII fields on email4
