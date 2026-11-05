import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import rehypeHighlight from "rehype-highlight";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  Download,
  ExternalLink,
  FileCode2,
  FileText,
  FolderOpen,
  GitBranch,
  Grid2X2,
  History,
  Import,
  Leaf,
  List,
  Loader2,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Star,
  Upload,
  X,
  Archive,
  Save,
  Eye,
  TriangleAlert,
  RefreshCw,
} from "lucide-react";
import "./styles.css";
import Workbench from "./workbench";

type Obj = Record<string, any>;
const API = "/api/v1";
const MODULES = [
  { id: "writing", name: "文献撰写" },
  { id: "analysis", name: "数据分析与生图" },
];
function ModulePicker({ value, onChange }: any) {
  return (
    <fieldset className="module-picker">
      <legend>所属业务板块</legend>
      <div className="row wrap">
        {MODULES.map((m) => (
          <label className="checkbox" key={m.id}>
            <input
              type="checkbox"
              checked={value?.includes(m.id) || false}
              onChange={() =>
                onChange(
                  value?.includes(m.id)
                    ? value.filter((x) => x !== m.id)
                    : [...(value || []), m.id],
                )
              }
            />
            {m.name}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
function ModuleTags({ value }: any) {
  return (
    <>
      {MODULES.filter((m) => value?.includes(m.id)).map((m) => (
        <Tag key={m.id} kind="module">
          {m.name}
        </Tag>
      ))}
    </>
  );
}
const origins: Obj = {
  local: "本地创建",
  upload: "文件上传",
  github: "GitHub 导入",
  fork: "本地副本",
};
const statuses: Obj = {
  draft: "草稿",
  published: "已发布",
  archived: "回收站（已删除）",
  "imported-invalid": "格式待修复",
};
const nav = (url: string) => {
  history.pushState({}, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
};
function useLocation() {
  const [url, set] = useState(location.pathname + location.search);
  useEffect(() => {
    const f = () => set(location.pathname + location.search);
    window.addEventListener("popstate", f);
    return () => window.removeEventListener("popstate", f);
  }, []);
  return url;
}
function Link({ to, children, className = "", ...rest }: any) {
  return (
    <a
      href={to}
      className={className}
      {...rest}
      onClick={(e) => {
        if (!e.metaKey && !e.ctrlKey && !e.shiftKey && e.button === 0) {
          e.preventDefault();
          nav(to);
        }
      }}
    >
      {children}
    </a>
  );
}
async function api(path: string, method = "GET", data?: any) {
  const form = data instanceof FormData;
  const response = await fetch(API + path, {
    method,
    credentials: "same-origin",
    headers: data && !form ? { "Content-Type": "application/json" } : undefined,
    body: data ? (form ? data : JSON.stringify(data)) : undefined,
  });
  const body = await response.json();
  if (!response.ok) {
    const error: any = new Error(body.error?.message || "请求失败，请重试。");
    error.code = body.error?.code;
    error.details = body.error?.details;
    error.status = response.status;
    if (response.status === 401 && path != "/auth/login")
      window.dispatchEvent(new Event("signed-out"));
    throw error;
  }
  return body;
}
function useLoad(path: string | null, refresh = 0) {
  const [value, setValue] = useState<any>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    if (!path) {
      setLoading(false);
      setValue(null);
      return;
    }
    setLoading(true);
    setError("");
    api(path)
      .then((v) => {
        if (active) setValue(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, refresh]);
  return { value, error, loading };
}
function Loading() {
  return (
    <div className="loading" role="status">
      <Loader2 className="spin" size={22} />
      正在读取…
    </div>
  );
}
function ErrorBox({ text }: any) {
  return (
    <div className="error" role="alert">
      <TriangleAlert size={18} />
      <span>{text}</span>
    </div>
  );
}
function Tag({ children, kind = "" }: any) {
  return <span className={"tag " + kind}>{children}</span>;
}
function Md({ content }: any) {
  const frontmatter = (content || "").match(
    /^\uFEFF?---\s*\r?\n([\s\S]*?)\r?\n---(?:\s*\r?\n|$)/,
  );
  const body = frontmatter ? content.slice(frontmatter[0].length) : content;
  return (
    <div className="markdown">
      {frontmatter && (
        <details className="frontmatter">
          <summary>元数据（YAML）</summary>
          <pre>
            <code>{frontmatter[1]}</code>
          </pre>
        </details>
      )}
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, rehypeHighlight]}
        components={{
          img: () => <em>外部图片未加载，请查看来源。</em>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {body || "暂无内容。"}
      </Markdown>
    </div>
  );
}
function Modal({ title, children, onClose, wide = false }: any) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement;
    ref.current
      ?.querySelector<HTMLElement>("button,input,textarea,select")
      ?.focus();
    const handler = (e: KeyboardEvent) => {
      const dialogs = document.querySelectorAll("[role=dialog]");
      if (dialogs.length && dialogs[dialogs.length - 1] !== ref.current) return;
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const els = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled),input:not(:disabled),textarea,select,a[href]",
          ) || [],
        );
        if (e.shiftKey && document.activeElement === els[0]) {
          e.preventDefault();
          els.at(-1)?.focus();
        } else if (!e.shiftKey && document.activeElement === els.at(-1)) {
          e.preventDefault();
          els[0]?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      prev?.focus();
    };
  }, []);
  return (
    <div
      className="modal-shade"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={"modal " + (wide ? "wide" : "")}
      >
        <div className="modal-title">
          <h2>{title}</h2>
          <button className="icon" aria-label="关闭" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
function Diagnostics({ data }: any) {
  if (!data) return null;
  return (
    <div className="diagnostics">
      <div className="row wrap">
        <Tag kind={data.errors?.length ? "warn" : "green"}>
          {data.errors?.length ? "格式待修复" : "格式已校验"}
        </Tag>
        <Tag>
          {
            (
              {
                complete: "引用资源完整",
                incomplete: "引用资源缺失",
                unknown: "资源待确认",
              } as Obj
            )[data.resource_status]
          }
        </Tag>
      </div>
      {[...(data.errors || []), ...(data.warnings || [])].map((x, i) => (
        <p key={i} className={data.errors.includes(x) ? "danger" : "muted"}>
          {x}
        </p>
      ))}
      {data.missing_paths?.length > 0 && (
        <p className="mono small">缺失：{data.missing_paths.join("、")}</p>
      )}
      {data.unconfirmed_references?.length > 0 && (
        <p className="mono small">
          待确认：{data.unconfirmed_references.join("、")}
        </p>
      )}
      <p className="small muted">{data.reference_detection}</p>
    </div>
  );
}
function date(value: string) {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "—";
}
function size(n: number) {
  return n < 1024
    ? n + " B"
    : n < 1048576
      ? (n / 1024).toFixed(1) + " KB"
      : (n / 1048576).toFixed(1) + " MB";
}
function Files({ items, path, onSelect }: any) {
  return (
    <div className="file-tree" aria-label="技能包文件">
      {items?.map((f: Obj) => (
        <button
          key={f.path}
          title={f.path}
          className={"file " + (path === f.path ? "selected" : "")}
          style={{
            paddingLeft: 12 + Math.min(f.path.split("/").length - 1, 4) * 10,
          }}
          onClick={() => onSelect(f.path)}
        >
          <FileText size={15} />
          <span>{f.path}</span>
          <small>{size(f.size)}</small>
        </button>
      ))}
    </div>
  );
}

function App() {
  const url = useLocation(),
    [authenticated, setAuth] = useState<boolean | null>(null),
    [notice, setNotice] = useState(""),
    [fallback, setFallback] = useState<string | null>(null),
    [importOpen, setImportOpen] = useState(false),
    [refresh, setRefresh] = useState(0),
    [menu, setMenu] = useState(false);
  useEffect(() => {
    api("/auth/me")
      .then(() => setAuth(true))
      .catch(() => setAuth(false));
    const f = () => setAuth(false);
    window.addEventListener("signed-out", f);
    return () => window.removeEventListener("signed-out", f);
  }, []);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => setNotice(""), 4500);
      return () => clearTimeout(t);
    }
  }, [notice]);
  const notify = (x: string) => setNotice(x);
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      notify("已复制到剪贴板");
    } catch {
      setFallback(text);
    }
  };
  if (authenticated === null) return <Loading />;
  if (!authenticated)
    return (
      <Login
        onSuccess={() => {
          setAuth(true);
          setRefresh((x) => x + 1);
        }}
      />
    );
  const pathname = url.split("?")[0],
    parts = pathname.split("/").filter(Boolean);
  let page: any;
  const common = {
    notify,
    copy,
    refresh,
    onRefresh: () => setRefresh((x) => x + 1),
  };
  if (["algorithms", "plots", "runs"].includes(parts[0]))
    page = (
      <Workbench
        key={pathname}
        path={pathname}
        api={api}
        go={nav}
        notify={notify}
        Modal={Modal}
      />
    );
  else if (pathname === "/skills/new") page = <NewSkill {...common} />;
  else if (parts[0] === "skills" && parts[2] === "edit")
    page = <Editor key={url} sid={parts[1]} {...common} />;
  else if (parts[0] === "skills" && parts[1])
    page = <Detail key={parts[1]} sid={parts[1]} url={url} {...common} />;
  else if (pathname === "/sources") page = <Sources {...common} />;
  else
    page = (
      <Library url={url} {...common} onImport={() => setImportOpen(true)} />
    );
  return (
    <div className="shell">
      <aside className={"sidebar " + (menu ? "open" : "")}>
        <Link to="/skills" className="brand">
          <span className="brand-mark">
            <Leaf size={25} />
          </span>
          <span>
            BioFlow<small>Skill 中心</small>
          </span>
        </Link>
        <div className="side-caption">你的技能工作台</div>
        <nav>
          <Link
            to="/skills"
            className={pathname.startsWith("/skills") ? "active" : ""}
            onMouseUp={() => setMenu(false)}
          >
            <BookOpen size={19} />
            Skill 库
          </Link>
          <Link
            to="/sources"
            className={pathname === "/sources" ? "active" : ""}
            onMouseUp={() => setMenu(false)}
          >
            <GitBranch size={19} />
            来源与导入
          </Link>
          <Link
            to="/algorithms"
            className={pathname.startsWith("/algorithms") ? "active" : ""}
            onMouseUp={() => setMenu(false)}
          >
            <FileCode2 size={19} />
            算法库
          </Link>
          <Link
            to="/plots"
            className={pathname === "/plots" ? "active" : ""}
            onMouseUp={() => setMenu(false)}
          >
            <Eye size={19} />
            绘图示例与模板
          </Link>
          <Link
            to="/runs"
            className={pathname.startsWith("/runs") ? "active" : ""}
            onMouseUp={() => setMenu(false)}
          >
            <History size={19} />
            运行记录
          </Link>
        </nav>
        <button
          className="logout"
          onClick={async () => {
            await api("/auth/logout", "POST", {});
            setAuth(false);
          }}
        >
          <LogOut size={17} />
          退出登录
        </button>
      </aside>
      <div className="main">
        <div className="topbar">
          <button
            className="icon mobile-menu"
            aria-label="打开导航"
            onClick={() => setMenu(!menu)}
          >
            <Menu size={20} />
          </button>
          <span>
            工作空间 <span className="slash">/</span> Skill 中心
          </span>
          <div className="top-right">
            <span className="status-dot" />
            独立管理工作台<span className="avatar">XH</span>
          </div>
        </div>
        <main>{page}</main>
        <footer>BioFlow Skill 中心</footer>
      </div>
      {notice && (
        <div className="toast" role="status">
          <Check size={17} />
          {notice}
        </div>
      )}
      {fallback !== null && (
        <Modal
          title="剪贴板不可用，请手动复制"
          onClose={() => setFallback(null)}
        >
          <textarea
            className="copy-fallback"
            value={fallback}
            readOnly
            onFocus={(e) => e.target.select()}
          />
          <p className="muted">选中文本后按 Ctrl+C 复制。</p>
        </Modal>
      )}
      {importOpen && (
        <ImportDialog
          onClose={() => setImportOpen(false)}
          onComplete={() => {
            setImportOpen(false);
            setRefresh((x) => x + 1);
          }}
          notify={notify}
          defaultModules={
            new URLSearchParams(location.search).get("module")
              ? [new URLSearchParams(location.search).get("module")]
              : []
          }
        />
      )}
    </div>
  );
}

