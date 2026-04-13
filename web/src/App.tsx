import { Link, Route, Routes } from "react-router-dom";
import CasesPage from "./pages/CasesPage";
import CasePage from "./pages/CasePage";
import ReviewPage from "./pages/ReviewPage";

export default function App() {
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-line bg-white">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="font-semibold tracking-tight text-ink">
            ⚖︎ LLM Lawyer
          </Link>
          <div className="text-xs text-muted">
            Case-scoped review · redaction · chat
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
