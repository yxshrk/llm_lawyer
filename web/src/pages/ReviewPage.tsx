import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import MDEditor from "@uiw/react-md-editor";
import {
  api,
  type ChatReply,
  type Document as Doc,
  type OpposingChallenge,
  type OpposingGap,
  type Redaction,
  type StrengthsWeaknesses,
} from "../lib/api";
import { cn } from "../lib/utils";
import { Loader } from "../components/Loader";
import { PdfViewer } from "../components/PdfViewer";
import {
  ActivityConsole,
  useActivityLog,
  type ActivityEvent,
} from "../components/ActivityConsole";

type RightTab = "redactions" | "chat" | "memo" | "sw" | "opposing";

export default function ReviewPage() {
  const { caseId, docId } = useParams<{ caseId: string; docId: string }>();
  const [doc, setDoc] = useState<Doc | null>(null);
  const [redactions, setRedactions] = useState<Redaction[]>([]);
  const [tab, setTab] = useState<RightTab>("redactions");
  const [runningReds, setRunningReds] = useState(false);
  const [progress, setProgress] = useState<{
    batch: number;
    total: number;
    newIds: Set<string>;
  } | null>(null);

  // Activity console state — shared by every streaming op on this page.
  const { make: makeEvent } = useActivityLog();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [consoleCollapsed, setConsoleCollapsed] = useState(false);
  const [anyRunning, setAnyRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const pushEvent = useCallback(
    (partial: Omit<ActivityEvent, "id" | "t">) =>
      setEvents((prev) => [...prev, makeEvent(partial)]),
    [makeEvent],
  );

  const refresh = useCallback(async () => {
    if (!docId) return;
    const [d, r] = await Promise.all([
      api.getDocument(docId),
      api.listRedactions(docId),
    ]);
    setDoc(d);
    setRedactions(r);
  }, [docId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Abort any in-flight stream when we unmount.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const onRunReds = async () => {
    if (!docId) return;
    setRunningReds(true);
    setAnyRunning(true);
    setRedactions([]); // clear — server clears pending too
    const newIds = new Set<string>();
    setProgress({ batch: 0, total: 0, newIds });
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    pushEvent({ kind: "info", label: "Redaction analysis starting", badge: "RED" });
    try {
      for await (const ev of api.streamRedactions(docId, 5, ac.signal)) {
        if (ev.type === "started") {
          setProgress({ batch: 0, total: ev.total_batches ?? 0, newIds });
          pushEvent({
            kind: "info",
            label: `Analysing ${ev.chunk_count} chunks across ${ev.total_batches} batches`,
            badge: "RED",
          });
        } else if (ev.type === "batch_start") {
          setProgress({ batch: ev.batch, total: ev.total_batches, newIds });
          pushEvent({
            kind: "progress",
            label: `Batch ${ev.batch}/${ev.total_batches} → LLM`,
            badge: "RED",
          });
        } else if (ev.type === "batch_done") {
          pushEvent({
            kind: "result",
            label: `Batch ${ev.batch} produced ${ev.created} flag${ev.created === 1 ? "" : "s"}`,
            detail: ev.provider ? `via ${ev.provider}` : undefined,
            badge: "RED",
          });
        } else if (ev.type === "redaction") {
          newIds.add(ev.redaction.id);
          setRedactions((rs) => [...rs, ev.redaction]);
          pushEvent({
            kind: "result",
            label: `[${ev.redaction.label}] ${Math.round((ev.redaction.confidence ?? 0) * 100)}% — ${ev.redaction.text_span.slice(0, 60)}…`,
            detail: ev.redaction.reasoning ?? undefined,
            badge: "RED",
          });
        } else if (ev.type === "done") {
          setProgress((p) => (p ? { ...p, batch: p.total, newIds } : null));
          pushEvent({ kind: "done", label: `Redaction done — ${ev.total} flagged`, badge: "RED" });
        } else if (ev.type === "error") {
          pushEvent({ kind: "error", label: ev.message, badge: "RED" });
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        pushEvent({ kind: "error", label: e?.message ?? "Redaction stream failed", badge: "RED" });
      }
    } finally {
      setRunningReds(false);
      setAnyRunning(false);
      setTimeout(() => setProgress(null), 2500);
      await refresh();
    }
  };

  if (!doc) return <Loader label="Loading document…" />;

  const isOpposing = doc.production_type === "opposing";
  const rightTabs: Array<{ id: RightTab; label: string }> = isOpposing
    ? [
        { id: "opposing", label: "Opposing" },
        { id: "chat", label: "Chat" },
        { id: "memo", label: "Memo" },
      ]
    : [
        { id: "chat", label: "Chat" },
        { id: "memo", label: "Memo" },
        { id: "sw", label: "Strengths / Weaknesses" },
      ];

  return (
    <div className="h-[calc(100vh-56px)] flex flex-col">
      <div className="border-b border-line bg-white px-6 py-3 flex items-center justify-between">
        <div>
          <Link
            to={`/cases/${caseId}`}
            className="text-xs text-muted hover:text-ink"
          >
            ← Back to case
          </Link>
          <div className="font-medium text-ink truncate flex items-center gap-2">
            📄 {doc.title}
            <span
              className={cn(
                "text-[10px] px-2 py-0.5 rounded font-semibold",
                isOpposing
                  ? "bg-rose-100 text-rose-700"
                  : "bg-emerald-100 text-emerald-700",
              )}
            >
              {isOpposing ? "OPPOSING" : "OWN"}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {!isOpposing && (
            <button
              onClick={onRunReds}
              disabled={runningReds}
              className="px-4 py-2 bg-accent text-white text-sm rounded-md disabled:opacity-50"
            >
              {runningReds ? "Analyzing…" : "🔍 Run Redaction Analysis"}
            </button>
          )}
          {isOpposing && <RunOpposingButton docId={docId!} pushEvent={pushEvent} setAnyRunning={setAnyRunning} onDone={refresh} setTab={setTab} />}
        </div>
      </div>

      <div className="flex-1 grid grid-cols-[1fr_380px_380px] min-h-0">
        {/* PDF preview */}
        <div className="border-r border-line min-h-0">
          {doc.signed_url ? (
            <PdfViewer url={doc.signed_url} />
          ) : (
            <div className="flex items-center justify-center h-full text-muted">
              No preview URL.
            </div>
          )}
        </div>

        {/* Redactions column */}
        <div className="border-r border-line bg-white overflow-y-auto">
          <div className="sticky top-0 bg-white border-b border-line px-4 py-2 z-10">
            <div className="text-sm font-semibold flex items-center justify-between">
              <span>
                Redaction suggestions ({redactions.length})
              </span>
              {runningReds && (
                <span className="text-[10px] text-accent animate-pulse">
                  ● LIVE
                </span>
              )}
            </div>
            {progress && progress.total > 0 && (
              <div className="mt-2">
                <div className="flex justify-between text-[10px] text-muted mb-1">
                  <span>
                    {runningReds
                      ? `Analyzing batch ${progress.batch} of ${progress.total}`
                      : `Complete — ${redactions.length} flagged`}
                  </span>
                  <span>
                    {Math.round((progress.batch / progress.total) * 100)}%
                  </span>
                </div>
                <div className="h-1 bg-stone-200 rounded overflow-hidden">
                  <div
                    className="h-full bg-accent transition-all duration-300"
                    style={{
                      width: `${(progress.batch / progress.total) * 100}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
          {redactions.length === 0 && !runningReds ? (
            <div className="p-6 text-sm text-muted">
              No redactions yet. Click “Run Redaction Analysis”.
            </div>
          ) : (
            <div className="divide-y divide-line">
              {redactions.map((r) => (
                <RedactionCard
                  key={r.id}
                  r={r}
                  onChange={refresh}
                  justAdded={progress?.newIds.has(r.id) ?? false}
                />
              ))}
              {runningReds && (
                <div className="p-4 text-xs text-muted flex items-center gap-2">
                  <span className="flex gap-0.5">
                    <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce" />
                    <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:-0.3s]" />
                  </span>
                  Scanning for PRIV / PII / TS / WP…
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right panel: tabs */}
        <div className="flex flex-col bg-white min-h-0">
          <div className="flex border-b border-line">
            {rightTabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "flex-1 py-2 text-xs border-b-2 -mb-px transition",
                  tab === t.id
                    ? "border-ink text-ink font-medium"
                    : "border-transparent text-muted hover:text-ink",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {tab === "chat" && <ChatPanel docId={docId!} />}
            {tab === "memo" && <MemoPanel docId={docId!} pushEvent={pushEvent} setAnyRunning={setAnyRunning} />}
            {tab === "sw" && <SWPanel docId={docId!} />}
            {tab === "opposing" && <OpposingPanel docId={docId!} />}
          </div>
        </div>
      </div>
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

function labelColor(label: string) {
  const upper = label.toUpperCase();
  if (upper.includes("PRIV")) return "bg-rose-100 text-rose-800";
  if (upper.includes("WP")) return "bg-rose-100 text-rose-800";
  if (upper.includes("PII")) return "bg-amber-100 text-amber-800";
  if (upper.includes("PHI")) return "bg-amber-100 text-amber-800";
  if (upper.includes("TS")) return "bg-indigo-100 text-indigo-800";
  return "bg-stone-100 text-stone-700";
}

function confColor(c: number | null) {
  if (c == null) return "bg-stone-100 text-stone-600";
  if (c >= 0.85) return "bg-emerald-100 text-emerald-800";
  if (c >= 0.6) return "bg-amber-100 text-amber-800";
  return "bg-rose-100 text-rose-800";
}

function statusColor(s: string) {
  if (s === "accepted") return "border-emerald-400 bg-emerald-50";
  if (s === "rejected") return "border-stone-300 bg-stone-50 opacity-60";
  if (s === "modified") return "border-indigo-400 bg-indigo-50";
  return "border-line bg-white";
}

function RedactionCard({
  r,
  onChange,
  justAdded,
}: {
  r: Redaction;
  onChange: () => void;
  justAdded?: boolean;
}) {
  const [busy, setBusy] = useState(false);

  const act = async (status: string, modified_span?: string) => {
    setBusy(true);
    try {
      await api.reviewRedaction(r.id, status, modified_span);
      await onChange();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={cn(
        "p-4 border-l-4 transition",
        statusColor(r.status),
        justAdded && "animate-[fadeIn_0.6s_ease-out] ring-2 ring-accent/40",
      )}
      style={
        justAdded
          ? { animation: "redactionPop 0.5s ease-out" }
          : undefined
      }
    >
      <div className="flex items-center gap-2 mb-2">
        <span className={cn("px-2 py-0.5 text-[10px] font-bold rounded", labelColor(r.label))}>
          {r.label}
        </span>
        <span className={cn("px-2 py-0.5 text-[10px] rounded", confColor(r.confidence))}>
          {r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "—"}
        </span>
        {r.page != null && (
          <span className="text-[10px] text-muted">p.{r.page + 1}</span>
        )}
        <span className="ml-auto text-[10px] text-muted uppercase">
          {r.status}
        </span>
      </div>
      <div className="text-sm text-ink mb-2 font-mono bg-stone-50 border border-line rounded p-2 whitespace-pre-wrap">
        {r.text_span}
      </div>
      {r.reasoning && (
        <div className="text-xs text-muted italic mb-2">{r.reasoning}</div>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => act("accepted")}
          disabled={busy || r.status === "accepted"}
          className="px-2 py-1 text-xs bg-emerald-600 text-white rounded disabled:opacity-50"
        >
          ✓ Accept
        </button>
        <button
          onClick={() => act("rejected")}
          disabled={busy || r.status === "rejected"}
          className="px-2 py-1 text-xs bg-stone-600 text-white rounded disabled:opacity-50"
        >
          ✗ Reject
        </button>
        <button
          onClick={() => {
            const modified = prompt("Modify redaction span:", r.modified_span ?? r.text_span);
            if (modified && modified.trim()) act("modified", modified);
          }}
          disabled={busy}
          className="px-2 py-1 text-xs border border-line rounded"
        >
          ✎ Modify
        </button>
      </div>
    </div>
  );
}

function ChatPanel({ docId }: { docId: string }) {
  const [messages, setMessages] = useState<
    Array<{ role: "user" | "assistant"; content: string }>
  >([]);
  const [input, setInput] = useState("");
  const [convId, setConvId] = useState<string | undefined>(undefined);
  const [lastUsage, setLastUsage] = useState<ChatReply["usage"] | null>(null);
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    if (!input.trim() || sending) return;
    const msg = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setSending(true);
    try {
      const res = await api.chat(msg, {
        document_id: docId,
        conversation_id: convId as any,
      });
      setConvId(res.conversation_id);
      setLastUsage(res.usage);
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
    } catch (e: any) {
      setMessages((m) => [...m, { role: "assistant", content: "Error: " + e.message }]);
    } finally {
      setSending(false);
      setTimeout(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight }), 10);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={listRef} className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-xs text-muted">
            Ask anything about this document. Case memory + retrieved chunks are injected automatically.
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={cn(
              "p-2 rounded-md text-sm whitespace-pre-wrap",
              m.role === "user"
                ? "bg-stone-100 ml-6"
                : "bg-blue-50 mr-6 border border-blue-100",
            )}
          >
            {m.content}
          </div>
        ))}
        {sending && <div className="text-xs text-muted">Thinking…</div>}
      </div>
      {lastUsage && (
        <div className="px-3 py-1 text-[10px] text-muted border-t border-line">
          {lastUsage.provider} · {lastUsage.prompt_tokens}p / {lastUsage.completion_tokens}c
          {lastUsage.cached_prompt_tokens > 0 && ` · ${lastUsage.cached_prompt_tokens} cached`}
        </div>
      )}
      <div className="border-t border-line p-2 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about this document…"
          className="flex-1 border border-line rounded-md px-3 py-2 text-sm"
        />
        <button
          onClick={send}
          disabled={sending || !input.trim()}
          className="px-3 py-2 bg-ink text-white text-sm rounded-md disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}

function MemoPanel({
  docId,
  pushEvent,
  setAnyRunning,
}: {
  docId: string;
  pushEvent: (e: Omit<ActivityEvent, "id" | "t">) => void;
  setAnyRunning: (v: boolean) => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [chunkProgress, setChunkProgress] = useState<{ done: number; total: number } | null>(null);

  useEffect(() => {
    (async () => {
      const m = await api.getMemo(docId);
      setContent(m?.content ?? null);
    })();
  }, [docId]);

  const generate = async () => {
    setBusy(true);
    setAnyRunning(true);
    setContent(null);
    setStage("starting");
    setChunkProgress(null);
    pushEvent({ kind: "info", label: "Memo generation starting", badge: "MEMO" });
    try {
      let total = 0;
      let done = 0;
      for await (const ev of api.streamMemo(docId)) {
        if (ev.type === "started") {
          total = ev.chunk_count ?? 0;
          setChunkProgress({ done: 0, total });
          pushEvent({ kind: "info", label: `Summarising ${total} chunks`, badge: "MEMO" });
        } else if (ev.type === "stage") {
          setStage(ev.stage);
          pushEvent({ kind: "stage", label: `Stage: ${ev.stage}`, badge: "MEMO" });
        } else if (ev.type === "chunk_summarised") {
          done += 1;
          setChunkProgress({ done, total });
          pushEvent({
            kind: "progress",
            label: `Chunk #${ev.ordinal}${ev.page ? ` p${ev.page}` : ""}`,
            detail: ev.summary.slice(0, 140),
            badge: "MEMO",
          });
        } else if (ev.type === "memo") {
          setContent(ev.content);
          pushEvent({
            kind: "result",
            label: "Memo synthesised",
            detail: ev.provider ? `via ${ev.provider}` : undefined,
            badge: "MEMO",
          });
        } else if (ev.type === "done") {
          pushEvent({ kind: "done", label: "Memo ready", badge: "MEMO" });
        } else if (ev.type === "error") {
          pushEvent({ kind: "error", label: ev.message, badge: "MEMO" });
        }
      }
    } catch (e: any) {
      pushEvent({ kind: "error", label: e?.message ?? "Memo stream failed", badge: "MEMO" });
    } finally {
      setBusy(false);
      setAnyRunning(false);
      setStage(null);
    }
  };

  return (
    <div className="p-3 flex flex-col h-full">
      <div className="mb-3 flex items-center gap-3">
        <button
          onClick={generate}
          disabled={busy}
          className="px-3 py-1.5 text-xs bg-ink text-white rounded-md disabled:opacity-50"
        >
          {busy ? "Generating…" : content ? "↻ Regenerate memo" : "Generate memo"}
        </button>
        {busy && stage && (
          <span className="text-xs text-muted">
            {stage}
            {chunkProgress && stage === "summarise_chunks" && chunkProgress.total > 0
              ? ` · ${chunkProgress.done}/${chunkProgress.total}`
              : ""}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto bg-stone-50 border border-line rounded p-3 text-sm">
        {content ? (
          <div data-color-mode="light">
            <MDEditor.Markdown source={content} style={{ background: "transparent" }} />
          </div>
        ) : busy ? (
          <div className="text-xs text-muted italic">Synthesising memo…</div>
        ) : (
          <div className="text-xs text-muted">No memo yet.</div>
        )}
      </div>
    </div>
  );
}

function RunOpposingButton({
  docId,
  pushEvent,
  setAnyRunning,
  onDone,
  setTab,
}: {
  docId: string;
  pushEvent: (e: Omit<ActivityEvent, "id" | "t">) => void;
  setAnyRunning: (v: boolean) => void;
  onDone: () => void;
  setTab: (t: RightTab) => void;
}) {
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setAnyRunning(true);
    setTab("opposing");
    pushEvent({ kind: "info", label: "Opposing counsel review starting", badge: "OPP" });
    try {
      for await (const ev of api.streamOpposingReview(docId)) {
        if (ev.type === "started") {
          pushEvent({
            kind: "info",
            label: `${ev.chunk_count} chunks → challenges + gap finder`,
            badge: "OPP",
          });
        } else if (ev.type === "stage") {
          pushEvent({ kind: "stage", label: `Stage: ${ev.stage}`, badge: "OPP" });
        } else if (ev.type === "batch_start") {
          pushEvent({
            kind: "progress",
            label: `Batch ${ev.batch}/${ev.total_batches}`,
            badge: "OPP",
          });
        } else if (ev.type === "challenge") {
          pushEvent({
            kind: "result",
            label: `[${ev.challenge.strength.toUpperCase()}] ${ev.challenge.challenge.slice(0, 80)}`,
            detail: ev.challenge.legal_basis,
            badge: "OPP",
          });
        } else if (ev.type === "gap") {
          pushEvent({
            kind: "result",
            label: `GAP: ${ev.gap.expected_topic}`,
            detail: ev.gap.gap_description,
            badge: "OPP",
          });
        } else if (ev.type === "done") {
          pushEvent({
            kind: "done",
            label: `Opposing review done — ${ev.challenges} challenges, ${ev.gaps} gaps`,
            badge: "OPP",
          });
        } else if (ev.type === "error") {
          pushEvent({ kind: "error", label: ev.message, badge: "OPP" });
        }
      }
    } catch (e: any) {
      pushEvent({ kind: "error", label: e?.message ?? "Opposing stream failed", badge: "OPP" });
    } finally {
      setBusy(false);
      setAnyRunning(false);
      onDone();
    }
  };

  return (
    <button
      onClick={run}
      disabled={busy}
      className="px-4 py-2 bg-rose-600 text-white text-sm rounded-md disabled:opacity-50"
    >
      {busy ? "Analyzing…" : "⚔️ Run Opposing Review"}
    </button>
  );
}

function OpposingPanel({ docId }: { docId: string }) {
  const [data, setData] = useState<{ challenges: OpposingChallenge[]; gaps: OpposingGap[] } | null>(null);
  useEffect(() => {
    (async () => {
      const res = await api.getOpposingReview(docId);
      if (res) setData({ challenges: res.challenges, gaps: res.gaps });
    })();
  }, [docId]);

  return (
    <div className="p-3 flex flex-col h-full overflow-y-auto">
      <div className="mb-3 text-xs text-muted">
        Click the <b>⚔️ Run Opposing Review</b> button above to populate. Results are persisted.
      </div>
      {data ? (
        <>
          <div className="mb-4">
            <div className="text-xs font-semibold uppercase tracking-wide mb-2">
              Redaction Challenges ({data.challenges.length})
            </div>
            <div className="space-y-2">
              {data.challenges.length === 0 && (
                <div className="text-xs text-muted italic">No challengeable redactions identified.</div>
              )}
              {data.challenges.map((c, i) => (
                <div key={i} className="border border-rose-200 bg-rose-50 rounded p-2 text-xs">
                  <div className="flex gap-2 mb-1">
                    <span className={cn(
                      "px-2 py-0.5 rounded font-bold text-[10px]",
                      c.strength === "strong" ? "bg-rose-700 text-white" :
                      c.strength === "moderate" ? "bg-amber-200 text-amber-900" :
                      "bg-stone-200 text-stone-700",
                    )}>
                      {c.strength?.toUpperCase()}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-white text-[10px] text-stone-700">
                      {c.stated_category}
                    </span>
                  </div>
                  {c.redacted_passage && (
                    <div className="bg-white border border-rose-100 rounded p-1 mb-1 font-mono text-[11px]">
                      {c.redacted_passage}
                    </div>
                  )}
                  <div className="font-medium">{c.challenge}</div>
                  <div className="mt-1 italic text-muted">Legal basis: {c.legal_basis}</div>
                  {c.recommended_action && (
                    <div className="mt-1">
                      <b>Action:</b> {c.recommended_action}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide mb-2">
              Argument / Evidence Gaps ({data.gaps.length})
            </div>
            <div className="space-y-2">
              {data.gaps.length === 0 && (
                <div className="text-xs text-muted italic">No gaps identified.</div>
              )}
              {data.gaps.map((g, i) => (
                <div key={i} className="border border-amber-200 bg-amber-50 rounded p-2 text-xs">
                  <div className="font-semibold">{g.expected_topic}</div>
                  <div className="mt-1">{g.gap_description}</div>
                  {g.significance && (
                    <div className="mt-1 italic text-muted">Why: {g.significance}</div>
                  )}
                  {g.recommended_action && (
                    <div className="mt-1">
                      <b>Action:</b> {g.recommended_action}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="text-xs text-muted italic">No analysis yet.</div>
      )}
    </div>
  );
}

function SWPanel({ docId }: { docId: string }) {
  const [sw, setSw] = useState<StrengthsWeaknesses | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => setSw(await api.getSW(docId));
  useEffect(() => {
    load();
  }, [docId]);

  const generate = async () => {
    setBusy(true);
    try {
      setSw(await api.generateSW(docId));
    } catch (e: any) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-3 flex flex-col h-full">
      <button
        onClick={generate}
        disabled={busy}
        className="mb-3 self-start px-3 py-1.5 text-xs bg-ink text-white rounded-md disabled:opacity-50"
      >
        {busy ? "Analyzing…" : sw ? "↻ Regenerate" : "Analyze strengths & weaknesses"}
      </button>
      <div className="flex-1 overflow-y-auto space-y-4">
        {sw ? (
          <>
            <SWList title="💪 Strengths" items={sw.content.strengths ?? []} tone="emerald" />
            <SWList title="⚠️ Weaknesses" items={sw.content.weaknesses ?? []} tone="rose" />
          </>
        ) : (
          <div className="text-xs text-muted">No analysis yet.</div>
        )}
      </div>
    </div>
  );
}

function SWList({
  title,
  items,
  tone,
}: {
  title: string;
  items: Array<{ point: string; detail: string; citations: number[]; confidence: number }>;
  tone: "emerald" | "rose";
}) {
  const toneClasses =
    tone === "emerald"
      ? "border-emerald-300 bg-emerald-50"
      : "border-rose-300 bg-rose-50";
  return (
    <div>
      <div className="text-xs font-semibold mb-2">{title}</div>
      <div className="space-y-2">
        {items.length === 0 && <div className="text-xs text-muted">None identified.</div>}
        {items.map((it, i) => (
          <div key={i} className={cn("border rounded p-2 text-xs", toneClasses)}>
            <div className="font-semibold">{it.point}</div>
            <div className="mt-1">{it.detail}</div>
            <div className="mt-1 text-[10px] text-muted">
              conf {Math.round((it.confidence ?? 0) * 100)}% · cites {it.citations?.join(", ") || "—"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
