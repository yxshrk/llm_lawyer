import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import MDEditor from "@uiw/react-md-editor";
import {
  api,
  type Case,
  type CaseDocument,
  type Email,
  type Memory,
} from "../lib/api";
import { cn } from "../lib/utils";
import { EmailModal } from "../components/EmailModal";
import { GmailConnector } from "../components/GmailConnector";
import { UploadStepper } from "../components/UploadStepper";
import { Loader } from "../components/Loader";
import { QaPanel } from "../components/QaPanel";
import {
  ActivityConsole,
  useActivityLog,
  type ActivityEvent,
} from "../components/ActivityConsole";
import type { AuditEvent } from "../lib/api";

type TopTab = "ours" | "opposing" | "context" | "qa" | "history" | "consolidated";
type PipelineSub = "documents" | "emails";
type ProductionType = "own" | "opposing";

// Renamed per PRD §4.3 Case Context Memo fields.
const MEMORY_KINDS: Array<{ kind: string; label: string; hint: string }> = [
  { kind: "case_summary", label: "Case summary", hint: "What the case is about (2–5 sentences)." },
  { kind: "parties", label: "Parties", hint: "Client, opposing party, key third parties." },
  { kind: "jurisdiction", label: "Jurisdiction", hint: "Federal or state; if state, which one." },
  { kind: "key_legal_issues", label: "Key legal issues", hint: "Primary claims or defences (e.g. breach, trade secret)." },
  { kind: "privilege_rules", label: "Privilege rules", hint: "Privilege agreements or standing orders that apply." },
  { kind: "key_custodians", label: "Key custodians", hint: "Individuals whose documents are most relevant." },
  { kind: "key_date_range", label: "Key date range", hint: "Time period the case centres on." },
  { kind: "custom_rules", label: "Custom rules", hint: "Extra instructions (e.g. 'flag emails mentioning Project X')." },
];

