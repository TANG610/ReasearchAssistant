export type Paper = {
  id: number;
  key: string;
  title: string;
  authors: string[];
  year?: number | null;
  venue: string;
  source: string;
  sources?: string[];
  url: string;
  pdf: string;
  abstract: string;
  abstract_zh: string;
  project_url: string;
  pdf_file_path: string;
  overview_figure_path: string;
  overview_caption: string;
  initial_parse_markdown: string;
  tags: string[];
  status: string;
  reading_status: string;
  priority: string;
  comment: string;
  note_path: string;
  note_markdown?: string;
  created_at: string;
  updated_at: string;
};

export type Job = {
  id: number;
  type: string;
  status: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error: string;
};

export type SearchCandidate = {
  id: number;
  run_id: number;
  paper_id?: number | null;
  key: string;
  title: string;
  authors: string[];
  year?: number | null;
  venue: string;
  source: string;
  sources: string[];
  ids: Record<string, unknown>;
  url: string;
  pdf: string;
  abstract: string;
  abstract_zh: string;
  project_url: string;
  tags: string[];
  priority: string;
  comment: string;
  pdf_file_path: string;
  overview_figure_path: string;
  overview_caption: string;
  initial_parse_markdown: string;
  parse_status: string;
  parse_error: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ChatResponse = {
  session_id: number;
  answer: string;
  citations: Array<{ paper_id: number; title: string; url: string; sources?: string[] }>;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export function getToken(): string {
  return localStorage.getItem("research_token") ?? "";
}

export function setToken(token: string): void {
  localStorage.setItem("research_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("research_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  papers: (params: URLSearchParams) => request<Paper[]>(`/papers?${params.toString()}`),
  paper: (id: number) => request<Paper>(`/papers/${id}`),
  updatePaper: (id: number, payload: Partial<Paper>) =>
    request<Paper>(`/papers/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deletePaper: (id: number) => request<{ deleted: boolean; id: number }>(`/papers/${id}`, { method: "DELETE" }),
  importPaper: (options: { url?: string; file?: File }) => {
    const body = new FormData();
    if (options.url) body.set("url", options.url);
    if (options.file) body.set("file", options.file);
    return request<Paper>("/papers/import", { method: "POST", body });
  },
  acceptPaper: (id: number) => request<Paper>(`/papers/${id}/accept`, { method: "POST", body: "{}" }),
  rejectPaper: (id: number) => request<Paper>(`/papers/${id}/reject`, { method: "POST", body: "{}" }),
  search: (query: string, limit: number, sources: string[]) =>
    request<Job>("/papers/search", {
      method: "POST",
      body: JSON.stringify({ query, sources, limit }),
    }),
  candidates: (runId: number) => request<SearchCandidate[]>(`/search-runs/${runId}/candidates`),
  ingestCandidate: (id: number) => request<Paper>(`/search-candidates/${id}/ingest`, { method: "POST", body: "{}" }),
  rejectCandidate: (id: number) => request<SearchCandidate>(`/search-candidates/${id}/reject`, { method: "POST", body: "{}" }),
  parseCandidate: (id: number) => request<SearchCandidate>(`/search-candidates/${id}/parse`, { method: "POST", body: "{}" }),
  backfillOverviews: (options: { force?: boolean; parse_missing?: boolean; high_confidence_only?: boolean } = {}) =>
    request<Job>("/papers/backfill-overviews", {
      method: "POST",
      body: JSON.stringify(options),
    }),
  importKnowledgeBase: () => request<Job>("/import/knowledge-base", { method: "POST", body: "{}" }),
  exportMarkdown: () => request<Job>("/export/markdown", { method: "POST", body: "{}" }),
  deepRead: (id: number) => request<Job>(`/papers/${id}/deep-read`, { method: "POST", body: "{}" }),
  chat: (message: string, sessionId?: number) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    }),
  fileUrl: (path: string) =>
    path ? `${API_BASE}/files/${path.split("/").map(encodeURIComponent).join("/")}?token=${encodeURIComponent(getToken())}` : "",
};
