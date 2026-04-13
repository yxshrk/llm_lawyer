import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Case } from "../lib/api";
import { Loader } from "../components/Loader";

export default function CasesPage() {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    name: "",
    client_name: "",
    matter_type: "",
    description: "",
  });

  const refresh = async () => {
    setLoading(true);
    try {
      setCases(await api.listCases());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    await api.createCase(form);
    setForm({ name: "", client_name: "", matter_type: "", description: "" });
    setCreating(false);
    await refresh();
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Cases</h1>
          <p className="text-sm text-muted">
            Each case groups documents and persistent memory applied to every AI call.
          </p>
        </div>
        <button
          className="px-4 py-2 bg-ink text-white text-sm rounded-md hover:bg-stone-800"
          onClick={() => setCreating((v) => !v)}
        >
          {creating ? "Cancel" : "+ New Case"}
        </button>
      </div>

      {creating && (
        <form
          onSubmit={onCreate}
          className="mb-6 p-4 bg-white border border-line rounded-lg grid grid-cols-2 gap-3"
        >
          <input
            className="col-span-2 border border-line rounded-md px-3 py-2 text-sm"
            placeholder="Case name (e.g. Acme v. Widget Corp)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <input
            className="border border-line rounded-md px-3 py-2 text-sm"
            placeholder="Client name"
            value={form.client_name}
            onChange={(e) => setForm({ ...form, client_name: e.target.value })}
          />
          <input
            className="border border-line rounded-md px-3 py-2 text-sm"
            placeholder="Matter type (Litigation, M&A, ...)"
            value={form.matter_type}
            onChange={(e) => setForm({ ...form, matter_type: e.target.value })}
          />
          <textarea
            className="col-span-2 border border-line rounded-md px-3 py-2 text-sm"
            placeholder="Description"
            rows={2}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <button className="col-span-2 px-4 py-2 bg-accent text-white text-sm rounded-md">
            Create Case
          </button>
        </form>
      )}

      {loading ? (
        <Loader />
      ) : cases.length === 0 ? (
        <div className="p-8 text-center border border-dashed border-line rounded-lg text-muted">
          No cases yet. Create one to get started.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {cases.map((c) => (
            <Link
              key={c.id}
              to={`/cases/${c.id}`}
              className="block p-4 bg-white border border-line rounded-lg hover:border-ink/40 transition"
            >
              <div className="font-medium text-ink">{c.name}</div>
              {c.client_name && (
                <div className="text-xs text-muted mt-1">
                  Client: {c.client_name}
                </div>
              )}
              {c.matter_type && (
                <div className="text-xs text-muted">{c.matter_type}</div>
              )}
              <div className="flex gap-3 mt-3 text-xs text-muted">
                <span>📄 {c.document_count ?? 0} docs</span>
                <span>🧠 {c.memory_count ?? 0} memories</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