export default function CasePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [topTab, setTopTab] = useState<TopTab>("ours");
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [docs, setDocs] = useState<CaseDocument[]>([]);
  const [emails, setEmails] = useState<Email[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadName, setUploadName] = useState<string | undefined>();
  const { make: makeEvent } = useActivityLog();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [consoleCollapsed, setConsoleCollapsed] = useState(true);
  const [anyRunning, setAnyRunning] = useState(false);
  const pushEvent = (partial: Omit<ActivityEvent, "id" | "t">) =>
    setEvents((prev) => [...prev, makeEvent(partial)]);
  const fileRef = useRef<HTMLInputElement>(null);
  const pendingUploadType = useRef<ProductionType>("own");
  const navigate = useNavigate();

  const refresh = async () => {
    if (!caseId) return;
    const [c, d, e, m] = await Promise.all([
      api.getCase(caseId),
      api.listCaseDocuments(caseId),
      api.listEmails(caseId),
      api.listMemories(caseId),
    ]);
    setCaseData(c);
    setDocs(d);
    setEmails(e);
    setMemories(m);
  };

  useEffect(() => {
    refresh();
  }, [caseId]);

  const onUpload = async (file: File, productionType: ProductionType) => {
    if (!caseId) return;
    setUploading(true);
    setUploadName(file.name);
    try {
      const d = await api.uploadDocumentWithType(file, caseId, productionType);
      await new Promise((r) => setTimeout(r, 400));
      navigate(`/cases/${caseId}/documents/${d.id}`);
    } catch (e: any) {
      alert("Upload failed: " + e.message);
    } finally {
      setUploading(false);
    }
  };

  if (!caseData) return <Loader label="Loading case…" />;

  const ownDocs = docs.filter((d) => (d.production_type ?? "own") === "own");
  const opposingDocs = docs.filter((d) => d.production_type === "opposing");
  const ownEmails = emails.filter((e) => (e.production_type ?? "own") === "own");
  const opposingEmails = emails.filter((e) => e.production_type === "opposing");

  const tabs: Array<{ id: TopTab; label: string; count?: number; hint?: string }> = [
    { id: "ours", label: "🛡️ Our Pipeline", count: ownDocs.length + ownEmails.length },
    { id: "opposing", label: "⚔️ Opposing Counsel", count: opposingDocs.length + opposingEmails.length },
    { id: "context", label: "🧠 Case Context", count: memories.length },
    { id: "qa", label: "⚔️ Q&A Rehearsal" },
    { id: "history", label: "📜 Audit Trail" },
    { id: "consolidated", label: "📑 Consolidated Case" },
  ];

  const runRelevancy = async () => {
    if (!caseId) return;
    setAnyRunning(true);
    pushEvent({ kind: "info", label: "Relevancy filter starting", badge: "REL" });
    try {
      for await (const ev of api.streamRelevancy(caseId)) {
        if (ev.type === "started") {
          pushEvent({
            kind: "info",
            label: "Query embedded (case memory)",
            detail: ev.query_preview,
            badge: "REL",
          });
        } else if (ev.type === "stage") {
          pushEvent({
            kind: "stage",
            label: `Stage: ${ev.stage}${ev.doc_count != null ? ` (${ev.doc_count} docs)` : ""}`,
            badge: "REL",
          });
        } else if (ev.type === "doc") {
          pushEvent({
            kind: "result",
            label: `[${ev.label.toUpperCase()}] ${ev.score.toFixed(2)} · ${ev.title}`,
            detail: ev.reasoning,
            badge: "REL",
          });
        } else if (ev.type === "done") {
          pushEvent({ kind: "done", label: `Relevancy done (${ev.total ?? 0} docs)`, badge: "REL" });
        } else if (ev.type === "error") {
          pushEvent({ kind: "error", label: ev.message, badge: "REL" });
        }
      }
    } catch (e: any) {
      pushEvent({ kind: "error", label: e?.message ?? "Relevancy stream failed", badge: "REL" });
    } finally {
      setAnyRunning(false);
      await refresh();
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <UploadStepper active={uploading} fileName={uploadName} />
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onUpload(f, pendingUploadType.current);
          e.currentTarget.value = "";
        }}
      />

      <div className="mb-6">
        <Link to="/" className="text-xs text-muted hover:text-ink">
          ← All cases
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">
          {caseData.name}
        </h1>
        <div className="text-sm text-muted">
          {caseData.client_name && `Client: ${caseData.client_name}`}
          {caseData.matter_type && ` · ${caseData.matter_type}`}
        </div>
        {caseData.description && (
          <p className="text-sm text-muted mt-2 max-w-3xl">
            {caseData.description}
          </p>
        )}
      </div>

      <div className="flex gap-1 border-b border-line mb-6">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTopTab(t.id)}
            className={cn(
              "px-4 py-3 text-sm border-b-2 -mb-px transition",
              topTab === t.id
                ? "border-ink text-ink font-medium"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t.label}
            {t.count !== undefined && (
              <span className="ml-2 text-xs text-muted">({t.count})</span>
            )}
          </button>
        ))}
      </div>

      {topTab === "ours" && (
        <PipelineTab
          side="own"
          caseId={caseId!}
          docs={ownDocs}
          emails={ownEmails}
          onUploadClick={() => {
            pendingUploadType.current = "own";
            fileRef.current?.click();
          }}
          onChanged={refresh}
          onRunRelevancy={runRelevancy}
        />
      )}
      {topTab === "opposing" && (
        <PipelineTab
          side="opposing"
          caseId={caseId!}
          docs={opposingDocs}
          emails={opposingEmails}
          onUploadClick={() => {
            pendingUploadType.current = "opposing";
            fileRef.current?.click();
          }}
          onChanged={refresh}
        />
      )}
      {topTab === "context" && (
        <CaseContextTab
          caseId={caseId!}
          memories={memories}
          onChanged={refresh}
        />
      )}
      {topTab === "consolidated" && <ConsolidatedTab caseId={caseId!} />}
      {topTab === "qa" && (
        <QaPanel
          caseId={caseId!}
          pushEvent={pushEvent}
          setAnyRunning={setAnyRunning}
        />
      )}
      {topTab === "history" && <AuditTab caseId={caseId!} />}
      <ActivityConsole
        title="🧠 AI activity"
        events={events}
        running={anyRunning}
        collapsed={consoleCollapsed}
        onToggle={() => setConsoleCollapsed((v) => !v)}
        onClear={() => setEvents([])}
      />
    </div>
  );
}

