import type { EmailPreview } from "../lib/api";

/**
 * Render an email-sourced document inline (no PDF blob exists for these).
 * Mimics a minimal email-client layout — header grid + pre-wrapped body.
 */
export function EmailViewer({
  email,
  title,
}: {
  email: EmailPreview;
  title: string;
}) {
  return (
    <div className="w-full h-full overflow-y-auto bg-stone-50 p-6">
      <div className="max-w-3xl mx-auto bg-white border border-line rounded-lg shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-line bg-stone-50">
          <div className="text-[10px] uppercase tracking-widest text-muted mb-1">
            Email document
          </div>
          <div className="text-lg font-semibold text-ink">
            {email.subject || title || "(no subject)"}
          </div>
        </div>
        <div className="px-6 py-3 border-b border-line grid grid-cols-[70px_1fr] gap-y-1 text-sm">
          <div className="text-muted">From</div>
          <div className="font-mono">{email.from_addr || "—"}</div>
          <div className="text-muted">To</div>
          <div className="font-mono">{email.to_addrs || "—"}</div>
          <div className="text-muted">Date</div>
          <div className="font-mono">
            {email.timestamp
              ? new Date(email.timestamp).toLocaleString()
              : "—"}
          </div>
        </div>
        <div className="px-6 py-4 text-sm">
          {email.body ? (
            <pre className="whitespace-pre-wrap font-sans text-ink leading-relaxed">
              {email.body}
            </pre>
          ) : (
            <div className="italic text-muted">(no body)</div>
          )}
        </div>
      </div>
    </div>
  );
}
