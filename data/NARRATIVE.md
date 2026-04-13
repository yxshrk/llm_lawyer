# Case Narrative: Ellingson Mineral Company v. Belford et al.

## The Case in One Sentence

Eugene Belford, Head of IT Security at Ellingson Mineral Company, planted the Da Vinci virus to siphon $25.1M from Ellingson's financial systems, with the help of inside co-conspirator Margo Wallace — and was caught when Acting CTO Sarah Chen detected the attack and contacted the FBI.

---

## Timeline

| Date | Event |
|---|---|
| Aug 17, 1995 | Belford contacts Phantom Phreak (external hacker) via ROT13-encrypted email — oil tanker routing scheme discussed |
| Oct 2, 1995 | Belford sends routine security update to IT team — cover for his own access patterns |
| Oct 4, 1995 | Belford tells Wallace "the package is ready" — Da Vinci is compiled |
| Oct 10, 1995 | Belford submits resignation — two-week notice, plans to flee after extraction |
| Oct 12, 1995 | Belford provisions Wallace's Gibson access credentials |
| Oct 15, 1995 | Wallace accesses Gibson at 11:42 PM, plants Da Vinci virus (3 file writes, 47-minute session) |
| Oct 16, 1995 | Da Vinci executes at 2:00 AM in nightly batch — runs undetected 18 hours |
| Oct 16, 1995 | Chen detects anomalous transaction patterns at 8:14 PM — 4,182 transactions affected, $1,047.23 diverted |
| Oct 17, 1995 | Secret Service seizes the Gibson — forensic imaging begins |
| Oct 17, 1995 | Belford emails Wallace: "They have the Gibson. Here's what they'll find." — confesses full scope |
| Oct 19, 1995 | Belford contacts his attorney Sterling — legal strategy discussion, CC's Wallace (privilege waiver) |
| Oct 19, 1995 | Benson calls emergency board meeting. Legal team sends risk memo. Chen contacts FBI. |
| Oct 20, 1995 | Wallace emails Belford: "The system's acting up. IT is asking questions." |
| Oct 20, 1995 | Emergency board meeting. PR strategy discussed. |
| Oct 21, 1995 | Chen forwards Belford's confession email to Gill — unreviewed, unredacted |

---

## Stakeholders

### Eugene Belford — "The Plague"
**Role:** Head of IT Security, Ellingson Mineral Company  
**Position:** Defendant (primary)  
**What he did:** Designed and planted the Da Vinci virus. Provisioned Wallace's access credentials. Coordinated with outside hackers on a separate oil tanker routing scheme. Resigned and planned to flee.  
**Key documents:** ebelford.mbox — contains planning emails to Wallace, ROT13 communication with Phantom Phreak, and the smoking gun confession email (Oct 17) describing the full scope of Da Vinci.  
**Legal exposure:** Computer fraud, wire fraud, conspiracy, theft by taking.

---

### Margo Wallace
**Role:** VP Operations, Ellingson Mineral Company  
**Position:** Defendant (co-conspirator)  
**What she did:** Physically accessed the Gibson and planted the Da Vinci executable. Used credentials provisioned by Belford. Maintained cover story ("routine maintenance"). Communicated with Belford via his offshore email.  
**Key documents:** mwallace.mbox — contains operational cover emails to Benson, and incriminating coordination emails to Belford's offshore account.  
**Legal exposure:** Computer fraud, conspiracy, accessory after the fact.

---

### Hal Benson
**Role:** CEO, Ellingson Mineral Company  
**Position:** Victim / Witness  
**What he did:** Managed crisis response. Called emergency board meeting. Received legal and PR advice. Preserved documents.  
**Key documents:** hbenson.mbox — contains board communications, legal team's risk assessment (privileged), PR strategy, and Chen's technical briefings. The legal/factual split email (email2_mixed_content) is addressed to him.  
**Legal exposure:** Minimal — primarily a witness. Potential exposure if he made false statements to investigators.

---

### Dr. Sarah Chen
**Role:** Acting CTO, Ellingson Mineral Company  
**Position:** Key witness (whistleblower)  
**What she did:** Detected anomalous transaction patterns. Led technical investigation. Contacted FBI. Identified Belford as likely suspect in preliminary analysis. Forwarded Belford's confession email to Gill (the inconsistency).  
**Key documents:** schen.mbox — contains detection timeline, technical reports, FBI contact, and the forwarded confession email that creates the consistency problem.  
**Legal exposure:** None — she reported the crime.

---

### Richard Gill
**Role:** IT team member, Ellingson  
**Position:** Witness  
**What he did:** Assisted with containment. Received Chen's forwarded documents.  
**Key documents:** rgill.mbox  
**Legal exposure:** None.

---

### Kate Libby ("Acid Burn"), Dade Murphy ("Zero Cool"), Jennifer Mack ("Cereal Killer"), Alex Rivera
**Role:** External hackers / Phantom Phreak network  
**Position:** Peripheral — connected to Belford's external scheme  
**Note:** Peripheral to the core legal case. Excluded from demo pipeline — too noisy.

---

### US Department of Justice
**Position:** Prosecuting party (opposing counsel in the demo)  
**What they have:** Seized internal Ellingson communications — Benson's board emails, Chen's technical reports, legal team risk assessments, PR strategy. Also have financial data (potential_lawsuits.csv with Ellingson's own internal probability estimates).  
**Demo role:** Their production is used for the Opposing Counsel Review feature — we challenge their redactions and find argument gaps.

---

## What Ellingson's Lawyers Are Trying to Prove

**Client objective:** Minimize Benson's exposure. Establish that Belford acted alone (or with Wallace) without Benson's knowledge. Preserve privilege over legal strategy communications. Challenge DOJ's production for overbroad redactions and argument gaps.

**Key documents to protect:**
- Legal team's risk memo to Benson (email2 — mixed content, partial privilege)
- Belford-Sterling attorney communication (email1 — waived by Wallace CC)
- Any board communications containing legal strategy

**Key documents that hurt:**
- Belford's Oct 17 confession email to Wallace (email3a) — establishes full criminal scope
- Wallace's coordination emails to Belford's offshore account — co-conspirator liability
- The unredacted forwarded confession (email3b) — production inconsistency

---

## Demo Narrative for Judges

> "Ellingson Mineral Company has been hit by an insider cyberattack. The CEO is cooperating with investigators, but needs to protect privileged legal communications while producing thousands of documents. Opposing counsel — the DOJ — has their own production of seized Ellingson emails. LexAgent runs both pipelines: helping Ellingson's lawyers protect what should be protected, and attacking the DOJ's production for what they got wrong."
