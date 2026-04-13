import { useEffect, useState } from "react";
import { cn } from "../lib/utils";

const STEPS = [
  { key: "upload", label: "Uploading file to Supabase Storage" },
  { key: "parse", label: "Extracting text with PyMuPDF" },
  { key: "chunk", label: "Chunking (~500 tokens per chunk)" },
  { key: "embed", label: "Embedding chunks (Voyage voyage-law-2)" },
  { key: "persist", label: "Persisting to Postgres + pgvector" },
] as const;

/** Fake progressive stepper — we don't have real progress from the backend
 * during a single-shot POST, so we rotate through steps and hold on the last
 * one until the fetch resolves. Good enough for demo storytelling. */
export function UploadStepper({ active, fileName }: { active: boolean; fileName?: string }) {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (!active) {
      setCurrent(0);
      return;
    }
    setCurrent(0);
    const interval = setInterval(() => {
      setCurrent((c) => Math.min(c + 1, STEPS.length - 1));
    }, 1100);
    return () => clearInterval(interval);
  }, [active]);

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6">
        <div className="mb-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Ingesting document
          </div>
          <div className="text-lg font-semibold truncate">
            {fileName ?? "document"}
          </div>
        </div>
        <ol className="space-y-3">
          {STEPS.map((s, i) => {
            const status =
              i < current ? "done" : i === current ? "active" : "pending";
            return (
              <li
                key={s.key}
                className={cn(
                  "flex items-center gap-3 text-sm transition",
                  status === "pending" && "opacity-40",
                )}
              >
                <span
                  className={cn(
                    "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold",
                    status === "done" && "bg-emerald-500 text-white",
                    status === "active" && "bg-accent text-white animate-pulse",
                    status === "pending" && "bg-stone-200 text-stone-500",
                  )}
                >
                  {status === "done" ? "✓" : i + 1}
                </span>
                <span
                  className={cn(
                    status === "active" && "font-medium text-ink",
                  )}
                >
                  {s.label}
                </span>
                {status === "active" && (
                  <span className="ml-auto flex gap-0.5">
                    <span className="w-1 h-1 bg-accent rounded-full animate-bounce" />
                    <span className="w-1 h-1 bg-accent rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-1 h-1 bg-accent rounded-full animate-bounce [animation-delay:-0.3s]" />
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
