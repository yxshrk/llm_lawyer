import { Link } from "react-router-dom";
import { type Email } from "../lib/api";

export function EmailModal({
  email,
  caseId,
  onClose,
}: {
  email: Email;
  caseId: string;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-line flex items-start justify-between">
          <div className="min-w-0">
            <div className="text-xs text-muted uppercase tracking-wide mb-1">
              Email
            </div>
            <div className="text-lg font-semibold truncate">
              {email.subject || "(no subject)"}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-muted hover:text-ink text-2xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4 border-b border-line grid grid-cols-[80px_1fr] gap-y-2 text-sm">
          <div className="text-muted">From</div>
          <div>{email.from_addr || "—"}</div>
          <div className="text-muted">To</div>
          <div>{email.to_addrs || "—"}</div>
          <div className="text-muted">Date</div>
          <div>
            {email.timestamp
              ? new Date(email.timestamp).toLocaleString()
              : "—"}
          </div>
          <div className="text-muted">Attachments</div>
          <div>
            {email.attachments.length === 0 ? (
              <span className="text-muted">None</span>
            ) : (
              <div className="flex flex-wrap gap-2">
                {email.attachments.map((a) => (
                  <Link
                    key={a.id}
                    to={`/cases/${caseId}/documents/${a.id}`}
                    onClick={onClose}
                    className="inline-flex items-center gap-1 text-xs bg-stone-100 hover:bg-stone-200 px-2 py-1 rounded"
                  >
                    📎 {a.title}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {email.body ? (
            <pre className="whitespace-pre-wrap font-sans text-sm text-ink">
              {email.body}
            </pre>
          ) : (
            <div className="text-sm text-muted italic">(no body)</div>
          )}
        </div>
      </div>
    </div>
  );
}
