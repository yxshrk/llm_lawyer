import { useEffect, useRef } from "react";
import { cn } from "../lib/utils";

export interface ActivityEvent {
  id: number;
  t: number;
  kind: "info" | "stage" | "progress" | "result" | "error" | "done";
  label: string;
  detail?: string;
  badge?: string;
}

/** Terminal-style live log for streaming AI ops. Auto-scrolls to bottom as
 * events arrive; click the header to collapse. */
export function ActivityConsole({
  title,
  events,
  running,
  onClear,
  collapsed,
  onToggle,
}: {
  title: string;
  events: ActivityEvent[];
  running: boolean;
  onClear?: () => void;
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [events.length]);

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 w-[420px] bg-stone-900 text-stone-100 rounded-lg shadow-2xl border border-stone-700 text-xs font-mono z-40",
        collapsed ? "h-10" : "max-h-[50vh]",
        "flex flex-col overflow-hidden",
      )}
    >
      <div
        className="px-3 h-10 flex items-center justify-between border-b border-stone-700 bg-stone-800 cursor-pointer select-none"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "w-2 h-2 rounded-full",
              running ? "bg-emerald-400 animate-pulse" : "bg-stone-500",
            )}
          />
          <span className="font-semibold tracking-wide">{title}</span>
          {running && <span className="text-[10px] text-emerald-400">● LIVE</span>}
        </div>
        <div className="flex items-center gap-3 text-stone-400">
          <span>{events.length} events</span>
          {onClear && !running && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onClear();
              }}
              className="hover:text-white"
            >
              clear
            </button>
          )}
          <span>{collapsed ? "▲" : "▼"}</span>
        </div>
      </div>
      {!collapsed && (
        <div ref={listRef} className="flex-1 overflow-y-auto p-3 space-y-1">
          {events.length === 0 && (
            <div className="text-stone-500 italic">No activity yet.</div>
          )}
          {events.map((ev) => (
            <div key={ev.id} className="flex items-start gap-2 leading-tight">
              <span className="text-stone-500 shrink-0">
                {new Date(ev.t).toISOString().slice(11, 19)}
              </span>
              <span
                className={cn(
                  "shrink-0 uppercase text-[9px] px-1 py-0.5 rounded font-bold",
                  ev.kind === "info" && "bg-sky-900 text-sky-200",
                  ev.kind === "stage" && "bg-indigo-900 text-indigo-200",
                  ev.kind === "progress" && "bg-amber-900 text-amber-200",
                  ev.kind === "result" && "bg-emerald-900 text-emerald-200",
                  ev.kind === "error" && "bg-rose-900 text-rose-200",
                  ev.kind === "done" && "bg-emerald-700 text-white",
                )}
              >
                {ev.badge ?? ev.kind}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-stone-100">{ev.label}</div>
                {ev.detail && (
                  <div className="text-stone-400 truncate">{ev.detail}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Hook that maintains an event stream for a single page. */
export function useActivityLog() {
  const counter = useRef(0);
  return {
    make: (partial: Omit<ActivityEvent, "id" | "t">): ActivityEvent => ({
      id: ++counter.current,
      t: Date.now(),
      ...partial,
    }),
  };
}
