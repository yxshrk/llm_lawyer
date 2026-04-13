import { Link, Route, Routes } from "react-router-dom";
import CasesPage from "./pages/CasesPage";
import CasePage from "./pages/CasePage";
import ReviewPage from "./pages/ReviewPage";

export default function App() {
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-line bg-white">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 font-semibold tracking-tight text-ink"
          >
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-ink text-white text-sm">
              ♞
            </span>
            <span className="text-lg">Gambit</span>
          </Link>
          <div className="text-xs text-muted">
            AI-powered eDiscovery · redaction · Q&amp;A rehearsal · opposing counsel analysis
          </div>
        </div>
      </header>
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<CasesPage />} />
          <Route path="/cases/:caseId" element={<CasePage />} />
          <Route
            path="/cases/:caseId/documents/:docId"
            element={<ReviewPage />}
          />
        </Routes>
      </main>
    </div>
  );
}
