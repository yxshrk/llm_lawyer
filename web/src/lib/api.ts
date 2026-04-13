const BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ===== Types =====
export type UUID = string;

export interface Case {
  id: UUID;
  name: string;
  client_name: string | null;
  matter_type: string | null;
  description: string | null;
  document_count?: number;
  memory_count?: number;
}

export interface Memory {
  id: UUID;
  case_id: UUID;
  kind: string; // rule | client_context | judge_order | firm_kb
  content: string;
}

export interface Document {
  id: UUID;
  case_id: UUID | null;
  email_id?: UUID | null;
  title: string;
  author?: string | null;
  source_type: string;
  storage_path: string;
  mime: string | null;
  page_count: number | null;
  chunk_count: number;
  signed_url?: string | null;
  created_at?: string | null;
  last_opened_at?: string | null;
}

export interface CaseDocument {
  id: UUID;
  title: string;
  author?: string | null;
  source_type: string;
  production_type?: "own" | "opposing";
  page_count: number | null;
  email_id?: string | null;
  relevancy_label?: "relevant" | "uncertain" | "irrelevant" | null;
  relevancy_score?: number | null;
  relevancy_reasoning?: string | null;
  created_at: string | null;
  last_opened_at: string | null;
}

export interface RedactionChallenge {
  id: UUID;
  case_id: UUID;
  redaction_id: UUID;
  run_id: UUID;
  challenge_question: string;
  suggested_answer: string | null;
  legal_basis: string | null;
  risk_flag: string | null;
  difficulty: "priority_inconsistency" | "hard_low_confidence" | "standard" | string;
  inconsistency_peer_id: UUID | null;
  lawyer_status: "pending" | "prepared" | "needs_work" | "will_revise" | string;
  lawyer_notes: string | null;
  redaction: {
    id: UUID;
    label: string;
    confidence: number | null;
    confidence_band: string;
    text_span: string;
    page: number | null;
    document_id: UUID;
  } | null;
}

export interface AuditEvent {
  id: UUID;
  case_id: UUID | null;
  document_id: UUID | null;
  actor: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  summary: string | null;
  metadata: Record<string, any>;
  created_at: string;
}

export interface EmailAttachment {
  id: UUID;
  title: string;
  source_type: string;
}

export interface Email {
  id: UUID;
  case_id: UUID;
  from_addr: string | null;
  to_addrs: string | null;
  subject: string | null;
  body: string | null;
  timestamp: string | null;
  production_type?: "own" | "opposing";
  created_at: string;
  attachments: EmailAttachment[];
}

export interface Redaction {
  id: UUID;
  document_id: UUID;
  chunk_id: UUID | null;
  page: number | null;
  bbox: number[] | null;
  text_span: string;
  label: string;
  confidence: number | null;
  reasoning: string | null;
  status: "pending" | "accepted" | "rejected" | "modified";
  modified_span?: string | null;
}

export interface Citation {
  n: number;
  chunk_id: UUID;
  document_id: UUID;
  page: number | null;
  bbox: number[] | null;
  score: number;
  preview: string;
}

export interface ChatReply {
  conversation_id: UUID;
  reply: string;
  model: string;
  citations: Citation[];
  usage: {
    provider: string;
    prompt_tokens: number;
    cached_prompt_tokens: number;
    completion_tokens: number;
  };
}

export interface Memo {
  document_id: UUID;
  content: string;
  model: string | null;
}

export interface StrengthsWeaknesses {
  document_id: UUID;
  content: {
    strengths: Array<{ point: string; detail: string; citations: number[]; confidence: number }>;
    weaknesses: Array<{ point: string; detail: string; citations: number[]; confidence: number }>;
  };
  model: string | null;
}

/** NDJSON reader shared by every streaming endpoint. Yields each JSON event
 * as soon as it hits a newline boundary. */
