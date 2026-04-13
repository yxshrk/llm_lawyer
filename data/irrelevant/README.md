# Irrelevant Documents

Obvious noise for the relevancy filtering demo. Load these alongside client pipeline documents.

The AI should classify these as **Irrelevant** — they have no connection to the Da Vinci incident, Belford, Wallace, or any legal issue in the case.

| File | Why it's irrelevant |
|---|---|
| `golf_invite.mbox` | Benson scheduling golf with the board — no case connection |
| `lunch_order.mbox` | All-staff lunch order — no case connection |
| `hawaii_vacation.mbox` | Wallace emailing a colleague about her vacation — predates the incident, no operational content |

**Demo moment:** After loading, relevancy filter should immediately classify these as Irrelevant with plain-English reasoning ("No connection to Da Vinci incident, Belford/Wallace credentials, or any identified legal issue").

Note: the Wallace vacation email is subtle — she's a defendant, so a less precise system might flag it as Relevant just because of her name. LexAgent should reason about content, not just custodian identity.
