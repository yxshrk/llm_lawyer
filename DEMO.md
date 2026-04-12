# Demo Guide

## Dataset: Enron Mail Corpus (EMC-2)

### Why EMC-2

- Narrative judges immediately understand (Belford emails, Da Vinci analysis)
- Clear relevant vs. noise split — good for showing relevancy filtering
- DOJ folder is a ready-made opposing counsel production

### Known weakness

Privilege is too obvious. Redaction "wow moment" doesn't exist in this dataset — ambiguous privilege calls aren't here. Don't lead with redaction in the demo.

---

## What to load

### Client pipeline — load these only

| File | Why |
|---|---|
| `hbenson.mbox` | Key custodian |
| `schen.mbox` | Key custodian |
| `rgill.mbox` | Key custodian |
| `ebelford.mbox` | Core narrative — Belford emails |
| `mwallace.mbox` | Key custodian |
| `Da_Vinci_virus_analys.txt` | Obvious relevant doc |
| `plague_voicemail_transcript.txt` | Obvious relevant doc |
| `memo_10101995.txt` | Obvious relevant doc |

### Opposing counsel pipeline

| File | Why |
|---|---|
| `DOJ_EmailFile.mbox` | Ready-made opposing production |
| `edocs.zip` | Supporting opposing docs |

---

## What to skip

IRC logs, hacker custodians, journalist emails, traffic reports, peripheral chat logs.

**Why:** Too noisy. Confuses the demo story. The judge won't follow it.

---

## Demo flow

1. **Relevancy filtering** — upload client pipeline, show obvious relevant (Belford, Da Vinci) vs. obvious noise (golf invite, vacation, lunch order)
2. **Opposing counsel review** — upload DOJ folder, show redaction challenges + argument gap analysis
3. **Skip** leading with redaction — privilege is too clean to be impressive with this dataset