function DocRow({
  d,
  i,
  caseId,
}: {
  d: CaseDocument;
  i: number;
  caseId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasReason = !!d.relevancy_reasoning;
  const del = async () => {
    if (!confirm(`Delete "${d.title}"? This also deletes its chunks, redactions, and challenges.`)) return;
    await fetch(`${(import.meta.env.VITE_API_URL ?? "http://localhost:8000")}/documents/${d.id}`, {
      method: "DELETE",
    });
    window.location.reload();
  };
  return (
    <>
      <tr className="hover:bg-stone-50">
        <td className="px-4 py-2 text-muted align-top">{i + 1}</td>
        <td className="px-4 py-2 align-top">
          <Link
            to={`/cases/${caseId}/documents/${d.id}`}
            className="text-ink hover:underline font-medium"
          >
            📄 {d.title}
          </Link>
          {d.email_id && (
            <span className="ml-2 text-[10px] text-muted">(email attachment)</span>
          )}
        </td>
        <td className="px-4 py-2 text-muted uppercase align-top">
          {d.source_type}
          {d.page_count ? ` · ${d.page_count}p` : ""}
        </td>
        <td className="px-4 py-2 text-muted align-top">{d.author || "—"}</td>
        <td className="px-4 py-2 align-top">
          <div className="flex items-center gap-2">
            <RelevancyBadge label={d.relevancy_label} score={d.relevancy_score} />
            {hasReason && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="text-[10px] text-accent hover:underline"
                title={expanded ? "Hide reasoning" : "Show LLM reasoning"}
              >
                {expanded ? "− why" : "+ why"}
              </button>
            )}
          </div>
        </td>
        <td className="px-4 py-2 text-muted align-top whitespace-nowrap">
          {formatDateTime(d.created_at)}
        </td>
        <td className="px-2 py-2 align-top">
          <button
            onClick={del}
            className="text-muted hover:text-rose-600 text-sm"
            title="Delete document"
          >
            🗑
          </button>
        </td>
      </tr>
      {expanded && hasReason && (
        <tr>
          <td colSpan={7} className="px-4 pb-3 bg-stone-50">
            <div className="text-xs border-l-4 border-accent bg-white rounded p-3 text-stone-700">
              <div className="text-[10px] uppercase tracking-wider text-muted mb-1">
                LLM reasoning · classified{" "}
                {d.relevancy_score != null && <>· {d.relevancy_score.toFixed(2)} similarity</>}
              </div>
              {d.relevancy_reasoning}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function RelevancyBadge({ label, score }: { label?: string | null; score?: number | null }) {
  if (!label) return <span className="text-[10px] text-muted">unclassified</span>;
  const cls =
    label === "relevant"
      ? "bg-emerald-100 text-emerald-800"
      : label === "uncertain"
      ? "bg-amber-100 text-amber-800"
      : "bg-stone-200 text-stone-600";
  return (
    <span className={cn("px-2 py-0.5 text-[10px] font-semibold rounded", cls)}>
      {label.toUpperCase()}
      {score != null && <span className="ml-1 opacity-70">{score.toFixed(2)}</span>}
    </span>
  );
}

function AuditTab({ caseId }: { caseId: string }) {
  const [rows, setRows] = useState<AuditEvent[] | null>(null);
  useEffect(() => {
    (async () => setRows(await api.listAudit(caseId)))();
  }, [caseId]);
  if (!rows) return <Loader label="Loading audit trail…" />;
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="font-medium">📜 Audit Trail</div>
          <div className="text-xs text-muted">
            Every AI decision and attorney action is logged for court-defensibility.
          </div>
        </div>
        <a
          href={api.auditCsvUrl(caseId)}
          className="px-3 py-1.5 text-xs border border-line rounded-md hover:bg-stone-50"
        >
          ⇣ Export CSV
        </a>
      </div>
      {rows.length === 0 ? (
        <div className="p-8 text-center border border-dashed border-line rounded-lg text-muted">
          No events yet.
        </div>
      ) : (
        <div className="bg-white border border-line rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2">When</th>
                <th className="px-4 py-2">Actor</th>
                <th className="px-4 py-2">Action</th>
                <th className="px-4 py-2">Summary</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((e) => (
                <tr key={e.id} className="align-top">
                  <td className="px-4 py-2 text-muted whitespace-nowrap">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2">
                    <span className={cn(
                      "px-2 py-0.5 text-[10px] rounded font-semibold",
                      e.actor === "ai" ? "bg-indigo-100 text-indigo-800" :
                      e.actor === "lawyer" ? "bg-emerald-100 text-emerald-800" :
                      "bg-stone-100 text-stone-700",
                    )}>{e.actor}</span>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{e.action}</td>
                  <td className="px-4 py-2 text-muted">{e.summary ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function PipelineTab({
  side,
  caseId,
  docs,
  emails,
  onUploadClick,
  onChanged,
  onRunRelevancy,
}: {
  side: ProductionType;
  caseId: string;
  docs: CaseDocument[];
  emails: Email[];
  onUploadClick: () => void;
  onChanged: () => void;
  onRunRelevancy?: () => void;
}) {
  const [sub, setSub] = useState<PipelineSub>("documents");
  const isOpposing = side === "opposing";
  return (
    <div>
      <div
        className={cn(
          "mb-5 p-4 rounded-lg border",
          isOpposing
            ? "border-rose-200 bg-rose-50"
            : "border-emerald-200 bg-emerald-50",
        )}
      >
        <div className="font-medium">
          {isOpposing ? "⚔️ Opposing Counsel Pipeline" : "🛡️ Our Document Pipeline"}
        </div>
        <div className="text-xs text-muted mt-1">
          {isOpposing
            ? "Their produced documents. AI finds holes in their production — bad redactions to challenge and argument/evidence gaps to exploit."
            : "Our client's documents. AI writes a memo, filters by relevance, suggests redactions for attorney review, and stress-tests the final set with a Q&A challenge rehearsal."}
        </div>
      </div>

      <div className="flex gap-4 border-b border-line mb-4">
        {(
          [
            { id: "documents" as const, label: `Documents (${docs.length})` },
            { id: "emails" as const, label: `Emails (${emails.length})` },
          ]
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setSub(t.id)}
            className={cn(
              "py-2 text-xs border-b-2 -mb-px",
              sub === t.id
                ? "border-ink text-ink font-medium"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {sub === "documents" ? (
        <DocumentsTable
          caseId={caseId}
          docs={docs}
          side={side}
          onUploadClick={onUploadClick}
          onRunRelevancy={onRunRelevancy}
        />
      ) : (
        <EmailsTable
          caseId={caseId}
          emails={emails}
          side={side}
          onChanged={onChanged}
        />
      )}
    </div>
  );
}

function DocumentsTable({
  caseId,
  docs,
  side,
  onUploadClick,
  onRunRelevancy,
}: {
  caseId: string;
  docs: CaseDocument[];
  side: ProductionType;
  onUploadClick: () => void;
  onRunRelevancy?: () => void;
}) {
  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <button
          onClick={onUploadClick}
          className="px-4 py-2 bg-ink text-white text-sm rounded-md"
        >
          + Upload {side === "opposing" ? "Opposing Counsel " : ""}PDF or DOCX
        </button>
        {side === "own" && onRunRelevancy && docs.length > 0 && (
          <button
            onClick={onRunRelevancy}
            className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-md"
            title="Embed case context, rank docs by relevance, tag irrelevant ones to skip redaction"
          >
            🎯 Run Relevancy Filter
          </button>
        )}
        <span className="text-xs text-muted">
          Ingests, chunks, embeds, and labels as <b>{side}</b> production.
        </span>
      </div>
      {docs.length === 0 ? (
        <div className="p-8 text-center border border-dashed border-line rounded-lg text-muted">
          No documents yet.
        </div>
      ) : (
        <div className="bg-white border border-line rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 w-10">#</th>
                <th className="px-4 py-2">Title</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Author</th>
                <th className="px-4 py-2">Relevancy</th>
                <th className="px-4 py-2">Uploaded</th>
                <th className="px-2 py-2 w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {docs.map((d, i) => (
                <DocRow key={d.id} d={d} i={i} caseId={caseId} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function EmailsTable({
  caseId,
  emails,
  side,
  onChanged,
}: {
  caseId: string;
  emails: Email[];
  side: ProductionType;
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [active, setActive] = useState<Email | null>(null);
  const [form, setForm] = useState({
    from_addr: "",
    to_addrs: "",
    subject: "",
    body: "",
    timestamp: "",
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: any = { ...form, production_type: side };
      if (!payload.timestamp) delete payload.timestamp;
      else payload.timestamp = new Date(payload.timestamp).toISOString();
      await api.createEmail(caseId, payload);
      setForm({ from_addr: "", to_addrs: "", subject: "", body: "", timestamp: "" });
      setAdding(false);
      await onChanged();
    } catch (e: any) {
      alert("Save failed: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <GmailConnector />
      <div className="mb-4 flex items-center gap-3">
        <button
          onClick={() => setAdding((v) => !v)}
          className="px-4 py-2 bg-ink text-white text-sm rounded-md"
        >
          {adding ? "Cancel" : "+ Add Email Manually"}
        </button>
        <span className="text-xs text-muted">
          Click any row to open the full email · new entries are tagged <b>{side}</b>.
        </span>
      </div>

      {adding && (
        <form
          onSubmit={submit}
          className="mb-6 p-4 bg-white border border-line rounded-lg grid grid-cols-2 gap-3"
        >
          <input
            className="border border-line rounded-md px-3 py-2 text-sm"
            placeholder="From (e.g. jane@acme.com)"
            value={form.from_addr}
            onChange={(e) => setForm({ ...form, from_addr: e.target.value })}
          />
          <input
            className="border border-line rounded-md px-3 py-2 text-sm"
            placeholder="To (comma-separated)"
            value={form.to_addrs}
            onChange={(e) => setForm({ ...form, to_addrs: e.target.value })}
          />
          <input
            className="col-span-2 border border-line rounded-md px-3 py-2 text-sm"
            placeholder="Subject"
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
          />
          <input
            type="datetime-local"
            className="border border-line rounded-md px-3 py-2 text-sm"
            value={form.timestamp}
            onChange={(e) => setForm({ ...form, timestamp: e.target.value })}
          />
          <div />
          <textarea
            className="col-span-2 border border-line rounded-md px-3 py-2 text-sm font-mono"
            placeholder="Body (optional)"
            rows={4}
            value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })}
          />
          <button
            disabled={saving}
            className="col-span-2 px-4 py-2 bg-accent text-white text-sm rounded-md disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save email"}
          </button>
        </form>
      )}

      {emails.length === 0 ? (
        <div className="p-8 text-center border border-dashed border-line rounded-lg text-muted">
          No emails yet.
        </div>
      ) : (
        <div className="bg-white border border-line rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 w-10">#</th>
                <th className="px-4 py-2">From</th>
                <th className="px-4 py-2">To</th>
                <th className="px-4 py-2">Subject</th>
                <th className="px-4 py-2">Timestamp</th>
                <th className="px-4 py-2">Attachments</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {emails.map((e, i) => (
                <tr
                  key={e.id}
                  onClick={() => setActive(e)}
                  className="hover:bg-stone-50 align-top cursor-pointer"
                >
                  <td className="px-4 py-2 text-muted">{i + 1}</td>
                  <td className="px-4 py-2">{e.from_addr || "—"}</td>
                  <td className="px-4 py-2 text-muted">{e.to_addrs || "—"}</td>
                  <td className="px-4 py-2 font-medium hover:underline">
                    {e.subject || "(no subject)"}
                  </td>
                  <td className="px-4 py-2 text-muted whitespace-nowrap">
                    {formatDateTime(e.timestamp)}
                  </td>
                  <td className="px-4 py-2" onClick={(ev) => ev.stopPropagation()}>
                    {e.attachments.length === 0 ? (
                      <span className="text-muted">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {e.attachments.map((a) => (
                          <Link
                            key={a.id}
                            to={`/cases/${caseId}/documents/${a.id}`}
                            className="text-xs bg-stone-100 hover:bg-stone-200 px-2 py-0.5 rounded"
                          >
                            📎 {a.title}
                          </Link>
                        ))}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {active && (
        <EmailModal
          email={active}
          caseId={caseId}
          onClose={() => setActive(null)}
        />
      )}
    </div>
  );
}

function CaseContextTab({
  caseId,
  memories,
  onChanged,
}: {
  caseId: string;
  memories: Memory[];
  onChanged: () => void;
}) {
  return (
    <div>
      <div className="mb-5 p-4 rounded-lg border border-sky-200 bg-sky-50">
        <div className="font-medium">🧠 Case Context Memo</div>
        <div className="text-xs text-muted mt-1">
          Briefing for the AI — written after you've reviewed the documents.
          Fields below are injected as named placeholders into every downstream
          prompt (redaction, memo, Q&amp;A challenges, opposing counsel review).
        </div>
      </div>
      <div className="space-y-4">
        {MEMORY_KINDS.map((kind) => (
          <MemoryEditor
            key={kind.kind}
            caseId={caseId}
            kind={kind.kind}
            label={kind.label}
            hint={kind.hint}
            entries={memories.filter((m) => m.kind === kind.kind)}
            onChanged={onChanged}
          />
        ))}
      </div>
    </div>
  );
}

function ConsolidatedTab({ caseId: _caseId }: { caseId: string }) {
  return (
    <div>
      <div className="mb-5 p-4 rounded-lg border border-violet-200 bg-violet-50">
        <div className="font-medium">📑 Consolidated Case Brief</div>
        <div className="text-xs text-muted mt-1">
          The finalised package: our defensible redactions with privilege log
          entries, strengths/weaknesses on our own documents, challenges against
          opposing counsel's redactions, and gap analysis of their production.
        </div>
      </div>
      <div className="p-10 text-center border border-dashed border-line rounded-lg text-muted">
        <div className="text-3xl mb-2">🚧</div>
        <div className="text-sm">Coming in the next build.</div>
        <div className="text-xs mt-2 max-w-md mx-auto">
          Will roll up: our accepted redactions (privilege log), Q&amp;A rehearsal
          status per redaction, opposing counsel redaction challenges, and
          argument gap analysis — exportable as a single PDF.
        </div>
      </div>
    </div>
  );
}

function MemoryEditor({
  caseId,
  kind,
  label,
  hint,
  entries,
  onChanged,
}: {
  caseId: string;
  kind: string;
  label: string;
  hint: string;
  entries: Memory[];
  onChanged: () => void;
}) {
  const existing = entries[0];
  const [content, setContent] = useState(existing?.content ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setContent(existing?.content ?? "");
  }, [existing?.id]);

  const save = async () => {
    setSaving(true);
    try {
      if (existing) {
        await api.updateMemory(caseId, existing.id, kind, content);
      } else if (content.trim()) {
        await api.createMemory(caseId, kind, content);
      }
      await onChanged();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-line rounded-lg p-4">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-sm font-semibold">{label}</div>
          <div className="text-xs text-muted">{hint}</div>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="px-3 py-1.5 text-xs bg-ink text-white rounded-md disabled:opacity-50"
        >
          {saving ? "Saving…" : existing ? "Update" : "Save"}
        </button>
      </div>
      <div data-color-mode="light">
        <MDEditor
          value={content}
          onChange={(v) => setContent(v ?? "")}
          height={160}
          preview="edit"
        />
      </div>
    </div>
  );
}
