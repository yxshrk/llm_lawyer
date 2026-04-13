/**
 * Pipeline 2 — Q&A Challenge Set (PRD §6).
 * Attorney stress-tests every accepted redaction with an adversarial Q&A.
 * Priority inconsistencies surface first, then low-confidence "hard mode".
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type RedactionChallenge } from "../lib/api";
import { cn } from "../lib/utils";
import type { ActivityEvent } from "./ActivityConsole";

export function QaPanel({
  caseId,
  pushEvent,
  setAnyRunning,
}: {
  caseId: string;
  pushEvent: (e: Omit<ActivityEvent, "id" | "t">) => void;
  setAnyRunning: (v: boolean) => void;
}) {
  const [challenges, setChallenges] = useState<RedactionChallenge[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();

  const refresh = async () => setChallenges(await api.listQa(caseId));
  useEffect(() => {
    refresh();
  }, [caseId]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const run = async () => {
    setRunning(true);
    setAnyRunning(true);
    setChallenges([]);
    setProgress({ done: 0, total: 0 });
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    pushEvent({ kind: "info", label: "Q&A challenge run starting", badge: "Q&A" });
    try {
      let total = 0;
      let done = 0;
      for await (const ev of api.streamQa(caseId, ac.signal)) {
        if (ev.type === "started") {
          total = ev.total ?? 0;
          setProgress({ done: 0, total });
          pushEvent({ kind: "info", label: `Challenging ${total} accepted redactions`, badge: "Q&A" });
        } else if (ev.type === "inconsistency_scan") {
          pushEvent({
            kind: "stage",
            label: `Consistency scan: ${ev.pairs} inconsistency pair${ev.pairs === 1 ? "" : "s"}`,
            badge: "Q&A",
          });
        } else if (ev.type === "stage") {
          pushEvent({ kind: "stage", label: `Stage: ${ev.stage}`, badge: "Q&A" });
        } else if (ev.type === "challenge") {
          done += 1;
          setProgress({ done, total });
          setChallenges((c) => [...c, ev.challenge]);
          pushEvent({
            kind: "result",
            label: `[${ev.challenge.difficulty}] ${ev.challenge.challenge_question.slice(0, 80)}`,
            detail: ev.challenge.legal_basis ?? undefined,
            badge: "Q&A",
          });
        } else if (ev.type === "done") {
          pushEvent({ kind: "done", label: `Q&A done — ${ev.total ?? 0} challenges`, badge: "Q&A" });
        } else if (ev.type === "error") {
          pushEvent({ kind: "error", label: ev.message, badge: "Q&A" });
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        pushEvent({ kind: "error", label: e?.message ?? "Q&A stream failed", badge: "Q&A" });
      }
    } finally {
      setRunning(false);
      setAnyRunning(false);
      await refresh();
    }
  };

  const setStatus = async (ch: RedactionChallenge, status: string) => {
    if (status === "will_revise") {
      await api.reviewChallenge(ch.id, status);
      navigate(`/cases/${caseId}/documents/${ch.redaction?.document_id}`);
      return;
    }
    await api.reviewChallenge(ch.id, status);
    await refresh();
  };

  const grouped = {
    priority: challenges.filter((c) => c.difficulty === "priority_inconsistency"),
    hard: challenges.filter((c) => c.difficulty === "hard_low_confidence"),
    standard: challenges.filter((c) => c.difficulty === "standard"),
  };

  return (
    <div>
      <div className="mb-5 p-4 rounded-lg border border-amber-200 bg-amber-50 flex items-center justify-between">
        <div>
          <div className="font-medium">⚔️ Q&amp;A Challenge Set (Pipeline 2)</div>
          <div className="text-xs text-muted mt-1 max-w-2xl">
            Stress-test every accepted redaction by simulating the questions a judge or opposing counsel would ask.
            Priority inconsistencies surface first; low-confidence redactions get harder "hard mode" questions.
            Mark each challenge <b>Prepared</b>, <b>Needs Work</b>, or <b>Will Revise Redaction</b> (jumps you back to the redaction).
          </div>
        </div>
        <button
          onClick={run}
          disabled={running}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm rounded-md whitespace-nowrap disabled:opacity-50"
        >
          {running
            ? progress
              ? `Challenging ${progress.done}/${progress.total}…`
              : "Running…"
            : challenges.length > 0
              ? "↻ Re-run Q&A"
              : "🎯 Run Q&A Rehearsal"}
        </button>
      </div>

      {running && (
        <div className="mb-4 text-xs text-muted animate-pulse">
          Judge + opposing counsel drafting challenges… first pass against priority inconsistencies.
        </div>
      )}

      {challenges.length === 0 && !running && (
        <div className="p-10 text-center border border-dashed border-line rounded-lg text-muted">
          <div className="text-3xl mb-2">🛡️</div>
          <div className="text-sm">
            No challenges yet. Accept some redactions first, then click <b>Run Q&amp;A Rehearsal</b>.
          </div>
        </div>
      )}

      {grouped.priority.length > 0 && (
        <Section title="🚨 Priority — Inconsistencies" tone="rose">
          {grouped.priority.map((c) => (
            <ChallengeCard key={c.id} challenge={c} onStatus={setStatus} />
          ))}
        </Section>
      )}
      {grouped.hard.length > 0 && (
        <Section title="🔥 Hard Mode — Low Confidence" tone="amber">
          {grouped.hard.map((c) => (
            <ChallengeCard key={c.id} challenge={c} onStatus={setStatus} />
          ))}
        </Section>
      )}
      {grouped.standard.length > 0 && (
        <Section title="Standard Challenges" tone="stone">
          {grouped.standard.map((c) => (
            <ChallengeCard key={c.id} challenge={c} onStatus={setStatus} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "rose" | "amber" | "stone";
  children: React.ReactNode;
}) {
  return (
    <div className="mb-5">
      <div
        className={cn(
          "text-xs font-bold uppercase tracking-wider mb-2 px-2 py-1 rounded inline-block",
          tone === "rose" && "bg-rose-100 text-rose-800",
          tone === "amber" && "bg-amber-100 text-amber-800",
          tone === "stone" && "bg-stone-100 text-stone-700",
        )}
      >
        {title}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function ChallengeCard({
  challenge,
  onStatus,
}: {
  challenge: RedactionChallenge;
  onStatus: (c: RedactionChallenge, s: string) => void;
}) {
  const statusStyles: Record<string, string> = {
    pending: "border-line bg-white",
    prepared: "border-emerald-400 bg-emerald-50",
    needs_work: "border-amber-400 bg-amber-50",
    will_revise: "border-rose-400 bg-rose-50",
  };
  return (
    <div
      className={cn(
        "border-l-4 rounded p-4 bg-white border border-line",
        statusStyles[challenge.lawyer_status] ?? "border-line",
      )}
    >
      <div className="flex items-center gap-2 flex-wrap mb-2">
        {challenge.redaction && (
          <>
            <span className="text-[10px] font-bold bg-stone-900 text-white px-2 py-0.5 rounded">
              {challenge.redaction.label}
            </span>
            <span className="text-[10px] font-semibold bg-stone-100 text-stone-700 px-2 py-0.5 rounded">
              {challenge.redaction.confidence_band} confidence
              {challenge.redaction.confidence != null && (
                <> · {Math.round(challenge.redaction.confidence * 100)}%</>
              )}
            </span>
            {challenge.redaction.page != null && (
              <span className="text-[10px] text-muted">p.{challenge.redaction.page + 1}</span>
            )}
          </>
        )}
        <span className="ml-auto text-[10px] uppercase text-muted">
          {challenge.lawyer_status.replace("_", " ")}
        </span>
      </div>

      {challenge.redaction && (
        <div className="mb-2 bg-stone-50 border border-line rounded p-2 font-mono text-xs text-stone-700">
          Redacted: {challenge.redaction.text_span.slice(0, 240)}
          {challenge.redaction.text_span.length > 240 ? "…" : ""}
        </div>
      )}

      <div className="text-sm font-semibold text-ink mb-2">
        Q: {challenge.challenge_question}
      </div>
      {challenge.suggested_answer && (
        <div className="text-sm text-ink mb-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">A (suggested): </span>
          {challenge.suggested_answer}
        </div>
      )}
      {challenge.legal_basis && (
        <div className="text-xs italic text-muted mb-1">
          <b>Legal basis:</b> {challenge.legal_basis}
        </div>
      )}
      {challenge.risk_flag && (
        <div className="text-xs bg-rose-100 text-rose-800 border border-rose-200 rounded p-2 mb-2">
          <b>⚠ Risk:</b> {challenge.risk_flag}
        </div>
      )}

      <div className="flex gap-2 mt-3">
        <button
          onClick={() => onStatus(challenge, "prepared")}
          className="px-2 py-1 text-xs bg-emerald-600 text-white rounded disabled:opacity-50"
          disabled={challenge.lawyer_status === "prepared"}
        >
          ✓ Prepared
        </button>
        <button
          onClick={() => onStatus(challenge, "needs_work")}
          className="px-2 py-1 text-xs bg-amber-600 text-white rounded disabled:opacity-50"
          disabled={challenge.lawyer_status === "needs_work"}
        >
          ✎ Needs Work
        </button>
        <button
          onClick={() => onStatus(challenge, "will_revise")}
          className="px-2 py-1 text-xs bg-rose-600 text-white rounded"
          title="Jump back to this redaction to revise it"
        >
          ⟲ Will Revise Redaction
        </button>
      </div>
    </div>
  );
}