function Login({ onSuccess }: any) {
  const [username, setUser] = useState("xh"),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="login-page">
      <div className="login-card">
        <span className="login-logo">
          <Leaf size={30} />
        </span>
        <p className="eyebrow">BIOFLOW WORKSPACE</p>
        <h1>Skill 中心</h1>
        <p className="muted">管理技能，让可复用的方法有迹可循。</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              await api("/auth/login", "POST", { username, password });
              onSuccess();
            } catch (x: any) {
              setError(x.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            用户名
            <input
              autoComplete="username"
              value={username}
              onChange={(e) => setUser(e.target.value)}
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <ErrorBox text={error} />}
          <button className="primary full" disabled={busy}>
            {busy ? (
              <Loader2 className="spin" size={18} />
            ) : (
              <ArrowRight size={18} />
            )}
            登录工作台
          </button>
        </form>
      </div>
    </div>
  );
}

function Library({ url, refresh, onRefresh, onImport, notify }: any) {
  const params = new URLSearchParams(url.split("?")[1] || ""),
    [q, setQ] = useState(params.get("q") || ""),
    [view, setView] = useState(localStorage.getItem("sc-view") || "grid");
  const { value, error, loading } = useLoad(
    "/skills?" + params.toString(),
    refresh,
  );
  const update = (key: string, value: string) => {
    const p = new URLSearchParams(location.search);
    value ? p.set(key, value) : p.delete(key);
    if (key !== "page") p.delete("page");
    nav("/skills?" + p.toString());
  };
  useEffect(() => {
    const t = setTimeout(() => {
      if (q !== params.get("q") && !(q === "" && !params.get("q")))
        update("q", q);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setQ(params.get("q") || ""), [url]);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SKILL LIBRARY</p>
          <h1>Skill 库</h1>
        </div>
        <div className="actions">
          <button onClick={onImport}>
            <Import size={17} />
            导入 Skill
          </button>
          <Link
            className="button primary"
            to={
              params.get("module")
                ? "/skills/new?module=" + params.get("module")
                : "/skills/new"
            }
          >
            <Plus size={18} />
            新建 Skill
          </Link>
        </div>
      </div>
      <div className="module-tabs" role="tablist" aria-label="业务板块">
        <button
          role="tab"
          aria-selected={!params.get("module")}
          className={!params.get("module") ? "active" : ""}
          onClick={() => update("module", "")}
        >
          全部技能 <span>{value?.modules?.total ?? "—"}</span>
        </button>
        {MODULES.map((m) => (
          <button
            key={m.id}
            role="tab"
            aria-selected={params.get("module") === m.id}
            className={params.get("module") === m.id ? "active" : ""}
            onClick={() => update("module", m.id)}
          >
            {m.name}
            <span>
              {value?.modules?.items.find((x) => x.id === m.id)?.count ?? "—"}
            </span>
          </button>
        ))}
      </div>
      {params.get("module") && (
        <p className="module-description">
          {
            value?.modules?.items.find((x) => x.id === params.get("module"))
              ?.description
          }
        </p>
      )}
      <div className="toolbar">
        <div className="search">
          <Search size={18} />
          <input
            aria-label="搜索技能"
            placeholder="搜索名称、用途或标签…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {q && (
            <button
              className="icon"
              aria-label="清空搜索"
              onClick={() => setQ("")}
            >
              <X size={15} />
            </button>
          )}
        </div>
        <div className="view-switch">
          <button
            aria-label="卡片视图"
            aria-pressed={view === "grid"}
            className={view === "grid" ? "active" : ""}
            onClick={() => {
              setView("grid");
              localStorage.setItem("sc-view", "grid");
            }}
          >
            <Grid2X2 size={18} />
          </button>
          <button
            aria-label="列表视图"
            aria-pressed={view === "list"}
            className={view === "list" ? "active" : ""}
            onClick={() => {
              setView("list");
              localStorage.setItem("sc-view", "list");
            }}
          >
            <List size={19} />
          </button>
        </div>
      </div>
      <div className="filters">
        <label>
          类别
          <select
            aria-label="类别"
            value={params.get("category") || ""}
            onChange={(e) => update("category", e.target.value)}
          >
            <option value="">全部类别</option>
            {(
              value?.categories || ["文献", "写作", "分析", "可视化", "通用"]
            ).map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label>
          来源
          <select
            aria-label="来源"
            value={params.get("origin_type") || ""}
            onChange={(e) => update("origin_type", e.target.value)}
          >
            <option value="">全部来源</option>
            {Object.entries(origins).map(([k, v]) => (
              <option key={k} value={k}>
                {v as string}
              </option>
            ))}
          </select>
        </label>
        <label>
          状态
          <select
            aria-label="状态"
            value={params.get("content_status") || ""}
            onChange={(e) => update("content_status", e.target.value)}
          >
            <option value="">全部状态</option>
            {Object.entries(statuses)
              .filter(([k]) => k !== "imported-invalid")
              .map(([k, v]) => (
                <option key={k} value={k}>
                  {v as string}
                </option>
              ))}
          </select>
        </label>
        <button
          className={"filter-star " + (params.get("favorite") ? "active" : "")}
          onClick={() =>
            update("favorite", params.get("favorite") ? "" : "true")
          }
        >
          <Star size={16} />
          收藏
        </button>
        <label className="sort">
          排序
          <select
            aria-label="排序"
            value={params.get("sort") || "updated"}
            onChange={(e) => update("sort", e.target.value)}
          >
            <option value="updated">最近更新</option>
            <option value="recent">最近打开</option>
            <option value="name">名称</option>
          </select>
        </label>
      </div>
      <div className="result-meta">
        <span>{value ? `${value.total} 个技能` : "读取技能库"}</span>
        <span>发布状态与运行能力分别记录</span>
      </div>
      {error && <ErrorBox text={error} />}{" "}
      {loading ? (
        <Loading />
      ) : value?.items.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">
            <FolderOpen size={39} strokeWidth={1.4} />
          </div>
          <h2>{params.size ? "没有符合条件的 Skill" : "还没有 Skill"}</h2>
          <p>
            {params.size
              ? "试试其他搜索词或筛选条件。"
              : "从一个完整技能包开始，保存说明、脚本和参考资料。"}
          </p>
          <div className="actions">
            <button onClick={onImport}>
              <Upload size={17} />
              导入技能包
            </button>
            <Link className="button primary" to="/skills/new">
              <Plus size={17} />
              创建第一个 Skill
            </Link>
          </div>
          <div className="empty-formats">
            <FileText size={15} />
            SKILL.md <span>·</span> ZIP <span>·</span> GitHub 公开仓库
          </div>
        </div>
      ) : (
        <div className={view === "grid" ? "skill-grid" : "skill-list"}>
          {value?.items.map((s: Obj) => (
            <article className="skill-card" key={s.id}>
              <Link to={"/skills/" + s.id} className="card-main">
                <div className="card-top">
                  <span className="skill-icon">
                    <FileCode2 size={22} />
                  </span>
                  <Tag kind={s.content_status === "published" ? "green" : ""}>
                    {statuses[s.content_status]}
                  </Tag>
                </div>
                <h3>{s.display_name}</h3>
                <code className="standard-name">{s.skill_name}</code>
                <p>{s.display_summary || s.description || "用途尚未填写。"}</p>
                <div className="row wrap">
                  <Tag>{s.category}</Tag>
                  <ModuleTags value={s.applicable_modules} />
                  {s.tags.slice(0, 2).map((t) => (
                    <Tag key={t}>{t}</Tag>
                  ))}
                </div>
              </Link>
              <div className="card-bottom">
                <span>
                  <GitBranch size={13} />
                  {origins[s.origin_type]}
                  {s.version && ` · v${s.version}`}
                </span>
                <button
                  className={"icon " + (s.favorite ? "favorited" : "")}
                  aria-label={s.favorite ? "取消收藏" : "收藏技能"}
                  onClick={async () => {
                    try {
                      await api("/skills/" + s.id + "/favorite", "PUT", {
                        favorite: !s.favorite,
                      });
                      onRefresh();
                    } catch (e: any) {
                      notify(e.message);
                    }
                  }}
                >
                  <Star size={17} fill={s.favorite ? "currentColor" : "none"} />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {value?.total > 12 && (
        <div className="pagination">
          <button
            disabled={value.page <= 1}
            onClick={() => update("page", String(value.page - 1))}
          >
            上一页
          </button>
          <span>
            {value.page} / {Math.ceil(value.total / 12)}
          </span>
          <button
            disabled={value.page * 12 >= value.total}
            onClick={() => update("page", String(value.page + 1))}
          >
            下一页
          </button>
        </div>
      )}
    </>
  );
}

function NewSkill({ notify }: any) {
  const [form, setForm] = useState({
      skill_name: "",
      display_name: "",
      description: "",
      category: "通用",
      template: "blank",
      applicable_modules: new URLSearchParams(location.search).get("module")
        ? [new URLSearchParams(location.search).get("module")]
        : [],
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const change = (key, value) => setForm({ ...form, [key]: value });
  return (
    <>
      <Link className="back" to="/skills">
        <ArrowLeft size={16} />
        返回 Skill 库
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CREATE A SKILL</p>
          <h1>新建 Skill</h1>
          <p>先写清楚它解决什么问题，再逐步完善方法与资源。</p>
        </div>
      </div>
      <form
        className="panel create-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const result = await api("/skills", "POST", form);
            notify("草稿已创建");
            nav(`/skills/${result.skill.id}/edit?draft=${result.draft.id}`);
          } catch (x: any) {
            setError(x.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="form-grid">
          <label>
            展示名称
            <input
              aria-label="展示名称"
              value={form.display_name}
              onChange={(e) => change("display_name", e.target.value)}
              placeholder="例如：科研段落润色"
              maxLength={200}
            />
            <span className="hint">可用中文；不改变技能的标准名称。</span>
          </label>
          <label>
            标准名称
            <input
              aria-label="标准名称"
              value={form.skill_name}
              onChange={(e) => change("skill_name", e.target.value)}
              placeholder="academic-polishing"
              required
              pattern="[a-z0-9]+(-[a-z0-9]+)*"
              maxLength={64}
            />
            <span className="hint">
              小写字母、数字和单连字符，与目录名保持一致。
            </span>
          </label>
        </div>
        <label>
          用途与触发条件
          <textarea
            value={form.description}
            onChange={(e) => change("description", e.target.value)}
            placeholder="说明技能适合什么任务，以及什么时候使用。"
            required
            maxLength={1024}
            rows={3}
          />
        </label>
        <label>
          类别
          <input
            value={form.category}
            onChange={(e) => change("category", e.target.value)}
            list="categories"
            maxLength={80}
          />
          <datalist id="categories">
            {["文献", "写作", "分析", "可视化", "通用"].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </datalist>
        </label>
        <ModulePicker
          value={form.applicable_modules}
          onChange={(v) => change("applicable_modules", v)}
        />
        <label>选择起始模板</label>
        <div className="template-grid">
          {[
            ["blank", "空白技能", "从通用结构开始"],
            ["writing", "科研写作", "结构、表述与事实保留"],
            ["literature", "文献阅读", "提取方法与证据"],
            ["tool", "工具执行", "记录脚本与依赖"],
            ["visualization", "可视化", "组织数据与图表流程"],
          ].map(([id, name, desc]) => (
            <button
              key={id}
              type="button"
              className={"template " + (form.template === id ? "selected" : "")}
              onClick={() => change("template", id)}
            >
              <FileText size={21} />
              <strong>{name}</strong>
              <small>{desc}</small>
              {form.template === id && <Check size={15} />}
            </button>
          ))}
        </div>
        {error && <ErrorBox text={error} />}
        <div className="form-footer">
          <span>创建后进入编辑器，保存草稿与发布版本分开进行。</span>
          <button className="primary" disabled={busy}>
            {busy ? <Loader2 className="spin" size={17} /> : <Plus size={17} />}
            创建草稿
          </button>
        </div>
      </form>
    </>
  );
}

function Detail({ sid, url, refresh, onRefresh, notify, copy }: any) {
  const { value: s, error, loading } = useLoad("/skills/" + sid, refresh),
    params = new URLSearchParams(url.split("?")[1] || ""),
    tab = params.get("tab") || "overview";
  const { value: versions } = useLoad("/skills/" + sid + "/revisions", refresh);
  const rid =
    params.get("revision") || s?.published_revision_id || s?.latest_revision_id;
  const { value: r } = useLoad(
    rid ? `/skills/${sid}/revisions/${rid}` : null,
    refresh,
  );
  const [path, setPath] = useState(""),
    [raw, setRaw] = useState(false),
    [settings, setSettings] = useState(false),
    [diff, setDiff] = useState<any>(null),
    [actionBusy, setBusy] = useState(false);
  useEffect(() => {
    if (r) setPath(r.entry_path);
  }, [r?.id]);
  useEffect(() => {
    if (r && tab === "overview") setPath(r.entry_path);
  }, [tab, r?.id]);
  const {
    value: file,
    error: fileError,
    loading: fileLoading,
  } = useLoad(
    rid && path
      ? `/skills/${sid}/revisions/${rid}/files?path=${encodeURIComponent(path)}`
      : null,
  );
  const { value: usage } = useLoad(
    rid ? `/skills/${sid}/usage-options?revision_id=${rid}` : null,
  );
  const changeTab = (next: string) => {
    const p = new URLSearchParams(location.search);
    p.set("tab", next);
    nav(`/skills/${sid}?${p}`);
  };
  const fork = async () => {
    setBusy(true);
    try {
      const data = await api("/skills/" + sid + "/fork", "POST", {
        revision_id: rid,
      });
      notify("完整副本已创建");
      nav(`/skills/${data.skill.id}/edit?draft=${data.draft.id}`);
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  };
  const edit = async () => {
    if (s?.origin_type === "github" || s?.origin_type === "upload") {
      await fork();
      return;
    }
    if (s?.drafts.length) {
      nav(`/skills/${sid}/edit?draft=${s.drafts[0].id}`);
      return;
    }
    try {
      const data = await api("/skills/" + sid + "/drafts", "POST", {
        revision_id: rid,
      });
      nav(`/skills/${sid}/edit?draft=${data.id}`);
    } catch (e: any) {
      notify(e.message);
    }
  };
  if (loading) return <Loading />;
  if (error) return <ErrorBox text={error} />;
  if (!s) return null;
  return (
    <>
      <Link className="back" to="/skills">
        <ArrowLeft size={16} />
        返回 Skill 库
      </Link>
      <div className="page-heading detail-heading">
        <div>
          <div className="row wrap">
            <span className="detail-icon">
              <FileCode2 size={26} />
            </span>
            <p className="eyebrow">{origins[s.origin_type]}</p>
            <Tag kind={s.content_status === "published" ? "green" : ""}>
              {statuses[s.content_status]}
            </Tag>
          </div>
          <h1>{s.display_name}</h1>
          <p>{s.display_summary || s.description || "用途待补充。"}</p>
          <div className="row wrap small muted">
            <code>{s.skill_name}</code>
            <span>·</span>
            <span>{r ? `平台版本 v${r.platform_version}` : "未发布"}</span>
            <span>·</span>
            <span>{s.category}</span>
            <ModuleTags value={s.applicable_modules} />
          </div>
        </div>
        <div className="actions">
          <button
            aria-label={s.favorite ? "取消收藏" : "收藏技能"}
            className={s.favorite ? "favorited" : ""}
            onClick={async () => {
              await api(`/skills/${sid}/favorite`, "PUT", {
                favorite: !s.favorite,
              });
              onRefresh();
            }}
          >
            <Star size={17} fill={s.favorite ? "currentColor" : "none"} />
          </button>
          <button disabled={!rid || actionBusy} onClick={fork}>
            <Copy size={17} />
            创建副本
          </button>
          <button className="primary" disabled={actionBusy} onClick={edit}>
            <FileText size={17} />
            {["github", "upload"].includes(s.origin_type)
              ? "副本并编辑"
              : "编辑技能"}
          </button>
        </div>
      </div>
      <div className="detail-controls">
        <div className="actions">
          {rid && (
            <a
              className="button"
              href={`${API}/skills/${sid}/export?revision_id=${rid}`}
            >
              <Download size={16} />
              下载完整包
            </a>
          )}
          {usage?.content && (
            <button onClick={() => copy(usage.content)}>
              <Copy size={16} />
              复制正文
            </button>
          )}
          {r?.source_links && (
            <a
              className="button"
              href={r.source_links.original}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={16} />
              查看原 Skill
            </a>
          )}
          <button onClick={() => setSettings(true)}>
            <Settings2 size={16} />
            展示设置
          </button>
        </div>
        <button
          className="text-button"
          onClick={async () => {
            if (
              !confirm(
                s.archived_at
                  ? "从回收站恢复该技能？"
                  : "将技能移至回收站？历史版本和资源保留，可随时恢复。",
              )
            )
              return;
            await api(`/skills/${sid}/archive`, "POST", {
              archived: !s.archived_at,
            });
            notify(s.archived_at ? "技能已恢复" : "技能已移至回收站");
            onRefresh();
          }}
        >
          <Archive size={15} />
          {s.archived_at ? "恢复技能" : "删除技能"}
        </button>
      </div>
      {s.drafts.length > 0 && (
        <div className="draft-banner">
          <FileText size={17} />
          <span>有 {s.drafts.length} 份可编辑草稿。</span>
          <button className="text-button" onClick={edit}>
            继续编辑
            <ArrowRight size={15} />
          </button>
        </div>
      )}
      <div className="tabs" role="tablist">
        {[
          ["overview", "概览"],
          ["files", "文件"],
          ["usage", "使用方式"],
          ["versions", "版本"],
        ].map(([id, title]) => (
          <button
            role="tab"
            aria-selected={tab === id}
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => changeTab(id)}
          >
            {title}
          </button>
        ))}
        <div className="tab-spacer" />
        {versions?.items.length > 0 && (
          <select
            aria-label="选择版本"
            value={rid || ""}
            onChange={(e) => {
              const p = new URLSearchParams(location.search);
              p.set("revision", e.target.value);
              nav(`/skills/${sid}?${p}`);
            }}
          >
            {versions.items.map((v: Obj) => (
              <option key={v.id} value={v.id}>
                v{v.platform_version}
                {v.id === s.published_revision_id ? " · 当前" : ""}
              </option>
            ))}
          </select>
        )}
      </div>
      {!r && tab !== "versions" ? (
        <div className="panel empty compact">
          <FileText size={35} />
          <h2>这份技能还在草稿中</h2>
          <p>打开编辑器完成说明，然后发布第一个版本。</p>
          <button className="primary" onClick={edit}>
            打开草稿
          </button>
        </div>
      ) : null}
      {r && tab === "overview" && (
        <div className="detail-grid">
          <div className="panel content-panel">
            <div className="panel-heading">
              <h2>技能说明</h2>
              <Tag>原始内容</Tag>
            </div>
            {fileError ? (
              <ErrorBox text={fileError} />
            ) : fileLoading ? (
              <Loading />
            ) : (
              <Md content={path === r.entry_path ? file?.content : undefined} />
            )}
          </div>
          <aside className="detail-aside">
            <div className="panel">
              <h3>版本与内容</h3>
              <dl>
                <dt>平台版本</dt>
                <dd>v{r.platform_version}</dd>
                <dt>文件</dt>
                <dd>
                  {r.files.length} 个 ·{" "}
                  {size(r.files.reduce((a, f) => a + f.size, 0))}
                </dd>
                <dt>发布时间</dt>
                <dd>{date(r.created_at)}</dd>
                <dt>执行类型</dt>
                <dd>
                  {
                    (
                      {
                        unclassified: "未分类",
                        text: "文本",
                        tool: "工具",
                        manual: "手动",
                      } as Obj
                    )[s.execution_type]
                  }
                </dd>
                <dt>运行状态</dt>
                <dd>尚未接入在线运行</dd>
              </dl>
              <Diagnostics data={r.diagnostics} />
            </div>
            <div className="panel">
              <h3>来源可追溯</h3>
              {r.source_snapshot ? (
                <>
                  <p className="small">{r.source_snapshot.repository_url}</p>
                  <code className="hash">{r.source_snapshot.commit_sha}</code>
                  <div className="vertical-links">
                    <a
                      href={r.source_links?.imported}
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看导入提交
                      <ExternalLink size={13} />
                    </a>
                    <a
                      href={r.source_links?.latest}
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看最新来源
                      <ExternalLink size={13} />
                    </a>
                  </div>
                  <p className="small muted">
                    许可证：
                    {r.source_snapshot.license || "上游未识别，请查看包内文件"}
                  </p>
                </>
              ) : (
                <p className="muted">
                  {s.origin_type === "fork"
                    ? "本地副本，保留父技能和父版本。"
                    : "本地创建或文件上传，没有远程来源。"}
                </p>
              )}
              {s.parent_skill_id && (
                <Link
                  to={`/skills/${s.parent_skill_id}?revision=${s.parent_revision_id}`}
                >
                  查看父技能与版本
                  <ArrowRight size={13} />
                </Link>
              )}
            </div>
          </aside>
        </div>
      )}
      {r && tab === "files" && (
        <div className="panel browser-panel">
          <div className="file-sidebar">
            <div className="panel-heading">
              <strong>完整技能包</strong>
              <small>{r.files.length} 个文件</small>
            </div>
            <Files items={r.files} path={path} onSelect={setPath} />
          </div>
          <div className="file-content">
            <div className="file-heading">
              <code>{path}</code>
              <div className="actions">
                <button className="small-button" onClick={() => setRaw(!raw)}>
                  <Eye size={15} />
                  {raw ? "预览" : "原文"}
                </button>
                <a
                  className="button small-button"
                  href={`${API}/skills/${sid}/revisions/${rid}/files?path=${encodeURIComponent(path)}&download=true`}
                >
                  <Download size={15} />
                  下载文件
                </a>
              </div>
            </div>
            {fileError ? (
              <ErrorBox text={fileError} />
            ) : fileLoading ? (
              <Loading />
            ) : !raw && path.toLowerCase().endsWith(".md") ? (
              <Md content={file?.content} />
            ) : (
              <pre className="source">
                <code>{file?.content}</code>
              </pre>
            )}
          </div>
        </div>
      )}
      {r && tab === "usage" && (
        <div className="panel usage-panel">
          <h2>带走一份完整的方法</h2>
          <p className="muted">正文可复制，资源请随完整技能包一起保存。</p>
          <div className="usage-option">
            <div>
              <h3>Skill 正文</h3>
              <p>{usage?.copy_note}</p>
            </div>
            <button
              disabled={!usage?.content}
              onClick={() => copy(usage.content)}
            >
              <Copy size={16} />
              复制正文
            </button>
          </div>
          <div className="usage-option">
            <div>
              <h3>使用提示</h3>
              <p>包含技能名称、用途、版本及任务占位。</p>
            </div>
            <button disabled={!usage} onClick={() => copy(usage.prompt)}>
              <Copy size={16} />
              复制提示
            </button>
          </div>
          {usage?.install_command && (
            <pre className="command">
              <code>{usage.install_command}</code>
              <button
                className="icon"
                aria-label="复制安装命令"
                onClick={() => copy(usage.install_command)}
              >
                <Copy size={16} />
              </button>
            </pre>
          )}
          <p className="small muted">{usage?.install_note}</p>
          <div className="usage-option">
            <div>
              <h3>完整技能包</h3>
              <p>固定为当前选定版本，包含原文、资源和导出清单。</p>
            </div>
            <a
              className="button primary"
              href={`${API}/skills/${sid}/export?revision_id=${rid}`}
            >
              <Download size={16} />
              下载 ZIP
            </a>
          </div>
        </div>
      )}
      {tab === "versions" && (
        <div className="panel versions-panel">
          <h2>版本记录</h2>
          <p className="muted">发布快照保持不变。恢复旧版会新增发布记录。</p>
          {versions?.items.length === 0 && <p>尚未发布版本。</p>}
          {versions?.items.map((v: Obj, index: number) => (
            <div className="version-row" key={v.id}>
              <div className="version-mark">
                <History size={20} />
              </div>
              <div className="version-info">
                <div className="row wrap">
                  <strong>平台版本 v{v.platform_version}</strong>
                  {v.id === s.published_revision_id && (
                    <Tag kind="green">当前发布</Tag>
                  )}
                  <Tag>{statuses[v.status] || v.status}</Tag>
                </div>
                <p>{v.change_note || "发布技能版本"}</p>
                <small>
                  {date(v.created_at)} · {v.files.length} 个文件
                </small>
                <code className="hash">{v.content_hash}</code>
              </div>
              <div className="actions">
                <button
                  onClick={() => {
                    const p = new URLSearchParams();
                    p.set("revision", v.id);
                    p.set("tab", "files");
                    nav(`/skills/${sid}?${p}`);
                  }}
                >
                  查看
                </button>
                {index < versions.items.length - 1 && (
                  <button
                    onClick={async () => {
                      try {
                        setDiff(
                          await api(
                            `/skills/${sid}/diff?from_revision_id=${versions.items[index + 1].id}&to_revision_id=${v.id}`,
                          ),
                        );
                      } catch (e: any) {
                        notify(e.message);
                      }
                    }}
                  >
                    差异
                  </button>
                )}
                <button
                  disabled={
                    v.diagnostics.errors.length > 0 ||
                    v.id === s.published_revision_id
                  }
                  onClick={async () => {
                    if (
                      !confirm(
                        `恢复 v${v.platform_version}，并创建新发布记录？`,
                      )
                    )
                      return;
                    try {
                      await api(`/skills/${sid}/restore`, "POST", {
                        revision_id: v.id,
                      });
                      notify("旧版内容已作为新版本发布");
                      onRefresh();
                    } catch (e: any) {
                      notify(e.message);
                    }
                  }}
                >
                  恢复
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {settings && (
        <SettingsDialog
          skill={s}
          onClose={() => setSettings(false)}
          onDone={() => {
            setSettings(false);
            onRefresh();
          }}
        />
      )}
      {diff && <DiffDialog data={diff} onClose={() => setDiff(null)} />}
    </>
  );
}

function SettingsDialog({ skill, onClose, onDone }: any) {
  const [form, setForm] = useState({
      display_name: skill.display_name,
      display_summary: skill.display_summary,
      category: skill.category,
      tags: skill.tags.join(", "),
      enabled: skill.enabled,
      execution_type: skill.execution_type,
      applicable_modules: skill.applicable_modules || [],
    }),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const change = (k, v) => setForm({ ...form, [k]: v });
  return (
    <Modal title="展示与使用设置" onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("/skills/" + skill.id, "PATCH", {
              ...form,
              tags: form.tags
                .split(/[,，]/)
                .map((x) => x.trim())
                .filter(Boolean),
            });
            onDone();
          } catch (x: any) {
            setError(x.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          展示名称
          <input
            value={form.display_name}
            onChange={(e) => change("display_name", e.target.value)}
            required
            maxLength={200}
          />
        </label>
        <label>
          平台补充简介
          <textarea
            value={form.display_summary}
            onChange={(e) => change("display_summary", e.target.value)}
            rows={3}
            maxLength={2048}
          />
        </label>
        <div className="form-grid">
          <label>
            类别
            <input
              value={form.category}
              onChange={(e) => change("category", e.target.value)}
              maxLength={80}
            />
          </label>
          <label>
            标签
            <input
              value={form.tags}
              onChange={(e) => change("tags", e.target.value)}
              placeholder="逗号分隔"
            />
          </label>
        </div>
        <ModulePicker
          value={form.applicable_modules}
          onChange={(v) => change("applicable_modules", v)}
        />
        <label>
          执行类型
          <select
            value={form.execution_type}
            onChange={(e) => change("execution_type", e.target.value)}
          >
            <option value="unclassified">未分类</option>
            <option value="text">文本</option>
            <option value="tool">工具</option>
            <option value="manual">手动</option>
          </select>
          <span className="hint">声明类型不表示已验证可运行。</span>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => change("enabled", e.target.checked)}
          />
          启用
        </label>
        {error && <ErrorBox text={error} />}
        <div className="modal-footer">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary" disabled={busy}>
            保存设置
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Editor({ sid, notify }: any) {
  const did = new URLSearchParams(location.search).get("draft"),
    { value: loaded, error, loading } = useLoad(did ? "/drafts/" + did : null),
    [d, setD] = useState<Obj | null>(null),
    [path, setPath] = useState(""),
    [text, setText] = useState(""),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [fileError, setFileError] = useState(""),
    [mode, setMode] = useState(window.innerWidth <= 768 ? "edit" : "split"),
    [metaOpen, setMeta] = useState(false),
    [newPath, setNewPath] = useState<string | null>(null),
    [newContent, setNewContent] = useState(""),
    [note, setNote] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null),
    current = useRef("");
  current.current = text;
  const uploadRef = useRef<HTMLInputElement>(null);
  const loadFile = async (p: string) => {
    setFileError("");
    try {
      const f = await api(`/drafts/${did}/files?path=${encodeURIComponent(p)}`);
      setText(f.content);
      setPath(p);
      setDirty(false);
    } catch (e: any) {
      setPath(p);
      setText("");
      setDirty(false);
      setFileError(e.message);
    }
  };
  useEffect(() => {
    if (loaded) {
      setD(loaded);
      loadFile(loaded.entry_path);
    }
  }, [loaded?.id]);
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  useEffect(() => {
    const guard = (event: MouseEvent) => {
      const target = (event.target as HTMLElement).closest("a[href]");
      if (dirty && target && !confirm("当前文件有未保存的修改，确认离开？")) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    document.addEventListener("click", guard, true);
    return () => document.removeEventListener("click", guard, true);
  }, [dirty]);
  const save = async () => {
    if (!d) return null;
    const sent = text;
    setBusy(true);
    try {
      const next = await api(`/drafts/${did}/files`, "PATCH", {
        draft_counter: d.draft_counter,
        changes: [{ path, content: sent }],
      });
      setD(next);
      if (current.current === sent) setDirty(false);
      if (path === d.entry_path && next.entry_path !== d.entry_path)
        setPath(next.entry_path);
      notify("草稿已保存");
      return next;
    } catch (e: any) {
      setFileError(
        e.code === "REVISION_CONFLICT"
          ? e.message + " 当前文本已保留，请复制备份后刷新页面。"
          : e.message,
      );
      return null;
    } finally {
      setBusy(false);
    }
  };
  const publish = async () => {
    let next = d;
    if (dirty) {
      next = await save();
      if (!next) return;
    }
    if (!next) return;
    const diag = next.diagnostics;
    if (diag.errors.length) {
      setFileError("请先修复格式错误后发布。");
      return;
    }
    if (
      (diag.warnings.length || diag.resource_status !== "complete") &&
      !confirm("该版本有资源或格式提示。仍要发布为阅读版？")
    )
      return;
    setBusy(true);
    try {
      await api(`/drafts/${did}/publish`, "POST", {
        draft_counter: next.draft_counter,
        change_note: note,
      });
      setDirty(false);
      notify("新版本已发布");
      nav("/skills/" + sid);
    } catch (e: any) {
      setFileError(e.message);
    } finally {
      setBusy(false);
    }
  };
  if (loading) return <Loading />;
  if (error) return <ErrorBox text={error} />;
  if (!did) return <ErrorBox text="缺少草稿 ID，请从技能详情打开编辑器。" />;
  if (!d) return <Loading />;
  return (
    <>
      <Link className="back" to={"/skills/" + sid}>
        <ArrowLeft size={16} />
        返回技能详情
      </Link>
      <div className="page-heading editor-heading">
        <div>
          <p className="eyebrow">SKILL EDITOR</p>
          <h1>编辑技能包</h1>
        </div>
        <div className="actions">
          <Tag>{dirty ? "有未保存修改" : `草稿 #${d.draft_counter}`}</Tag>
          <button disabled={busy || !dirty || !!fileError} onClick={save}>
            <Save size={17} />
            保存草稿
          </button>
          <button className="primary" disabled={busy} onClick={publish}>
            {busy ? (
              <Loader2 className="spin" size={17} />
            ) : (
              <Check size={17} />
            )}
            发布版本
          </button>
        </div>
      </div>
      <div className="editor-config">
        <button onClick={() => setMeta(true)}>
          <Settings2 size={16} />
          基础信息表单
        </button>
        <label className="inline-label">
          版本说明
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="这次修改了什么？"
            maxLength={1000}
          />
        </label>
      </div>
      <div className="panel editor-panel">
        <div className="file-sidebar">
          <div className="panel-heading">
            <strong>包内文件</strong>
            <button
              className="icon"
              aria-label="添加文件"
              disabled={busy}
              onClick={() => {
                if (dirty) {
                  notify("请先保存当前文件，再新增资源。");
                  return;
                }
                setNewPath("");
                setNewContent("");
              }}
            >
              <Plus size={17} />
            </button>
          </div>
          <Files
            items={d.files}
            path={path}
            onSelect={(p) => {
              if (!dirty || confirm("当前文件有未保存修改，确认切换？"))
                loadFile(p);
            }}
          />
          <div className="file-tools">
            <button
              className="small-button"
              disabled={busy}
              onClick={() => uploadRef.current?.click()}
            >
              <Upload size={14} />
              上传资源
            </button>
            <input
              type="file"
              hidden
              ref={uploadRef}
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                const target = prompt(
                  "保存到包内相对路径：",
                  d.entry_path.replace(/SKILL\.md$/, "assets/") + f.name,
                );
                if (!target) return;
                if (dirty && target === path) {
                  notify("请先保存当前文件，再替换该资源。");
                  return;
                }
                setBusy(true);
                try {
                  const body = new FormData();
                  body.append("file", f);
                  const next = await api(
                    `/drafts/${did}/upload?path=${encodeURIComponent(target)}&draft_counter=${d.draft_counter}`,
                    "POST",
                    body,
                  );
                  setD(next);
                  if (target === path) await loadFile(path);
                  notify("资源已保存");
                } catch (x: any) {
                  setFileError(x.message);
                } finally {
                  setBusy(false);
                  e.target.value = "";
                }
              }}
            />
            {path !== d.entry_path && (
              <button
                className="text-button danger"
                disabled={busy}
                onClick={async () => {
                  if (!confirm("从草稿删除此文件？发布历史保持不变。")) return;
                  try {
                    const next = await api(`/drafts/${did}/files`, "PATCH", {
                      draft_counter: d.draft_counter,
                      changes: [{ path, delete: true }],
                    });
                    setD(next);
                    loadFile(next.entry_path);
                  } catch (e: any) {
                    setFileError(e.message);
                  }
                }}
              >
                删除当前文件
              </button>
            )}
          </div>
        </div>
        <div className="editor-work">
          <div className="file-heading">
            <code>{path}</code>
            <div className="view-switch editor-views">
              {[
                ["edit", "编辑"],
                ["split", "并排"],
                ["preview", "预览"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  className={mode === id ? "active" : ""}
                  onClick={() => setMode(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {fileError && <ErrorBox text={fileError} />}
          <div className={"edit-panes " + mode}>
            {mode !== "preview" && (
              <textarea
                ref={textarea}
                aria-label="文件编辑器"
                spellCheck={false}
                className="code-editor"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  setDirty(true);
                  setFileError("");
                }}
              />
            )}
            {mode !== "edit" && (
              <div className="preview-pane">
                {path.toLowerCase().endsWith(".md") ? (
                  <Md content={text} />
                ) : (
                  <pre className="source">
                    <code>{text}</code>
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="panel validation-panel">
        <div className="panel-heading">
          <h3>发布检查</h3>
          <button
            className="small-button"
            onClick={async () => {
              try {
                const data = await api(`/drafts/${did}/validate`, "POST", {});
                setD({ ...d, diagnostics: data });
                notify(
                  dirty ? "已检查保存的草稿；当前修改尚未保存" : "检查完成",
                );
              } catch (e: any) {
                setFileError(e.message);
              }
            }}
          >
            <ShieldCheck size={15} />
            检查已保存内容
          </button>
        </div>
        <Diagnostics data={d.diagnostics} />
        <p className="small muted">
          格式错误阻止发布；资源缺失的内容可以阅读，但不能声明为运行就绪。
        </p>
      </div>
      {metaOpen && (
        <MetadataDialog
          fields={d.diagnostics.metadata}
          entry={d.entry_path}
          onClose={() => setMeta(false)}
          onSave={async (fields) => {
            if (
              dirty &&
              !confirm(
                "表单将基于服务器已保存的 SKILL.md 更新。当前文件有未保存修改，仍继续？",
              )
            )
              return;
            try {
              const next = await api(`/drafts/${did}/files`, "PATCH", {
                draft_counter: d.draft_counter,
                metadata: fields,
              });
              setD(next);
              await loadFile(next.entry_path);
              setMeta(false);
              notify("基础信息已保存，扩展 YAML 字段已保留");
            } catch (e: any) {
              setFileError(e.message);
              throw e;
            }
          }}
        />
      )}
      {newPath !== null && (
        <Modal title="新增文本文件" onClose={() => setNewPath(null)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                if (d.files.some((f) => f.path === newPath))
                  throw new Error("该文件已存在，请在文件树中打开编辑。");
                const next = await api(`/drafts/${did}/files`, "PATCH", {
                  draft_counter: d.draft_counter,
                  changes: [{ path: newPath, content: newContent }],
                });
                setD(next);
                await loadFile(newPath);
                setNewPath(null);
                notify("文件已新增");
              } catch (x: any) {
                setFileError(x.message);
              }
            }}
          >
            <label>
              包内相对路径
              <input
                value={newPath}
                onChange={(e) => setNewPath(e.target.value)}
                placeholder="my-skill/references/notes.md"
                required
              />
            </label>
            <label>
              内容
              <textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                rows={8}
              />
            </label>
            <div className="modal-footer">
              <button type="button" onClick={() => setNewPath(null)}>
                取消
              </button>
              <button className="primary">创建文件</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

function MetadataDialog({ fields, entry, onSave, onClose }: any) {
  const [name, setName] = useState(
      fields.name || entry.split("/").at(-2) || "",
    ),
    [description, setDescription] = useState(
      typeof fields.description === "string" ? fields.description : "",
    ),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title="基础信息" onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await onSave({ name, description });
          } catch (x: any) {
            setError(x.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          标准名称
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            pattern="[a-z0-9]+(-[a-z0-9]+)*"
            maxLength={64}
          />
          <span className="hint">修改后同步调整包内技能目录名。</span>
        </label>
        <label>
          用途与触发条件
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            required
            maxLength={1024}
          />
        </label>
        {error && <ErrorBox text={error} />}
        <div className="modal-footer">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary" disabled={busy}>
            保存基础信息
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ImportDialog({
  onClose,
  onComplete,
  notify,
  initialJob,
  defaultModules = [],
}: any) {
  const [assignment, setAssignment] = useState<string[]>(defaultModules);
  const [kind, setKind] = useState("github"),
    [url, setUrl] = useState(""),
    [ref, setRef] = useState(""),
    [path, setPath] = useState(""),
    [job, setJob] = useState<Obj | null>(initialJob || null),
    [selected, setSelected] = useState<string[]>([]),
    [support, setSupport] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [copy, setCopy] = useState(false),
    [preview, setPreview] = useState<Obj | null>(null),
    [diff, setDiff] = useState<any>(null);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const t = setInterval(async () => {
      try {
        setJob(await api("/imports/" + job.id));
      } catch (e: any) {
        setError(e.message);
      }
    }, 1500);
    return () => clearInterval(t);
  }, [job?.id, job?.status]);
  useEffect(() => {
    if (job?.status === "ready") {
      setSelected(
        job.candidates.length === 1 ? [job.candidates[0].entry_path] : [],
      );
      if (job.update_skill_id)
        api("/sources").then((data) => {
          const s = data.items.find((x) => x.id === job.source_id);
          if (s) setSupport(s.support_paths || []);
        });
    }
  }, [job?.id, job?.status]);
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      setJob(
        await api("/imports/github/preview", "POST", {
          url,
          ref: ref || undefined,
          path: path || undefined,
        }),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const commit = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api("/imports/" + job?.id + "/commit", "POST", {
        entries: selected,
        support_paths: support,
        applicable_modules: assignment,
        new_copy: copy,
      });
      notify(
        `已保存 ${result.items.filter((x) => !x.skipped).length} 项，跳过 ${result.items.filter((x) => x.skipped).length} 个重复快照`,
      );
      onComplete(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const toggle = (p, list, set) =>
    set(list.includes(p) ? list.filter((x) => x !== p) : [...list, p]);
  return (
    <Modal
      wide
      title={job?.update_skill_id ? "检查并导入来源更新" : "导入完整 Skill"}
      onClose={onClose}
    >
      {!job && (
        <>
          <div className="tabs">
            <button
              className={kind === "github" ? "active" : ""}
              onClick={() => setKind("github")}
            >
              GitHub
            </button>
            <button
              className={kind === "upload" ? "active" : ""}
              onClick={() => setKind("upload")}
            >
              文件上传
            </button>
          </div>
          {kind === "github" ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                start();
              }}
            >
              <label>
                公开 GitHub 链接
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo/tree/main/my-skill"
                  type="url"
                  required
                />
              </label>
              <details>
                <summary>指定分支与路径（可选）</summary>
                <div className="form-grid">
                  <label>
                    分支 / 提交
                    <input
                      value={ref}
                      onChange={(e) => setRef(e.target.value)}
                      placeholder="feature/my-branch"
                    />
                  </label>
                  <label>
                    技能目录或 SKILL.md 路径
                    <input
                      value={path}
                      onChange={(e) => setPath(e.target.value)}
                      placeholder="skills/my-skill"
                    />
                  </label>
                </div>
              </details>
              <p className="small muted">
                扫描只下载文件，不运行仓库中的脚本或安装命令。
              </p>
              <button className="primary" disabled={busy}>
                {busy ? (
                  <Loader2 className="spin" size={17} />
                ) : (
                  <Search size={17} />
                )}
                扫描技能
              </button>
            </form>
          ) : (
            <label className="upload-zone">
              <Upload size={29} />
              <strong>选择 SKILL.md 或 ZIP 文件</strong>
              <span>上传不超过 50 MB · 保留完整目录和许可证</span>
              <input
                type="file"
                accept=".md,.zip"
                disabled={busy}
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setBusy(true);
                  setError("");
                  try {
                    const body = new FormData();
                    body.append("file", f);
                    setJob(await api("/imports/upload/preview", "POST", body));
                  } catch (x: any) {
                    setError(x.message);
                  } finally {
                    setBusy(false);
                  }
                }}
              />
              {busy && <Loader2 className="spin" size={18} />}
            </label>
          )}
        </>
      )}
      {job && (
        <>
          <div className="job-meta">
            <Tag kind={job.status === "ready" ? "green" : ""}>
              {
                (
                  {
                    queued: "等待扫描",
                    running: "扫描中",
                    ready: "扫描完成",
                    failed: "扫描失败",
                    cancelled: "已取消",
                    interrupted: "已中断",
                    committed: "已保存",
                  } as Obj
                )[job.status]
              }
            </Tag>
            <span>{job.progress}</span>
          </div>
          {job.source && (
            <div className="source-snapshot">
              <strong>{job.source.repository_url}</strong>
              <small>分支 {job.source.ref} · 固定提交</small>
              <code>{job.source.commit_sha}</code>
              <small>
                许可证：{job.source.license || "未识别，需查看包内许可证"}
              </small>
            </div>
          )}
          {["queued", "running"].includes(job.status) && (
            <div className="scan-progress">
              <Loader2 className="spin" size={27} />
              <p>正在读取真实仓库快照…</p>
              <button
                onClick={async () =>
                  setJob(
                    await api("/imports/" + job.id + "/cancel", "POST", {}),
                  )
                }
              >
                取消扫描
              </button>
            </div>
          )}
          {["failed", "cancelled", "interrupted"].includes(job.status) && (
            <>
              <ErrorBox text={job.error || "导入未完成。"} />
              <div className="actions">
                {job.input_type === "github" && (
                  <button
                    onClick={async () => {
                      try {
                        setJob(
                          await api(
                            "/imports/" + job.id + "/retry",
                            "POST",
                            {},
                          ),
                        );
                        setError("");
                      } catch (e: any) {
                        setError(e.message);
                      }
                    }}
                  >
                    <RefreshCw size={16} />
                    重试
                  </button>
                )}
                <button
                  onClick={() => {
                    setJob(null);
                    setError("");
                  }}
                >
                  重新选择来源
                </button>
              </div>
            </>
          )}
          {job.status === "ready" && (
            <>
              <ModulePicker value={assignment} onChange={setAssignment} />
              <div className="section-heading">
                <h3>选择要导入的技能</h3>
                <span>
                  {job.candidates.length} 个入口 · {job.files.length} 个文件
                </span>
              </div>
              <div className="candidate-list">
                {job.candidates.map((c: Obj) => (
                  <div className="candidate" key={c.entry_path}>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={selected.includes(c.entry_path)}
                        onChange={() =>
                          toggle(c.entry_path, selected, setSelected)
                        }
                      />
                      <strong>{c.skill_name}</strong>
                    </label>
                    <p>{c.description || "上游未提供有效用途描述。"}</p>
                    <code>{c.entry_path}</code>
                    <div className="row wrap">
                      <Tag>
                        {c.files.length} 个文件 ·{" "}
                        {size(c.files.reduce((a, f) => a + f.size, 0))}
                      </Tag>
                      {c.diagnostics.errors.length > 0 && (
                        <Tag kind="warn">格式待修复：仅保存阅读</Tag>
                      )}
                      {c.same_name_skills?.length > 0 && (
                        <Tag kind="warn">已有同名技能，按独立 ID 保存</Tag>
                      )}
                      <button
                        className="text-button"
                        onClick={() => setPreview(c)}
                      >
                        查看文件与诊断
                        <ArrowRight size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {job.support_files.length > 0 && (
                <details className="support-selection">
                  <summary>
                    共享与支持资源（{job.support_files.length} 个文件）
                  </summary>
                  <p className="small muted">
                    许可证自动保留。请依据引用确认其他共享资源，不能把检测线索当作确定依赖。
                  </p>
                  <div>
                    {job.support_files.map((f: Obj) => (
                      <label className="checkbox" key={f.path}>
                        <input
                          type="checkbox"
                          checked={support.includes(f.path)}
                          onChange={() => toggle(f.path, support, setSupport)}
                        />
                        <code>{f.path}</code>
                        <small>{size(f.size)}</small>
                      </label>
                    ))}
                  </div>
                </details>
              )}
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={copy}
                  onChange={(e) => setCopy(e.target.checked)}
                />
                相同来源与快照也创建新副本（默认跳过重复项）
              </label>
              {job.source_id && (
                <button
                  onClick={async () => {
                    try {
                      setDiff(
                        await api(
                          `/sources/${job.source_id}/diff?import_job_id=${job.id}`,
                        ),
                      );
                    } catch (e: any) {
                      setError(e.message);
                    }
                  }}
                >
                  <GitBranch size={16} />
                  比较来源差异
                </button>
              )}
              <div className="modal-footer">
                <span>发布有效内容；格式无效的原包保留为阅读快照。</span>
                <button
                  onClick={async () => {
                    await api(`/imports/${job.id}/cancel`, "POST", {});
                    onClose();
                  }}
                >
                  取消导入
                </button>
                <button
                  className="primary"
                  disabled={busy || selected.length === 0}
                  onClick={commit}
                >
                  {busy ? (
                    <Loader2 className="spin" size={17} />
                  ) : (
                    <Import size={17} />
                  )}
                  保存 {selected.length} 个技能
                </button>
              </div>
            </>
          )}
        </>
      )}
      {error && <ErrorBox text={error} />}
      <p className="small muted import-footnote">
        导入原版只读。需要修改时，创建包含全部资源的独立副本。
      </p>
      {preview && (
        <CandidatePreview
          job={job}
          candidate={preview}
          onClose={() => setPreview(null)}
        />
      )}
      {diff && <DiffDialog data={diff} onClose={() => setDiff(null)} />}
    </Modal>
  );
}

function DiffDialog({ data, onClose }: any) {
  return (
    <Modal wide title="文件版本差异" onClose={onClose}>
      {data.changes.length === 0 ? (
        <p className="muted">文件内容一致，没有变化。</p>
      ) : (
        data.changes.map((c: Obj) => (
          <details
            className="diff-file"
            key={c.path}
            open={data.changes.length === 1}
          >
            <summary>
              <Tag kind={c.change === "deleted" ? "warn" : "green"}>
                {
                  ({ added: "新增", deleted: "删除", modified: "修改" } as Obj)[
                    c.change
                  ]
                }
              </Tag>
              <code>{c.path}</code>
            </summary>
            {c.diff ? (
              <pre className="diff">
                <code>{c.diff}</code>
              </pre>
            ) : (
              <p className="small muted">
                二进制或大文件，以内容哈希比较。{c.before_hash} → {c.after_hash}
              </p>
            )}
          </details>
        ))
      )}
    </Modal>
  );
}

function Sources({ refresh, onRefresh, notify }: any) {
  const { value, error, loading } = useLoad("/sources", refresh),
    { value: jobs } = useLoad("/imports", refresh),
    [job, setJob] = useState<Obj | null>(null),
    [busy, setBusy] = useState("");
  const check = async (s: Obj) => {
    setBusy(s.id);
    try {
      setJob(await api(`/sources/${s.id}/check-update`, "POST", {}));
      onRefresh();
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SOURCES & SNAPSHOTS</p>
          <h1>来源与导入</h1>
          <p>追踪技能来自哪里，比较更新，再决定是否发布新版本。</p>
        </div>
        <button onClick={onRefresh}>
          <RefreshCw size={16} />
          刷新
        </button>
      </div>
      {error && <ErrorBox text={error} />}{" "}
      {loading ? (
        <Loading />
      ) : value?.items.length === 0 ? (
        <div className="panel empty compact">
          <GitBranch size={35} />
          <h2>暂无 GitHub 来源</h2>
          <p>从 Skill 库导入公开仓库后，来源记录会出现在这里。</p>
          <Link className="button" to="/skills">
            返回 Skill 库<ArrowRight size={16} />
          </Link>
        </div>
      ) : (
        <div className="source-grid">
          {value?.items.map((s: Obj) => (
            <div className="panel source-card" key={s.id}>
              <div className="row">
                <GitBranch size={20} />
                <strong>
                  {s.owner}/{s.repo}
                </strong>
              </div>
              <code>{s.skill_path}</code>
              <p className="small muted">
                分支：{s.ref} · 许可证：{s.license || "未识别"}
              </p>
              <p className="small muted">最近检查：{date(s.last_checked_at)}</p>
              <code className="hash">{s.last_commit_sha}</code>
              <div className="actions">
                <Link className="button" to={"/skills/" + s.skill_id}>
                  查看技能
                </Link>
                <button disabled={busy === s.id} onClick={() => check(s)}>
                  <RefreshCw size={15} />
                  检查更新
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="panel import-history">
        <div className="panel-heading">
          <h2>导入记录</h2>
          <span className="muted small">最近 100 次扫描</span>
        </div>
        {!jobs?.items.length ? (
          <p className="muted">尚无导入记录。</p>
        ) : (
          jobs.items.map((j: Obj) => (
            <div key={j.id} className="history-row">
              <span className="history-icon">
                {j.input_type === "github" ? (
                  <GitBranch size={18} />
                ) : (
                  <Upload size={18} />
                )}
              </span>
              <div>
                <strong>{j.input.url || j.input.filename}</strong>
                <small>
                  {date(j.created_at)} · {j.progress}
                </small>
                {j.error && <p className="danger small">{j.error}</p>}
              </div>
              <Tag>
                {
                  (
                    {
                      queued: "排队",
                      running: "扫描中",
                      ready: "待确认",
                      committed: "已保存",
                      failed: "失败",
                      cancelled: "已取消",
                      interrupted: "已中断",
                    } as Obj
                  )[j.status]
                }
              </Tag>
              {j.status !== "committed" && (
                <button onClick={() => setJob(j)}>查看</button>
              )}
            </div>
          ))
        )}
      </div>
      {job && (
        <ImportDialog
          initialJob={job}
          notify={notify}
          onClose={() => {
            setJob(null);
            onRefresh();
          }}
          onComplete={() => {
            setJob(null);
            onRefresh();
          }}
        />
      )}
    </>
  );
}

function CandidatePreview({ job, candidate, onClose }: any) {
  const [path, setPath] = useState(candidate.entry_path);
  const { value, error, loading } = useLoad(
    `/imports/${job.id}/files?path=${encodeURIComponent(path)}`,
  );
  return (
    <Modal
      title={candidate.skill_name + " · 文件与诊断"}
      wide
      onClose={onClose}
    >
      <Diagnostics data={candidate.diagnostics} />
      <div className="panel browser-panel">
        <div className="file-sidebar">
          <Files items={candidate.files} path={path} onSelect={setPath} />
        </div>
        <div className="file-content">
          {loading ? (
            <Loading />
          ) : error ? (
            <ErrorBox text={error} />
          ) : path.toLowerCase().endsWith(".md") ? (
            <Md content={value?.content} />
          ) : (
            <pre className="source">
              <code>{value?.content}</code>
            </pre>
          )}
        </div>
      </div>
    </Modal>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
