import { useState } from "react";

export function GmailConnector() {
  const [connected] = useState(false); // intentionally hard-coded for demo
  const [importing, setImporting] = useState(false);
  const [lastImport, setLastImport] = useState<string | null>(null);

  const onConnect = () => {
    alert(
      "Gmail connector — coming soon.\n\nWill use Google OAuth to subscribe to an inbox label and ingest emails + attachments automatically into this case.",
    );
  };

  const onForceImport = async () => {
    setImporting(true);
    // Cosmetic only — simulate a sync cycle for the demo.
    await new Promise((r) => setTimeout(r, 1600));
    setImporting(false);
    setLastImport(new Date().toLocaleTimeString());
    alert(
      "Force import complete (demo).\n\n0 new emails — connect a Gmail account first.",
    );
  };

  return (
    <div className="mb-4 flex items-center gap-3 p-3 border border-line rounded-lg bg-gradient-to-r from-sky-50 to-emerald-50">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-lg">📬</span>
        <div>
          <div className="font-medium">
            Gmail connector{" "}
            <span className="text-[10px] font-semibold text-muted bg-stone-200 px-1.5 py-0.5 rounded">
              {connected ? "CONNECTED" : "NOT CONNECTED"}
            </span>
          </div>
          <div className="text-xs text-muted">
            {connected
              ? "Auto-syncs every 3 hours · new emails & attachments flow into this case."
              : "Auto-sync every 3 hours · one-click import of emails + attachments."}
            {lastImport && ` · last forced ${lastImport}`}
          </div>
        </div>
      </div>
      <div className="ml-auto flex gap-2">
        <button
          onClick={onForceImport}
          disabled={importing}
          className="px-3 py-1.5 text-xs border border-line rounded-md hover:bg-white disabled:opacity-50"
        >
          {importing ? "⟳ Syncing…" : "⇣ Force Import"}
        </button>
        <button
          onClick={onConnect}
          className="px-3 py-1.5 text-xs bg-ink text-white rounded-md hover:bg-stone-800"
        >
          {connected ? "Manage" : "Connect Gmail"}
        </button>
      </div>
    </div>
  );
}
