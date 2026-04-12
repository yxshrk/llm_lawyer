# Demo Guide

## Dataset: Enron Mail Corpus (EMC-2)

**Why EMC-2:**
- Judges immediately understand the story (Ellingson Mineral, Da Vinci virus, cover-up)
- Clear relevant vs. noise split — good for relevancy filtering wow moment
- DOJ folder is a ready-made opposing counsel production
- CC-BY-4.0, ~200 documents, October 15-25 1995 timeline

**Known weakness:**
Privilege is too obvious. Don't lead with redaction using vanilla EMC-2 docs — the ambiguity isn't there. The 3 synthetic emails below fix this.

---

## Demo data

Download EMC-2 from https://github.com/jur1st/EMC-2 and place files as shown.

### Client pipeline (`data/client/`)

| File | Source path in EMC-2 |
|---|---|
| `hbenson.mbox` | `custodians/Benson, Hal/` |
| `schen.mbox` | `custodians/Chen, Sarah/` |
| `rgill.mbox` | `custodians/Gill, Richard/` |
| `ebelford.mbox` | `custodians/Belford, Eugene/` |
| `mwallace.mbox` | `custodians/Wallace, Margo/` |
| `Da_Vinci_virus_analys.txt` | `edocs_unzipped_metadata_bonked/` |
| `plague_voicemail_transcript.txt` | `edocs_unzipped_metadata_bonked/` |
| `memo_10101995.txt` | `edocs_unzipped_metadata_bonked/` |

Also load all 3 synthetic emails from `data/synthetic/` into the client pipeline.

### Opposing counsel pipeline (`data/opposing/`)

| File | Source path in EMC-2 |
|---|---|
| `DOJ_EmailFile.mbox` | `custodians/US-DOJ/` |
| `edocs.zip` | `custodians/US-DOJ/` |

**Skip everything else** — IRC logs, hacker custodians, journalist, traffic reports, peripheral chat logs. Too noisy, confuses the story.

---

## Synthetic emails (`data/synthetic/`)

These fix the redaction gap in EMC-2. Each targets a specific demo moment.

| File | Scenario | Demo moment |
|---|---|---|
| `email1_privilege_waiver.mbox` | Belford emails his attorney about legal strategy — CC's Margo Wallace (non-lawyer co-conspirator) | AI flags attorney-client privilege → Q&A immediately challenges: "non-lawyer CC'd, privilege likely waived" |
| `email2_mixed_content.mbox` | Legal team sends Benson an email that's half factual access log summary, half legal advice | AI redacts only the legal advice section, leaves the factual section untouched — shows surgical precision |
| `email3_inconsistency_a.mbox` + `email3_inconsistency_b.mbox` | Same Da Vinci passage appears in Belford→Wallace email (should be redacted) and a Chen→Gill forward (slipped through unredacted) | Q&A consistency checker flags the inconsistency across documents before production |

---

## Suggested demo flow

1. **Relevancy filtering** — show obvious relevant docs (Belford emails, Da Vinci analysis) vs. obvious noise (golf invite, vacation, lunch order). Fast, clear, judges get it immediately.
2. **Redaction — privilege waiver** (`email1`) — AI flags privilege, Q&A challenges the CC. This is the wow moment.
3. **Redaction — mixed content** (`email2`) — show the surgical redaction. Half the email stays visible.
4. **Q&A consistency catch** (`email3`) — trigger Q&A, show the cross-document flag.
5. **Opposing counsel review** — upload DOJ folder, show redaction challenges + argument gap analysis.