async function* ndjsonStream(
  url: string,
  init: RequestInit = {},
): AsyncGenerator<StreamEvent> {
  const res = await fetch(url, init);
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${text}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      try {
        yield JSON.parse(line) as StreamEvent;
      } catch (err) {
        console.warn("bad ndjson line", line, err);
      }
    }
  }
  if (buf.trim()) {
    try {
      yield JSON.parse(buf.trim()) as StreamEvent;
    } catch {
      /* ignore */
    }
  }
}

// ===== Streaming event types =====
export interface WebResult {
  type: "web_result";
  title: string;
  url: string;
  score: number;
  snippet: string;
}

export type StreamEvent =
  | { type: "started"; total_batches?: number; chunk_count?: number; doc_title?: string; stage_plan?: string[]; case_id?: string; query_preview?: string }
  | { type: "stage"; stage: string; doc_count?: number }
  | { type: "batch_start"; batch: number; total_batches: number }
  | { type: "batch_done"; batch: number; created: number; provider?: string; model?: string; error?: string }
  | { type: "redaction"; redaction: Redaction }
  | { type: "chunk_summarised"; ordinal: number; page?: number | null; summary: string }
  | { type: "memo"; content: string; model?: string; provider?: string }
  | { type: "challenge"; challenge: OpposingChallenge }
  | { type: "gap"; gap: OpposingGap }
  | WebResult
  | { type: "web_query"; query: string; note?: string }
  | { type: "doc"; document_id: string; title: string; label: string; score: number; reasoning: string }
  | { type: "inconsistency_scan"; pairs: number }
  | { type: "challenge"; challenge: RedactionChallenge }
  | { type: "done"; total?: number; challenges?: number; gaps?: number; run_id?: string }
  | { type: "error"; message: string };

export interface OpposingChallenge {
  chunk_ordinal: number | null;
  redacted_passage: string;
  stated_category: string;
  challenge: string;
  legal_basis: string;
  strength: "strong" | "moderate" | "speculative" | string;
  recommended_action: string;
}

export interface OpposingGap {
  expected_topic: string;
  gap_description: string;
  significance: string;
  recommended_action: string;
}

