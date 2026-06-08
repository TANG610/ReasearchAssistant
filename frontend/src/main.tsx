import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";
import {
  BookOpen,
  Bot,
  Check,
  Database,
  Download,
  Filter,
  ImageIcon,
  LogOut,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { api, clearToken, getToken, Paper, SearchCandidate, setToken } from "./lib/api";
import "katex/dist/katex.min.css";
import "./styles.css";

type Filters = {
  query: string;
  priority: string;
  reading_status: string;
  tag: string;
};

type CollectionOptions = {
  sources: string[];
  limit: number;
};

type JobResult = { status: string; result?: Record<string, unknown>; error?: string };
type DeepReadNotice = { status: "running" | "done" | "error"; text: string } | undefined;
type NoteSaveState = "idle" | "saving" | "saved" | "error";

const NOTE_TEMPLATE_PATTERNS = [
  /待补充/u,
  /待精读后回答/u,
  /输入：待补充/u,
  /输出：待补充/u,
  /可借鉴：待补充/u,
  /不适合直接借鉴：待补充/u,
  /实验设计：待补充/u,
  /图表\/写法：待补充/u,
];

function hasMeaningfulDeepReadNote(content?: string | null): boolean {
  if (!content?.trim()) return false;
  const remaining = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^#{1,6}\s/.test(line))
    .filter((line) => !NOTE_TEMPLATE_PATTERNS.some((pattern) => pattern.test(line)))
    .join("\n")
    .trim();
  return remaining.length >= 60;
}

function shouldShowDeepReadPanel(paper?: Paper): boolean {
  return paper?.reading_status === "read" && hasMeaningfulDeepReadNote(paper.note_markdown);
}

function MarkdownRenderer({
  content,
  fallback,
  className,
}: {
  content?: string | null;
  fallback: string;
  className?: string;
}) {
  const text = content?.trim() ? content : fallback;
  return (
    <div className={["markdownBody", className].filter(Boolean).join(" ")}>
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await api.login(username, password);
      setToken(result.access_token);
      onLogin();
    } catch {
      setError("登录失败，请检查用户名和密码。");
    }
  }

  return (
    <main className="loginPage">
      <form className="loginPanel" onSubmit={submit}>
        <div className="brand">
          <BookOpen size={30} />
          <div>
            <h1>科研工作台</h1>
            <p>论文筛选、精读和知识问答</p>
          </div>
        </div>
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" type="submit">
          登录
        </button>
      </form>
    </main>
  );
}

function Toolbar({
  filters,
  onFilters,
  onRefresh,
  onSearch,
  onManualImport,
  onExport,
  onBackfillOverviews,
  collection,
  onCollection,
  busy,
}: {
  filters: Filters;
  onFilters: (filters: Filters) => void;
  onRefresh: () => void;
  onSearch: () => void;
  onManualImport: () => void;
  onExport: () => void;
  onBackfillOverviews: () => void;
  collection: CollectionOptions;
  onCollection: (options: CollectionOptions) => void;
  busy: boolean;
}) {
  function toggleSource(source: string) {
    const current = new Set(collection.sources);
    if (current.has(source)) current.delete(source);
    else current.add(source);
    onCollection({ ...collection, sources: Array.from(current) });
  }

  return (
    <section className="toolbar">
      <div className="searchBox">
        <Search size={18} />
        <input
          placeholder="搜索标题、摘要、备注"
          value={filters.query}
          onChange={(event) => onFilters({ ...filters, query: event.target.value })}
        />
      </div>
      <div className="sourceBox">
        {[
          ["arxiv", "arXiv"],
          ["cvf", "CVPR/ICCV"],
          ["openreview", "NeurIPS"],
        ].map(([value, label]) => (
          <label key={value}>
            <input
              type="checkbox"
              checked={collection.sources.includes(value)}
              onChange={() => toggleSource(value)}
            />
            {label}
          </label>
        ))}
      </div>
      <label className="limitBox">
        <span>数量</span>
        <input
          type="number"
          min={1}
          max={50}
          value={collection.limit}
          onChange={(event) => onCollection({ ...collection, limit: Number(event.target.value) || 10 })}
        />
      </label>
      <select value={filters.priority} onChange={(event) => onFilters({ ...filters, priority: event.target.value })}>
        <option value="">全部优先级</option>
        <option value="A">A</option>
        <option value="B">B</option>
        <option value="C">C</option>
      </select>
      <select
        value={filters.reading_status}
        onChange={(event) => onFilters({ ...filters, reading_status: event.target.value })}
      >
        <option value="">全部状态</option>
        <option value="candidate">candidate</option>
        <option value="reading">reading</option>
        <option value="read">read</option>
        <option value="skipped">skipped</option>
      </select>
      <div className="tagBox">
        <Filter size={16} />
        <input
          placeholder="标签"
          value={filters.tag}
          onChange={(event) => onFilters({ ...filters, tag: event.target.value })}
        />
      </div>
      <button title="刷新列表" onClick={onRefresh} disabled={busy}>
        <RefreshCw size={17} />
      </button>
      <button title="按当前关键词搜索论文" onClick={onSearch} disabled={busy}>
        <Search size={17} />
      </button>
      <button title="导入论文链接或 PDF" onClick={onManualImport} disabled={busy}>
        <Upload size={17} />
      </button>
      <button title="重跑框架图" onClick={onBackfillOverviews} disabled={busy}>
        <ImageIcon size={17} />
      </button>
      <button title="导出 Markdown" onClick={onExport} disabled={busy}>
        <Download size={17} />
      </button>
    </section>
  );
}

