# Case Context Memo
**Matter ID:** EMC-DEMO-001
**Matter:** Ellingson Mineral Company — Da Vinci Incident
**Prepared by:** Hal Benson (CEO) via counsel
**Date:** October 19, 1995

---

> **How this is used:** This memo is injected as system-level context into every LLM call across all three pipelines. It tells the AI what the case is about, who the parties are, what to look for, and what rules apply. All relevancy filtering, redaction suggestions, Q&A challenges, and opposing counsel analysis are scoped to this context.

---

## Case Summary

Ellingson Mineral Company suffered an insider cyberattack in October 1995. Eugene Belford, Head of IT Security, planted the Da Vinci virus — a salami-slicing program designed to divert $0.25 per financial transaction to an offshore account. The virus was physically deployed by co-conspirator Margo Wallace (VP Operations) using credentials provisioned by Belford. The attack ran undetected for 18 hours before Acting CTO Sarah Chen identified anomalous transaction patterns and contacted the FBI. The Gibson supercomputer was seized by the Secret Service on October 17. Total diverted before detection: $1,047.23. Total projected yield if undetected: $25.1M over 18 months.

## Parties

| Role | Name |
|---|---|
| Client | Ellingson Mineral Company (via CEO Hal Benson) |
| Primary defendant | Eugene Belford |
| Co-conspirator | Margo Wallace |
| Investigators | US Secret Service, FBI Cybercrime Division, US DOJ |
| Defense attorney (Belford) | Richard Sterling, Sterling & Associates |
| Key fact witness | Dr. Sarah Chen (Acting CTO) |

## Jurisdiction

Federal — Southern District of New York

## Key Legal Issues

- Computer fraud and unauthorized access (18 U.S.C. § 1030)
- Wire fraud (18 U.S.C. § 1343)
- Conspiracy
- Trade secret misappropriation
- Attorney-client privilege scope and waiver
- CEO/officer liability — what Benson knew and when

## Privilege Rules

Standard federal common law attorney-client privilege applies. No specific privilege agreements or standing orders. Preservation obligations triggered October 17, 1995 upon Secret Service seizure of the Gibson.

## Key Custodians

| Custodian | Role | Significance |
|---|---|---|
| Eugene Belford | Head of IT Security (defendant) | Primary perpetrator — all communications highly relevant |
| Margo Wallace | VP Operations (co-conspirator) | Physically planted virus — coordination emails with Belford critical |
| Hal Benson | CEO (client) | Receives privileged legal advice — mixed factual/legal content expected |
| Sarah Chen | Acting CTO (fact witness) | Detected the attack — technical investigation chain |
| Richard Gill | IT Security (fact witness) | Access log analysis — factual only |

## Key Date Range

**October 1 – October 25, 1995**

Critical dates:
- **Oct 12** — Belford provisions Wallace's Gibson access credentials
- **Oct 15, 11:42 PM** — Wallace accesses Gibson, plants Da Vinci (47-min session)
- **Oct 16, 2:00 AM** — Da Vinci executes in nightly batch
- **Oct 16, 8:14 PM** — Chen detects anomaly, 4,182 transactions affected
- **Oct 17** — Secret Service seizes Gibson; preservation obligations triggered
- **Oct 19** — Emergency board meeting; Belford contacts attorney (privilege waiver risk)

## Custom Flagging Rules

1. Flag all communications referencing: `Da Vinci`, `salami`, `Gibson`, `offshore`, `Project Da Vinci`
2. Flag any email where Eugene Belford is sender or recipient
3. Flag all emails to/from `offshore-secure.net` domain
4. Any communication discussing Belford's system access or credential provisioning is highly relevant
5. Communications between Benson and legal team: apply privilege review carefully — mixed factual/legal content is expected and must be partially redacted, not wholesale redacted

## Document Formats

Source documents are `.mbox` (email archives per custodian) and `.txt` (standalone documents). Both formats must be supported by the ingestion pipeline.