// ===== API =====
export const api = {
  // Cases
  listCases: () => request<Case[]>("/cases"),
  getCase: (id: UUID) => request<Case>(`/cases/${id}`),
  createCase: (data: Partial<Case>) =>
    request<Case>("/cases", { method: "POST", body: JSON.stringify(data) }),

  // Memories
  listMemories: (caseId: UUID) => request<Memory[]>(`/cases/${caseId}/memories`),
  createMemory: (caseId: UUID, kind: string, content: string) =>
    request<Memory>(`/cases/${caseId}/memories`, {
      method: "POST",
      body: JSON.stringify({ kind, content }),
    }),
  updateMemory: (caseId: UUID, memoryId: UUID, kind: string, content: string) =>
    request<Memory>(`/cases/${caseId}/memories/${memoryId}`, {
      method: "PUT",
      body: JSON.stringify({ kind, content }),
    }),
  deleteMemory: (caseId: UUID, memoryId: UUID) =>
    request<void>(`/cases/${caseId}/memories/${memoryId}`, { method: "DELETE" }),

  // Documents
  listCaseDocuments: (caseId: UUID, productionType?: "own" | "opposing") => {
    const qs = productionType ? `?production_type=${productionType}` : "";
    return request<CaseDocument[]>(`/cases/${caseId}/documents${qs}`);
  },
  getDocument: (id: UUID) => request<Document>(`/documents/${id}`),
  uploadDocumentWithType: async (file: File, caseId: UUID | null, productionType: "own" | "opposing") => {
    const fd = new FormData();
    fd.append("file", file);
    if (caseId) fd.append("case_id", caseId);
    fd.append("production_type", productionType);
    return request<Document>("/documents", { method: "POST", body: fd });
  },

  // Emails
  listEmails: (caseId: UUID, productionType?: "own" | "opposing") => {
    const qs = productionType ? `?production_type=${productionType}` : "";
    return request<Email[]>(`/cases/${caseId}/emails${qs}`);
  },
  createEmail: (
    caseId: UUID,
    data: {
      from_addr?: string;
      to_addrs?: string;
      subject?: string;
      body?: string;
      timestamp?: string;
      production_type?: "own" | "opposing";
    },
  ) =>
    request<Email>(`/cases/${caseId}/emails`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteEmail: (caseId: UUID, emailId: UUID) =>
    request<void>(`/cases/${caseId}/emails/${emailId}`, { method: "DELETE" }),
  uploadDocument: async (file: File, caseId: UUID | null) => {
    const fd = new FormData();
    fd.append("file", file);
    if (caseId) fd.append("case_id", caseId);
    return request<Document>("/documents", { method: "POST", body: fd });
  },

  // Redactions
  runRedactions: (docId: UUID, batchSize = 5) =>
    request<{ document_id: UUID; created: number; provider: string; model: string }>(
      `/documents/${docId}/redactions/run?batch_size=${batchSize}`,
      { method: "POST" },
    ),
  listRedactions: (docId: UUID) => request<Redaction[]>(`/documents/${docId}/redactions`),
  reviewRedaction: (redactionId: UUID, status: string, modified_span?: string) =>
    request<Redaction>(`/redactions/${redactionId}`, {
      method: "PATCH",
      body: JSON.stringify({ status, modified_span }),
    }),
  streamRedactions: (docId: UUID, batchSize = 5, signal?: AbortSignal) =>
    ndjsonStream(
      `${BASE_URL}/documents/${docId}/redactions/stream?batch_size=${batchSize}`,
      { method: "POST", signal },
    ),

  streamMemo: (docId: UUID, signal?: AbortSignal) =>
    ndjsonStream(
      `${BASE_URL}/documents/${docId}/memo/stream`,
      { method: "POST", signal },
    ),

  streamOpposingReview: (docId: UUID, signal?: AbortSignal) =>
    ndjsonStream(
      `${BASE_URL}/documents/${docId}/opposing_review/stream`,
      { method: "POST", signal },
    ),

  getOpposingReview: (docId: UUID) =>
    request<{ document_id: UUID; challenges: OpposingChallenge[]; gaps: OpposingGap[]; model: string | null } | null>(
      `/documents/${docId}/opposing_review`,
    ),

  // Relevancy filtering (streaming)
  streamRelevancy: (caseId: UUID, signal?: AbortSignal) =>
    ndjsonStream(`${BASE_URL}/cases/${caseId}/relevancy/stream`, {
      method: "POST",
      signal,
    }),

  // Audit trail
  listAudit: (caseId: UUID) => request<AuditEvent[]>(`/cases/${caseId}/audit`),
  auditCsvUrl: (caseId: UUID) => `${BASE_URL}/cases/${caseId}/audit.csv`,

  // Pipeline 2 — Q&A Challenge Set
  streamQa: (caseId: UUID, signal?: AbortSignal) =>
    ndjsonStream(`${BASE_URL}/cases/${caseId}/qa/run`, { method: "POST", signal }),
  listQa: (caseId: UUID) => request<RedactionChallenge[]>(`/cases/${caseId}/qa`),
  reviewChallenge: (id: UUID, lawyer_status: string, lawyer_notes?: string) =>
    request<RedactionChallenge>(`/redaction_challenges/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ lawyer_status, lawyer_notes }),
    }),

  // Chat
  chat: (message: string, opts: { conversation_id?: UUID; document_id?: UUID } = {}) =>
    request<ChatReply>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, ...opts }),
    }),

  // Memo
  generateMemo: (docId: UUID) =>
    request<Memo>(`/documents/${docId}/memo`, { method: "POST" }),
  getMemo: (docId: UUID) => request<Memo | null>(`/documents/${docId}/memo`),

  // Strengths / Weaknesses
  generateSW: (docId: UUID) =>
    request<StrengthsWeaknesses>(`/documents/${docId}/strengths_weaknesses`, { method: "POST" }),
  getSW: (docId: UUID) => request<StrengthsWeaknesses | null>(`/documents/${docId}/strengths_weaknesses`),
};