function ImportPaperModal({
  busy,
  onClose,
  onSubmit,
}: {
  busy: boolean;
  onClose: () => void;
  onSubmit: (options: { url?: string; file?: File }) => Promise<void>;
}) {
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | undefined>();
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (!url.trim() && !file) {
      setError("请填写论文链接或上传 PDF。");
      return;
    }
    try {
      await onSubmit({ url: url.trim(), file });
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败。");
    }
  }

  return (
    <div className="modalBackdrop">
      <form className="modalPanel" onSubmit={submit}>
        <div className="modalHeader">
          <div>
            <h2>导入单篇论文</h2>
            <p>支持 arXiv 链接、PDF 链接，或直接上传 PDF；只生成初始数据，不自动精读。</p>
          </div>
          <button type="button" title="关闭" onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <label>
          论文链接
          <input placeholder="https://arxiv.org/abs/..." value={url} onChange={(event) => setUrl(event.target.value)} />
        </label>
        <label>
          上传 PDF
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(event) => setFile(event.target.files?.[0])}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="modalActions">
          <button type="button" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "导入中" : "导入"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CandidatePreview({
  candidates,
  onReload,
  onToast,
  onComplete,
}: {
  candidates: SearchCandidate[];
  onReload: () => Promise<void>;
  onToast: (text: string) => void;
  onComplete: (pendingCount: number) => void;
}) {
  const pendingCount = candidates.filter((candidate) => candidate.status === "pending").length;
  const rejectedCount = candidates.filter((candidate) => candidate.status === "rejected").length;
  const ingestedCount = candidates.filter((candidate) => candidate.status === "ingested").length;
  const visibleCandidates = candidates.filter((candidate) => candidate.status !== "ingested");

  async function action(callback: () => Promise<unknown>, done: string) {
    try {
      await callback();
      onToast(done);
      await onReload();
    } catch (error) {
      onToast(error instanceof Error ? error.message : "操作失败。");
    }
  }

  if (!candidates.length) {
    return <section className="candidatePanel empty">输入关键词并点击搜集，候选论文会显示在这里。</section>;
  }

  return (
    <section className="candidatePanel">
      <div className="candidateHeader">
        <div>
          <h2>候选论文预览</h2>
          <p>{candidates.length} 篇待筛选 · 入库后才进入问答知识库</p>
        </div>
        <div className="candidateSummary">
          <span>未筛选 {pendingCount}</span>
          <span>已筛出 {rejectedCount}</span>
          <span>已入库 {ingestedCount}</span>
          <button className="primary candidateDone" onClick={() => onComplete(pendingCount)}>
            完成全部筛选
          </button>
        </div>
      </div>
      <div className="candidateGrid">
        {visibleCandidates.length === 0 && (
          <div className="candidateEmpty">候选论文已全部入库，点击“完成全部筛选”回到论文处理页。</div>
        )}
        {visibleCandidates.map((candidate) => (
          <article className={`candidateCard ${candidate.status}`} key={candidate.id}>
            <div className="candidateTop">
              <span className={`priority p${candidate.priority}`}>{candidate.priority || "?"}</span>
              <div>
                <h3>{candidate.title}</h3>
                <p>
                  {candidate.year || "----"} · {candidate.venue || candidate.source || "未知"} · {candidate.parse_status}
                </p>
              </div>
            </div>
            <div className="overviewSlot">
              {candidate.overview_figure_path ? (
                <img src={api.fileUrl(candidate.overview_figure_path)} alt={candidate.overview_caption || candidate.title} />
              ) : (
                <div className="overviewPlaceholder">
                  <ImageIcon size={22} />
                  <span>未提取到框架图</span>
                </div>
              )}
            </div>
            {candidate.overview_caption && (
              <MarkdownRenderer content={candidate.overview_caption} fallback="" className="caption" />
            )}
            <div className="candidateAbstracts">
              <div>
                <h4>中文摘要</h4>
                <MarkdownRenderer content={candidate.abstract_zh} fallback="暂无中文摘要。" />
              </div>
              <div>
                <h4>英文摘要</h4>
                <MarkdownRenderer content={candidate.abstract} fallback="暂无英文摘要。" />
              </div>
            </div>
            {candidate.parse_error && <p className="parseError">{candidate.parse_error}</p>}
            <div className="candidateActions">
              <button
                className="primary"
                disabled={candidate.status === "ingested"}
                onClick={() => action(() => api.ingestCandidate(candidate.id), "已入库。")}
              >
                <Database size={16} />
                入库
              </button>
              <button onClick={() => action(() => api.parseCandidate(candidate.id), "已重新解析。")}>
                <RefreshCw size={16} />
                解析
              </button>
              <button disabled={candidate.status === "rejected"} onClick={() => action(() => api.rejectCandidate(candidate.id), "已跳过。")}>
                <X size={16} />
                跳过
              </button>
              <button onClick={() => window.open(candidate.pdf || candidate.url, "_blank", "noreferrer")}>PDF</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function PaperList({
  papers,
  selectedId,
  onSelect,
}: {
  papers: Paper[];
  selectedId?: number;
  onSelect: (id: number) => void;
}) {
  return (
    <section className="paperList">
      {papers.map((paper) => (
        <button
          className={`paperRow ${paper.id === selectedId ? "active" : ""}`}
          key={paper.id}
          onClick={() => onSelect(paper.id)}
        >
          <span className={`priority p${paper.priority}`}>{paper.priority || "?"}</span>
          <span className="paperTitle">{paper.title}</span>
          <span className="paperMeta">
            {paper.year || "----"} · {paper.venue || paper.source || "未知"} · {paper.reading_status}
          </span>
        </button>
      ))}
    </section>
  );
}

function PaperDetail({
  paper,
  onReload,
  onToast,
  onDelete,
}: {
  paper?: Paper;
  onReload: () => Promise<void> | void;
  onToast: (text: string) => void;
  onDelete: (paper: Paper) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [showMarkdown, setShowMarkdown] = useState(false);
  const [noteSaveState, setNoteSaveState] = useState<NoteSaveState>("idle");
  const [githubHint, setGithubHint] = useState(false);
  const [deepReadNotice, setDeepReadNotice] = useState<DeepReadNotice>();
  const githubHintTimer = useRef<number | undefined>(undefined);
  const deepReadNoticeTimer = useRef<number | undefined>(undefined);
  const noteSaveTimer = useRef<number | undefined>(undefined);
  const lastSavedDraft = useRef("");

  useEffect(() => {
    const nextDraft = paper?.note_markdown ?? "";
    setDraft(nextDraft);
    lastSavedDraft.current = nextDraft;
    setNoteSaveState("idle");
  }, [paper?.id, paper?.note_markdown]);

  useEffect(() => {
    setShowMarkdown(shouldShowDeepReadPanel(paper));
  }, [paper]);

  useEffect(() => {
    if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current);
    if (!paper || !showMarkdown) return;
    if (draft === lastSavedDraft.current) return;

    setNoteSaveState("saving");
    noteSaveTimer.current = window.setTimeout(() => {
      void (async () => {
        try {
          await api.updatePaper(paper.id, { note_markdown: draft });
          lastSavedDraft.current = draft;
          setNoteSaveState("saved");
        } catch (error) {
          setNoteSaveState("error");
          onToast(error instanceof Error ? error.message : "笔记自动保存失败。");
        }
      })();
    }, 700);

    return () => {
      if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current);
    };
  }, [draft, onToast, paper, showMarkdown]);

  useEffect(() => {
    return () => {
      if (githubHintTimer.current) window.clearTimeout(githubHintTimer.current);
      if (deepReadNoticeTimer.current) window.clearTimeout(deepReadNoticeTimer.current);
      if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current);
    };
  }, []);

  if (!paper) {
    return <section className="detail empty">选择一篇论文开始处理。</section>;
  }
  const current = paper;

  async function update(payload: Partial<Paper>) {
    await api.updatePaper(current.id, payload);
    await onReload();
  }

  function openExternal(url: string, emptyMessage: string) {
    if (!url) {
      onToast(emptyMessage);
      return;
    }
    window.open(url, "_blank", "noreferrer");
  }

  function openGithub() {
    if (current.project_url) {
      window.open(current.project_url, "_blank", "noreferrer");
      return;
    }
    setGithubHint(true);
    if (githubHintTimer.current) window.clearTimeout(githubHintTimer.current);
    githubHintTimer.current = window.setTimeout(() => setGithubHint(false), 1800);
  }

  async function saveNote() {
    if (!showMarkdown) {
      onToast("请先点击上方 AI 精读生成 Markdown。");
      return;
    }
    if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current);
    setNoteSaveState("saving");
    await api.updatePaper(current.id, { note_markdown: draft });
    lastSavedDraft.current = draft;
    setNoteSaveState("saved");
    onToast("笔记已保存。");
  }

  async function runDeepRead() {
    if (deepReadNoticeTimer.current) window.clearTimeout(deepReadNoticeTimer.current);
    setDeepReadNotice({ status: "running", text: "正在精读中" });
    try {
      const job = await api.deepRead(current.id);
      await onReload();
      if (job.status === "completed") {
        setShowMarkdown(true);
        setDeepReadNotice({ status: "done", text: "精读内容已生成" });
      } else {
        setDeepReadNotice({ status: "error", text: job.error || "精读任务提交失败" });
      }
    } catch (error) {
      setDeepReadNotice({ status: "error", text: error instanceof Error ? error.message : "精读任务失败" });
    } finally {
      deepReadNoticeTimer.current = window.setTimeout(() => setDeepReadNotice(undefined), 1800);
    }
  }

  return (
    <section className="detail">
      <div className="detailHeader">
        <div>
          <h2>{current.title}</h2>
          <p>
            {current.authors.slice(0, 5).join("、")}
            {current.authors.length > 5 ? " 等" : ""}
          </p>
        </div>
        <div className="actions">
          <button title="通过筛选" onClick={() => api.acceptPaper(current.id).then(onReload)}>
            <Check size={17} />
          </button>
          <button title="跳过" onClick={() => api.rejectPaper(current.id).then(onReload)}>
            <X size={17} />
          </button>
          <button title="AI 精读" onClick={runDeepRead} disabled={deepReadNotice?.status === "running"}>
            <Sparkles size={17} />
          </button>
          <button className="dangerIcon" title="删除论文" onClick={() => onDelete(current)}>
            <Trash2 size={17} />
          </button>
        </div>
      </div>
      {deepReadNotice && (
        <div className={`deepReadNotice ${deepReadNotice.status}`}>
          <span>{deepReadNotice.text}</span>
          {deepReadNotice.status === "running" && <span className="deepReadProgress" />}
        </div>
      )}
      <div className="fields">
        <label>
          优先级
          <select value={current.priority} onChange={(event) => update({ priority: event.target.value })}>
            <option>A</option>
            <option>B</option>
            <option>C</option>
          </select>
        </label>
        <label>
          阅读状态
          <select value={current.reading_status} onChange={(event) => update({ reading_status: event.target.value })}>
            <option>candidate</option>
            <option>reading</option>
            <option>read</option>
            <option>skipped</option>
          </select>
        </label>
        <label>
          标签
          <input
            value={current.tags.join(", ")}
            onChange={(event) =>
              update({
                tags: event.target.value
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
      </div>
      <div className="abstractGrid">
        <article className="abstractBlock">
          <h3>英文摘要</h3>
          <MarkdownRenderer content={current.abstract} fallback="暂无英文摘要。" />
        </article>
        <article className="abstractBlock">
          <h3>中文摘要</h3>
          <MarkdownRenderer content={current.abstract_zh} fallback="暂无中文摘要。" />
        </article>
      </div>
      <section className="overviewSection">
        <h3>框架图 / Overview</h3>
        {current.overview_figure_path ? (
          <>
            <img src={api.fileUrl(current.overview_figure_path)} alt={current.overview_caption || current.title} />
            {current.overview_caption && (
              <MarkdownRenderer content={current.overview_caption} fallback="" className="caption" />
            )}
          </>
        ) : (
          <div className="overviewPlaceholder">
            <ImageIcon size={24} />
            <span>暂无框架图，仍可继续精读。</span>
          </div>
        )}
      </section>
      {showMarkdown && (
        <div className="noteSection">
          <div className="noteHeader">
            <h3>精读笔记</h3>
            <span className={`noteSaveState ${noteSaveState}`}>
              {noteSaveState === "saving" && "正在自动保存..."}
              {noteSaveState === "saved" && "已自动保存"}
              {noteSaveState === "error" && "自动保存失败"}
              {noteSaveState === "idle" && "左侧编辑，右侧预览"}
            </span>
          </div>
          <div className="markdownPanel">
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
            <div className="notePreview">
            <MarkdownRenderer content={draft} fallback="暂无笔记内容。" />
          </div>
        </div>
        </div>
      )}
      <div className="footerActions">
        <button onClick={() => openExternal(current.pdf || current.url, "暂无论文链接。")}>PDF</button>
        <div className="githubAction">
          <button onClick={openGithub}>Github</button>
          {githubHint && <span className="githubHint">该项目暂未开源</span>}
        </div>
        <button className="primary" onClick={saveNote}>
          保存笔记
        </button>
      </div>
    </section>
  );
}

function Assistant({ onToast }: { onToast: (text: string) => void }) {
  const [message, setMessage] = useState("GaussianEditor 解决什么问题？");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Array<{ paper_id: number; title: string; url: string; sources?: string[] }>>([]);
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [busy, setBusy] = useState(false);

  async function ask() {
    if (!message.trim()) return;
    setBusy(true);
    try {
      const result = await api.chat(message, sessionId);
      setSessionId(result.session_id);
      setAnswer(result.answer);
      setCitations(result.citations);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "问答失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="assistant">
      <div className="assistantTitle">
        <Bot size={19} />
        <span>AI 助手</span>
      </div>
      <textarea value={message} onChange={(event) => setMessage(event.target.value)} />
      <button className="primary" onClick={ask} disabled={busy}>
        {busy ? "思考中" : "提问"}
      </button>
      <div className="answer">
        <MarkdownRenderer content={answer} fallback="可以问：这篇论文解决什么问题、下一步读什么、帮我想一个 idea。" />
      </div>
      {citations.length > 0 && (
        <div className="citations">
          {citations.map((citation) => (
            <button key={`${citation.paper_id}-${citation.title}`} onClick={() => citation.url && window.open(citation.url, "_blank", "noreferrer")}>
              {citation.title}
              <span>{(citation.sources || []).join(" / ") || "metadata"}</span>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}

function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(getToken()));
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selected, setSelected] = useState<Paper | undefined>();
  const [filters, setFilters] = useState<Filters>({ query: "", priority: "", reading_status: "", tag: "" });
  const [collection, setCollection] = useState<CollectionOptions>({ sources: ["arxiv", "cvf", "openreview"], limit: 10 });
  const [candidates, setCandidates] = useState<SearchCandidate[]>([]);
  const [activeRunId, setActiveRunId] = useState<number | undefined>();
  const [mainView, setMainView] = useState<"papers" | "candidates">("papers");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [showImportPaper, setShowImportPaper] = useState(false);

  const params = useMemo(() => {
    const next = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) next.set(key, value);
    });
    return next;
  }, [filters]);

  async function loadPapers() {
    setBusy(true);
    try {
      const list = await api.papers(params);
      setPapers(list);
      if (selected) {
        const fresh = list.find((paper) => paper.id === selected.id);
        setSelected(fresh ? await api.paper(fresh.id) : undefined);
      }
    } catch (error) {
      if (error instanceof Error && error.message.includes("401")) {
        clearToken();
        setAuthenticated(false);
      } else {
        setToast(error instanceof Error ? error.message : "加载失败。");
      }
    } finally {
      setBusy(false);
    }
  }

  async function selectPaper(id: number) {
    setSelected(await api.paper(id));
    setMainView("papers");
  }

  async function importPaper(options: { url?: string; file?: File }) {
    setBusy(true);
    try {
      const paper = await api.importPaper(options);
      setShowImportPaper(false);
      await loadPapers();
      setSelected(await api.paper(paper.id));
      setMainView("papers");
      setToast("论文已导入，已生成初始数据。");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "导入失败。");
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function deletePaper(paper: Paper) {
    if (!window.confirm(`确定删除《${paper.title}》吗？这会删除它在系统里的元数据、笔记和检索内容。`)) return;
    setBusy(true);
    try {
      await api.deletePaper(paper.id);
      setSelected(undefined);
      await loadPapers();
      setToast("论文已删除。");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "删除失败。");
    } finally {
      setBusy(false);
    }
  }

  async function loadCandidates(runId = activeRunId) {
    if (!runId) return;
    const list = await api.candidates(runId);
    setCandidates(list);
  }

  async function runAction(action: () => Promise<JobResult>) {
    setBusy(true);
    try {
      const job = await action();
      setToast(job.status === "completed" ? `完成：${JSON.stringify(job.result ?? {})}` : job.error || "任务已提交。");
      const runId = typeof job.result?.run_id === "number" ? job.result.run_id : undefined;
      if (runId) {
        setActiveRunId(runId);
        setCandidates(await api.candidates(runId));
        setMainView("candidates");
      }
      await loadPapers();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "任务失败。");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (authenticated) void loadPapers();
  }, [authenticated, params.toString()]);

  if (!authenticated) return <Login onLogin={() => setAuthenticated(true)} />;

  return (
    <main className="appShell">
      <header>
        <div>
          <h1>科研工作台</h1>
          <p>{papers.length} 篇论文 · 个人知识库</p>
        </div>
        <button
          title="退出登录"
          onClick={() => {
            clearToken();
            setAuthenticated(false);
          }}
        >
          <LogOut size={18} />
        </button>
      </header>
      <Toolbar
        filters={filters}
        onFilters={setFilters}
        onRefresh={loadPapers}
        onManualImport={() => setShowImportPaper(true)}
        onExport={() => runAction(() => api.exportMarkdown())}
        onBackfillOverviews={() => runAction(() => api.backfillOverviews({ force: true, parse_missing: true, high_confidence_only: true }))}
        collection={collection}
        onCollection={setCollection}
        onSearch={() =>
          runAction(() => api.search(filters.query || "3d-scene-editing", collection.limit, collection.sources.length ? collection.sources : ["arxiv"]))
        }
        busy={busy}
      />
      {toast && (
        <button className="toast" onClick={() => setToast("")}>
          {toast}
        </button>
      )}
      {showImportPaper && (
        <ImportPaperModal busy={busy} onClose={() => setShowImportPaper(false)} onSubmit={importPaper} />
      )}
      <div className="workspace">
        <PaperList papers={papers} selectedId={selected?.id} onSelect={selectPaper} />
        {mainView === "candidates" ? (
          <CandidatePreview
            candidates={candidates}
            onReload={async () => {
              await loadCandidates();
              await loadPapers();
            }}
            onToast={setToast}
            onComplete={(pendingCount) => {
              if (pendingCount > 0) {
                setToast(`还有 ${pendingCount} 篇论文未筛选。`);
                return;
              }
              setSelected(undefined);
              setMainView("papers");
              setToast("筛选已完成，请从左侧选择一篇论文开始处理。");
            }}
          />
        ) : (
          <PaperDetail paper={selected} onReload={loadPapers} onToast={setToast} onDelete={deletePaper} />
        )}
        <Assistant onToast={setToast} />
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
