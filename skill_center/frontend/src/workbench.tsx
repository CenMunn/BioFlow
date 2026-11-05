import React, { createContext, useContext, useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Download,
  FileUp,
  FlaskConical,
  History,
  Image,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  Upload,
} from "lucide-react";
import "./workbench.css";

const Context = createContext<any>(null);
const BASE = "/api/v1/workbench";
const LABELS: any = {
  queued: "等待运行",
  running: "运行中",
  succeeded: "已完成",
  failed: "运行失败",
  cancelled: "已取消",
  interrupted: "已中断",
  pending: "待验证",
  passed: "验证通过",
  catalog_only: "仅目录",
};
function useApi() {
  const c = useContext(Context);
  return {
    ...c,
    call: (path: string, method = "GET", data?: any) =>
      c.api("/workbench" + path, method, data),
  };
}
function useData(path: string, poll = false) {
  const { call } = useApi(),
    [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [counter, setCounter] = useState(0);
  useEffect(() => {
    let active = true,
      timer: any;
    setError("");
    setData(null);
    const load = () =>
      call(path)
        .then((d: any) => {
          if (!active) return;
          setData(d);
          if (poll && ["running", "queued"].includes(d.status))
            timer = setTimeout(load, 1300);
        })
        .catch((e: any) => active && setError(e.message));
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [path, counter]);
  return { data, error, reload: () => setCounter((x) => x + 1) };
}
function ErrorText({ text }: any) {
  return text ? (
    <div className="error" role="alert">
      {text}
    </div>
  ) : null;
}
function Badge({ state, children }: any) {
  return (
    <span
      className={
        "tag " +
        (["succeeded", "passed"].includes(state)
          ? "green"
          : state === "failed"
            ? "warn"
            : "")
      }
    >
      {children || LABELS[state] || state}
    </span>
  );
}
function Busy() {
  return (
    <div className="loading">
      <Loader2 className="spin" size={20} />
      正在读取…
    </div>
  );
}
function Route({ to, children, className = "" }: any) {
  const { go } = useApi();
  return (
    <a
      className={className}
      href={to}
      onClick={(e) => {
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          go(to);
        }
      }}
    >
      {children}
    </a>
  );
}
function Head({ eyebrow, title, description, children }: any) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="row wrap">{children}</div>
    </div>
  );
}
function DateText({ value }: any) {
  return <>{value ? new Date(value).toLocaleString("zh-CN") : "—"}</>;
}
function Table({ columns, rows }: any) {
  return (
    <div className="wb-table-scroll">
      <table className="wb-table">
        <thead>
          <tr>
            {columns.map((c: string) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r: any, i: number) => (
            <tr key={i}>
              {columns.map((c: string) => (
                <td key={c}>{String(r[c] ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Parameters({ schema, value, onChange }: any) {
  return (
    <div className="wb-fields">
      {Object.entries(schema || {}).map(([key, spec]: any) => (
        <label key={key}>
          {spec.label || key}
          {spec.enum ? (
            <select
              value={value[key] ?? spec.default}
              onChange={(e) => onChange({ ...value, [key]: e.target.value })}
            >
              {spec.enum.map((x: any) => (
                <option key={String(x)} value={String(x)}>
                  {String(x)}
                </option>
              ))}
            </select>
          ) : spec.type === "boolean" ? (
            <select
              value={String(value[key] ?? spec.default)}
              onChange={(e) =>
                onChange({ ...value, [key]: e.target.value === "true" })
              }
            >
              <option value="true">是</option>
              <option value="false">否</option>
            </select>
          ) : (
            <input
              type={
                ["integer", "number"].includes(spec.type) ? "number" : "text"
              }
              value={value[key] ?? spec.default ?? ""}
              min={spec.min}
              max={spec.max}
              step={spec.type === "integer" ? 1 : "any"}
              onChange={(e) =>
                onChange({
                  ...value,
                  [key]:
                    spec.type === "string"
                      ? e.target.value
                      : e.target.value === ""
                        ? ""
                        : Number(e.target.value),
                })
              }
            />
          )}
          <small className="muted">
            {spec.min !== undefined ? `${spec.min}～${spec.max}` : key}
          </small>
        </label>
      ))}
    </div>
  );
}
function PlotOptions({ value, onChange }: any) {
  return (
    <div className="wb-fields">
      <label>
        图标题
        <input
          value={value.title || ""}
          maxLength={160}
          onChange={(e) => onChange({ ...value, title: e.target.value })}
        />
      </label>
      <label>
        配色
        <select
          aria-label="配色"
          value={value.palette || "forest"}
          onChange={(e) => onChange({ ...value, palette: e.target.value })}
        >
          <option value="forest">森林绿</option>
          <option value="blue">蓝与暖色</option>
          <option value="colorblind">色觉友好</option>
        </select>
      </label>
      {[
        ["width", "宽度（英寸）", 8, 4, 14],
        ["height", "高度（英寸）", 5, 3, 12],
        ["font_size", "字体大小", 10, 8, 20],
      ].map(([key, label, def, min, max]: any) => (
        <label key={key}>
          {label}
          <input
            type="number"
            min={min}
            max={max}
            value={value[key] ?? def}
            onChange={(e) =>
              onChange({ ...value, [key]: Number(e.target.value) })
            }
          />
        </label>
      ))}
    </div>
  );
}

function ImportPackage({ algorithmId = "", onClose, onSaved }: any) {
  const { call, Modal } = useApi(),
    [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function save() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("algorithm_id", algorithmId);
      onSaved(await call("/algorithm-packages", "POST", form));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={algorithmId ? "导入算法新版本" : "导入算法源码包"}
      onClose={onClose}
    >
      <p>上传 ZIP，根目录需包含 algorithm.json 与 algorithm.py。</p>
      <p className="hint">请仅导入可信算法；所需依赖须提前安装。</p>
      <a href={BASE + "/examples/algorithm-package"} className="button">
        <Download size={16} />
        下载新增算法示例包
      </a>
      <label className="wb-upload">
        算法 ZIP 包
        <input
          type="file"
          accept=".zip"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>
      <ErrorText text={error} />
      <div className="form-footer">
        <button onClick={onClose}>取消</button>
        <button className="primary" disabled={!file || busy} onClick={save}>
          {busy ? "正在导入…" : "保存为待验证版本"}
        </button>
      </div>
    </Modal>
  );
}

function NewConfiguration({ items, onClose, onSaved }: any) {
  const { call, Modal } = useApi(),
    [baseId, setBase] = useState(items[0]?.id || ""),
    [name, setName] = useState(""),
    [display, setDisplay] = useState(""),
    [defaults, setDefaults] = useState<any>({}),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const base = items.find((e: any) => e.id === baseId)?.active_version;
  async function save(e: any) {
    e.preventDefault();
    setBusy(true);
    try {
      onSaved(
        await call("/algorithms", "POST", {
          name,
          display_name: display,
          base_algorithm_id: baseId,
          defaults: { ...base.defaults, ...defaults },
        }),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="新增算法配置" onClose={onClose}>
      <form onSubmit={save}>
        <div className="wb-fields">
          <label>
            基础算法
            <select
              value={baseId}
              onChange={(e) => {
                setBase(e.target.value);
                setDefaults({});
              }}
            >
              {items.map((a: any) => (
                <option key={a.id} value={a.id}>
                  {a.display_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            标准名称
            <input
              required
              pattern="[a-z0-9]+(-[a-z0-9]+)*"
              placeholder="pca-project-a"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            展示名称
            <input
              required
              value={display}
              onChange={(e) => setDisplay(e.target.value)}
            />
          </label>
        </div>
        <Parameters
          schema={base?.parameters}
          value={{ ...base?.defaults, ...defaults }}
          onChange={setDefaults}
        />
        <ErrorText text={error} />
        <div className="form-footer">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary" disabled={busy}>
            保存配置草稿
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Algorithms() {
  const [view, setView] = useState("active");
  const { data, error, reload } = useData(
      "/algorithms?archived=" + (view === "trash"),
    ),
    { go } = useApi(),
    [q, setQ] = useState(""),
    [category, setCategory] = useState(""),
    [modal, setModal] = useState("");
  const items = data?.items || [],
    shown = items.filter(
      (a: any) =>
        (!category || a.category === category) &&
        `${a.display_name} ${a.name} ${a.description} ${a.category}`
          .toLowerCase()
          .includes(q.trim().toLowerCase()),
    );
  return (
    <>
      <Head eyebrow="ALGORITHM LIBRARY" title="算法库">
        <button
          onClick={() => setModal("configuration")}
          disabled={
            !items.some(
              (x: any) => !x.archived_at && x.enabled && x.active_version,
            )
          }
        >
          <Plus size={17} />
          新增算法配置
        </button>
        <button className="primary" onClick={() => setModal("import")}>
          <Upload size={17} />
          导入算法包
        </button>
      </Head>
      <div className="wb-toolbar">
        <input
          aria-label="搜索算法"
          placeholder="搜索算法名称、任务或用途…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          aria-label="算法列表范围"
          value={view}
          onChange={(e) => {
            setView(e.target.value);
            setCategory("");
          }}
        >
          <option value="active">算法库</option>
          <option value="trash">回收站</option>
        </select>
        <select
          aria-label="算法类别"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">全部类别</option>
          {[...new Set(items.map((a: any) => a.category))].map((c: any) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <button className="icon" aria-label="刷新算法库" onClick={reload}>
          <RefreshCw size={17} />
        </button>
      </div>
      <ErrorText text={error} />
      {!data && !error ? (
        <Busy />
      ) : (
        <>
          <p className="muted">{shown.length} 个算法</p>
          <div className="wb-grid">
            {shown.map((a: any) => (
              <article className="panel wb-card" key={a.id}>
                <div className="row between">
                  <span className="file-icon">
                    <FlaskConical size={20} />
                  </span>
                  <Badge
                    state={
                      a.active_version
                        ? "passed"
                        : a.versions[0]?.validation_status
                    }
                  >
                    {a.archived_at
                      ? "已删除"
                      : a.active_version
                        ? a.enabled
                          ? "可运行"
                          : "已停用"
                        : a.versions[0]?.validation_status === "catalog_only"
                          ? "仅目录"
                          : "待验证"}
                  </Badge>
                </div>
                <h2>
                  <Route to={"/algorithms/" + a.id}>{a.display_name}</Route>
                </h2>
                <code>{a.name}</code>
                <p className="wb-clamp">{a.description}</p>
                <div className="row wrap">
                  <span className="tag">{a.category}</span>
                  <span className="tag">
                    {a.origin === "builtin"
                      ? "已有算法"
                      : a.origin === "package"
                        ? "算法源码包"
                        : "参数配置"}
                  </span>
                  {a.active_version && (
                    <span className="tag">v{a.active_version.number}</span>
                  )}
                </div>
                <div className="wb-card-footer">
                  <Route className="button" to={"/algorithms/" + a.id}>
                    {a.archived_at
                      ? "查看与恢复"
                      : a.active_version && a.enabled
                        ? "选择使用"
                        : "查看详情"}
                    <ArrowRight size={15} />
                  </Route>
                </div>
              </article>
            ))}
          </div>
          {!shown.length && <div className="panel">没有符合条件的算法。</div>}
        </>
      )}
      {modal === "import" && (
        <ImportPackage
          onClose={() => setModal("")}
          onSaved={(a: any) => go("/algorithms/" + a.id)}
        />
      )}{" "}
      {modal === "configuration" && (
        <NewConfiguration
          items={items.filter(
            (a: any) => !a.archived_at && a.active_version && a.enabled,
          )}
          onClose={() => setModal("")}
          onSaved={(a: any) => go("/algorithms/" + a.id)}
        />
      )}
    </>
  );
}

function EditAlgorithm({ entry, onClose, onSaved }: any) {
  const { call, Modal } = useApi(),
    [form, setForm] = useState({
      display_name: entry.display_name,
      description: entry.description,
      category: entry.category,
    }),
    [error, setError] = useState("");
  return (
    <Modal title="算法展示设置" onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await call("/algorithms/" + entry.id, "PATCH", {
              ...form,
              updated_at: entry.updated_at,
            });
            onSaved();
          } catch (e: any) {
            setError(e.message);
          }
        }}
      >
        <div className="wb-fields">
          {[
            ["display_name", "展示名称"],
            ["category", "类别"],
          ].map(([k, label]) => (
            <label key={k}>
              {label}
              <input
                required
                value={form[k]}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              />
            </label>
          ))}
        </div>
        <label>
          用途说明
          <textarea
            rows={4}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </label>
        <ErrorText text={error} />
        <div className="form-footer">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary">保存展示设置</button>
        </div>
      </form>
    </Modal>
  );
}

function NewVersion({ entry, onClose, onSaved }: any) {
  const { call, Modal } = useApi(),
    base = entry.active_version || entry.versions[0],
    [defaults, setDefaults] = useState(base.defaults),
    [note, setNote] = useState(""),
    [error, setError] = useState("");
  return (
    <Modal title="保存新的参数版本" onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await call("/algorithms/" + entry.id + "/versions", "POST", {
              base_version_id: base.id,
              defaults,
              change_note: note || "参数更新",
            });
            onSaved();
          } catch (e: any) {
            setError(e.message);
          }
        }}
      >
        <p className="hint">已发布版本保持原样。新参数版本需要验证后再发布。</p>
        <Parameters
          schema={base.parameters}
          value={defaults}
          onChange={setDefaults}
        />
        <label>
          修改说明
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <ErrorText text={error} />
        <div className="form-footer">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary">保存待验证版本</button>
        </div>
      </form>
    </Modal>
  );
}

function DatasetChooser({ value, onChange, example = "matrix" }: any) {
  const { call } = useApi(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function load(file: File) {
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      onChange(await call("/datasets", "POST", form));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function useExample() {
    try {
      setBusy(true);
      const r = await fetch(BASE + "/examples/" + example);
      if (!r.ok) throw new Error("示例文件读取失败");
      await load(
        new File([await r.blob()], "synthetic-" + example + ".csv", {
          type: "text/csv",
        }),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel wb-dataset">
      <div className="panel-heading">
        <h2>1 · 选择数据</h2>
        <span className="tag">CSV / TSV / TXT / XLSX</span>
      </div>
      <div className="row wrap">
        <label className="button wb-file-input">
          <FileUp size={16} />
          {busy ? "读取数据中…" : "上传数据文件"}
          <input
            type="file"
            accept=".csv,.tsv,.txt,.xlsx"
            disabled={busy}
            onChange={(e) => e.target.files?.[0] && load(e.target.files[0])}
          />
        </label>
        <button disabled={busy} onClick={useExample}>
          使用合成示例
        </button>
        <a href={BASE + "/examples/" + example} className="button">
          <Download size={15} />
          下载示例
        </a>
      </div>
      <p className="hint">
        第一行为列名，每行为一个样本；文件最多 10 MB。XLSX
        读取第一个工作表，不自动补缺失值。
      </p>
      <ErrorText text={error} />
      {value && (
        <>
          <p>
            <strong>{value.filename}</strong> · {value.rows} 行 ×{" "}
            {value.columns.length} 列
          </p>
          <Table
            columns={value.columns.slice(0, 8).map((c: any) => c.name)}
            rows={value.preview}
          />
          <p className="hint">显示前 8 行、8 列。</p>
        </>
      )}
    </section>
  );
}

function ColumnSelect({
  label,
  value,
  onChange,
  columns,
  required = false,
}: any) {
  return (
    <label>
      {label}
      <select
        aria-label={label}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{required ? "请选择" : "不使用"}</option>
        {columns.map((c: any) => (
          <option key={c.name} value={c.name}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}
function Features({ dataset, selection, onChange }: any) {
  const excluded = [
    selection.sample_column,
    selection.group_column,
    selection.target_column,
  ];
  const columns = dataset.columns.filter(
    (c: any) => c.numeric && !excluded.includes(c.name),
  );
  return (
    <fieldset className="wb-feature-picker">
      <legend>参与计算的数值特征（至少两列）</legend>
      <button
        type="button"
        className="small"
        onClick={() =>
          onChange({ ...selection, features: columns.map((c: any) => c.name) })
        }
      >
        选择全部数值特征
      </button>
      <div>
        {columns.map((c: any) => (
          <label className="checkbox" key={c.name}>
            <input
              type="checkbox"
              checked={selection.features?.includes(c.name) || false}
              onChange={(e) =>
                onChange({
                  ...selection,
                  features: e.target.checked
                    ? [...(selection.features || []), c.name]
                    : (selection.features || []).filter(
                        (x: string) => x !== c.name,
                      ),
                })
              }
            />
            {c.name}
            {c.missing > 0 && <span className="danger">缺失 {c.missing}</span>}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function AlgorithmRunner({ entry, version }: any) {
  const { call, go } = useApi(),
    [dataset, setDataset] = useState<any>(null),
    [selection, setSelection] = useState<any>({ features: [] }),
    [params, setParams] = useState<any>(version.defaults),
    [scale, setScale] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => setParams(version.defaults), [version.id]);
  function selectData(d: any) {
    setDataset(d);
    const sample =
      d.columns.find((c: any) => c.name === "sample_id")?.name ||
      d.columns.find((c: any) => !c.numeric)?.name ||
      "";
    const group = d.columns.find((c: any) => c.name === "group")?.name || "";
    setSelection({
      sample_column: sample,
      group_column: version.task === "classification" ? "" : group,
      target_column: version.task === "classification" ? group : "",
      features: d.columns
        .filter((c: any) => c.numeric && ![sample, group].includes(c.name))
        .map((c: any) => c.name),
    });
  }
  function field(k: string, v: string) {
    const next = { ...selection, [k]: v };
    next.features = next.features.filter(
      (x: string) =>
        ![next.sample_column, next.group_column, next.target_column].includes(
          x,
        ),
    );
    setSelection(next);
  }
  async function run(e: any) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await call("/runs", "POST", {
        kind: "algorithm",
        algorithm_id: entry.id,
        version_id: version.id,
        dataset_id: dataset.id,
        selection,
        params,
        scale,
      });
      go("/runs/" + r.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="wb-runner">
      <DatasetChooser value={dataset} onChange={selectData} />
      {dataset && (
        <form onSubmit={run}>
          <section className="panel">
            <h2>2 · 确认列与参数</h2>
            <div className="wb-fields">
              <ColumnSelect
                label="样本标识列"
                value={selection.sample_column}
                columns={dataset.columns}
                onChange={(v: string) => field("sample_column", v)}
              />
              <ColumnSelect
                label={
                  version.task === "classification"
                    ? "分类标签列（必选）"
                    : "展示分组列（可选）"
                }
                value={selection.target_column || selection.group_column}
                columns={dataset.columns}
                required={version.task === "classification"}
                onChange={(v: string) =>
                  field(
                    version.task === "classification"
                      ? "target_column"
                      : "group_column",
                    v,
                  )
                }
              />
            </div>
            <Features
              dataset={dataset}
              selection={selection}
              onChange={setSelection}
            />
            <Parameters
              schema={version.parameters}
              value={params}
              onChange={setParams}
            />
            {version.task !== "classification" && (
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={scale}
                  onChange={(e) => setScale(e.target.checked)}
                />
                对选定特征做 Z-score 标准化（记录在本次任务）
              </label>
            )}
            <p className="hint">样本标识、标签和分组不参与数值特征计算。</p>
            <ErrorText text={error} />
            <div className="form-footer">
              <span>
                固定算法版本 v{version.number} · {version.upstream_version}
              </span>
              <button
                className="primary"
                disabled={
                  busy ||
                  selection.features.length < 2 ||
                  (version.task === "classification" &&
                    !selection.target_column)
                }
              >
                <Play size={17} />
                {busy ? "提交中…" : "开始运行"}
              </button>
            </div>
          </section>
        </form>
      )}
    </div>
  );
}

function AlgorithmDetail({ id }: any) {
  const { data: entry, error, reload } = useData("/algorithms/" + id),
    { call, go, notify } = useApi(),
    [tab, setTab] = useState("run"),
    [modal, setModal] = useState(""),
    [actionError, setError] = useState(""),
    [busy, setBusy] = useState("");
  async function validate(v: any) {
    setBusy(v.id);
    setError("");
    try {
      const job = await call(
        `/algorithms/${id}/versions/${v.id}/validate`,
        "POST",
        {},
      );
      go("/runs/" + job.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  async function publish(v: any) {
    setBusy(v.id);
    setError("");
    try {
      await call(`/algorithms/${id}/versions/${v.id}/publish`, "POST", {
        expected_active_version_id: entry.active_version_id,
      });
      notify("已切换发布版本；历史运行记录保持原版本");
      reload();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  if (!entry) return error ? <ErrorText text={error} /> : <Busy />;
  const active = entry.active_version;
  return (
    <>
      <Route className="back-link" to="/algorithms">
        <ArrowLeft size={16} />
        返回算法库
      </Route>
      <Head
        eyebrow="ALGORITHM"
        title={entry.display_name}
        description={entry.description}
      >
        <button onClick={() => setModal("edit")} disabled={!!entry.archived_at}>
          <Settings2 size={16} />
          展示设置
        </button>
        <button
          onClick={() => setModal("version")}
          disabled={!active || !!entry.archived_at}
        >
          保存参数新版本
        </button>
        <button
          onClick={() => setModal("import")}
          disabled={!!entry.archived_at}
        >
          <Upload size={16} />
          导入源码新版本
        </button>
        <button
          disabled={busy === "archive"}
          onClick={async () => {
            if (
              !confirm(
                entry.archived_at
                  ? "恢复该算法，并恢复删除前的启用状态？"
                  : "将算法移至回收站？已提交任务继续运行，历史版本和结果保留，可随时恢复。",
              )
            )
              return;
            setBusy("archive");
            setError("");
            try {
              await call(`/algorithms/${id}/archive`, "POST", {
                archived: !entry.archived_at,
                updated_at: entry.updated_at,
              });
              notify(entry.archived_at ? "算法已恢复" : "算法已移至回收站");
              reload();
            } catch (e: any) {
              setError(e.message);
            } finally {
              setBusy("");
            }
          }}
        >
          {entry.archived_at ? "恢复算法" : "删除算法"}
        </button>
      </Head>
      <div className="row wrap wb-meta">
        <span className="tag">{entry.category}</span>
        <code>{entry.name}</code>
        <Badge
          state={active ? "passed" : entry.versions[0]?.validation_status}
        />
        {active && (
          <span>
            当前发布 v{active.number} · 算法 {active.upstream_version}
          </span>
        )}
        {active && !entry.archived_at && (
          <button
            className="small"
            onClick={async () => {
              try {
                await call("/algorithms/" + id, "PATCH", {
                  enabled: !entry.enabled,
                  updated_at: entry.updated_at,
                });
                reload();
              } catch (e: any) {
                setError(e.message);
              }
            }}
          >
            {entry.enabled ? "停用算法" : "启用算法"}
          </button>
        )}
      </div>
      {entry.archived_at && (
        <div className="panel">
          该算法已移至回收站。恢复后可继续编辑和使用，历史运行记录仍可查看。
        </div>
      )}
      <div className="tabs">
        <button
          className={tab === "run" ? "active" : ""}
          onClick={() => setTab("run")}
        >
          选择使用
        </button>
        <button
          className={tab === "versions" ? "active" : ""}
          onClick={() => setTab("versions")}
        >
          版本与验证
        </button>
        <button
          className={tab === "about" ? "active" : ""}
          onClick={() => setTab("about")}
        >
          输入输出说明
        </button>
      </div>
      <ErrorText text={actionError} />
      {tab === "run" &&
        (entry.archived_at ? null : active && entry.enabled ? (
          <AlgorithmRunner key={active.id} entry={entry} version={active} />
        ) : (
          <div className="panel">
            <h2>
              {entry.versions[0]?.validation_status === "catalog_only"
                ? "本版保留算法目录"
                : "尚无可运行版本"}
            </h2>
            <p>
              {entry.versions[0]?.validation_status === "catalog_only"
                ? "该算法暂不支持在线运行。"
                : active
                  ? "启用算法后即可运行。"
                  : "请在“版本与验证”中完成验证并发布。"}
            </p>
            <button onClick={() => setTab("versions")}>查看版本与验证</button>
          </div>
        ))}
      {tab === "versions" && (
        <div className="wb-version-list">
          {entry.versions.map((v: any) => (
            <section className="panel" key={v.id}>
              <div className="row between wrap">
                <h2>
                  v{v.number}{" "}
                  <small className="muted">算法 {v.upstream_version}</small>
                </h2>
                <div className="row wrap">
                  <Badge state={v.validation_status} />
                  {entry.active_version_id === v.id && (
                    <span className="tag green">当前发布</span>
                  )}
                </div>
              </div>
              <p>{v.change_note}</p>
              <p className="hint">
                <DateText value={v.created_at} />
              </p>
              <details>
                <summary>参数与版本信息</summary>
                <pre>
                  {JSON.stringify(
                    {
                      defaults: v.defaults,
                      parameters: v.parameters,
                      entrypoint: v.entrypoint,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <div className="row wrap">
                {v.validation_status !== "catalog_only" && (
                  <button
                    disabled={busy === v.id || !!entry.archived_at}
                    onClick={() => validate(v)}
                  >
                    <FlaskConical size={16} />
                    运行合成示例验证
                  </button>
                )}
                {v.validation_run_id && (
                  <Route className="button" to={"/runs/" + v.validation_run_id}>
                    查看验证记录
                  </Route>
                )}
                {v.validation_status === "passed" &&
                  entry.active_version_id !== v.id && (
                    <button
                      className="primary"
                      disabled={busy === v.id || !!entry.archived_at}
                      onClick={() => publish(v)}
                    >
                      {v.published_at ? "恢复为当前发布" : "发布此版本"}
                    </button>
                  )}
              </div>
            </section>
          ))}
        </div>
      )}
      {tab === "about" && (
        <section className="panel">
          <h2>输入与输出</h2>
          <ul>
            {(
              entry.input_requirements || [
                "样本 × 特征数值矩阵，至少两个特征，样本标识唯一。",
              ]
            ).map((s: string) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          <p>{entry.output_description || "输出分析指标、结果表和图表。"}</p>
          <p>{entry.notes}</p>
          <p className="hint">示例验证通过后，仍需检查真实数据的分析结果。</p>
        </section>
      )}
      {modal === "edit" && (
        <EditAlgorithm
          entry={entry}
          onClose={() => setModal("")}
          onSaved={() => {
            setModal("");
            reload();
          }}
        />
      )}
      {modal === "version" && (
        <NewVersion
          entry={entry}
          onClose={() => setModal("")}
          onSaved={() => {
            setModal("");
            setTab("versions");
            reload();
          }}
        />
      )}
      {modal === "import" && (
        <ImportPackage
          algorithmId={id}
          onClose={() => setModal("")}
          onSaved={() => {
            setModal("");
            setTab("versions");
            reload();
          }}
        />
      )}
    </>
  );
}

function PlotLibrary() {
  const { data, error } = useData("/plots"),
    [selected, setSelected] = useState<any>(null),
    { Modal } = useApi();
  return (
    <>
      <Head eyebrow="PLOT TEMPLATES" title="绘图示例与模板" />
      <ErrorText text={error} />
      {!data && !error ? (
        <Busy />
      ) : (
        <div className="wb-grid">
          {data?.items.map((p: any) => (
            <article className="panel wb-card wb-plot-card" key={p.id}>
              <button
                className="wb-image-button"
                onClick={() => setSelected(p)}
                aria-label={"使用" + p.name}
              >
                <img
                  src={BASE + "/plots/" + p.id + "/preview"}
                  alt={p.name + "合成数据示例"}
                  loading="lazy"
                />
              </button>
              <div className="wb-plot-body">
                <div className="row between">
                  <h2>{p.name}</h2>
                  <span className="tag">合成示例</span>
                </div>
                <p>{p.summary}</p>
                <p className="hint">输入：{p.input}</p>
                <div className="row wrap">
                  <button className="primary" onClick={() => setSelected(p)}>
                    <Play size={16} />
                    选择使用
                  </button>
                  {p.skill_id && (
                    <Route className="button" to={"/skills/" + p.skill_id}>
                      查看 Skill
                    </Route>
                  )}
                  <a className="button" href={BASE + "/examples/" + p.example}>
                    <Download size={15} />
                    示例数据
                  </a>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
      {selected && (
        <Modal
          title={"绘图 · " + selected.name}
          onClose={() => setSelected(null)}
          wide
        >
          <PlotForm recipe={selected} />
        </Modal>
      )}
    </>
  );
}

function PlotForm({ recipe }: any) {
  const { call, go } = useApi(),
    [dataset, setDataset] = useState<any>(null),
    [mapping, setMapping] = useState<any>({}),
    [options, setOptions] = useState<any>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  function selectData(d: any) {
    setDataset(d);
    const names = d.columns.map((c: any) => c.name);
    const initial = { ...recipe.mapping };
    for (const key of ["sample_column", "group_column", "x_column", "y_column"])
      if (!names.includes(initial[key])) initial[key] = "";
    if (initial.features)
      initial.features = d.columns
        .filter((c: any) => c.numeric && !["sample_id"].includes(c.name))
        .map((c: any) => c.name);
    setMapping(initial);
  }
  async function run(e: any) {
    e.preventDefault();
    setBusy(true);
    try {
      const job = await call("/runs", "POST", {
        kind: "plot",
        template_id: recipe.id,
        dataset_id: dataset.id,
        selection: mapping,
        plot_options: options,
      });
      go("/runs/" + job.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const numbers = dataset?.columns.filter((c: any) => c.numeric) || [];
  return (
    <>
      <p>{recipe.summary}</p>
      <DatasetChooser
        value={dataset}
        onChange={selectData}
        example={recipe.example}
      />
      {dataset && (
        <form onSubmit={run}>
          <div className="wb-fields">
            {recipe.id !== "workflow" && (
              <ColumnSelect
                label="样本标识列"
                value={mapping.sample_column}
                columns={dataset.columns}
                onChange={(v: string) =>
                  setMapping({
                    ...mapping,
                    sample_column: v,
                    features: mapping.features?.filter((c: string) => c !== v),
                  })
                }
              />
            )}{" "}
            {["scatter", "importance", "workflow"].includes(recipe.id) && (
              <ColumnSelect
                required
                label={
                  recipe.id === "workflow"
                    ? "步骤列"
                    : recipe.id === "importance"
                      ? "特征名称列"
                      : "横轴数值列"
                }
                value={mapping.x_column}
                columns={recipe.id === "scatter" ? numbers : dataset.columns}
                onChange={(v: string) =>
                  setMapping({ ...mapping, x_column: v })
                }
              />
            )}{" "}
            {["scatter", "box", "importance"].includes(recipe.id) && (
              <ColumnSelect
                required
                label="纵轴数值列"
                value={mapping.y_column}
                columns={numbers}
                onChange={(v: string) =>
                  setMapping({ ...mapping, y_column: v })
                }
              />
            )}{" "}
            {["scatter", "box"].includes(recipe.id) && (
              <ColumnSelect
                required={recipe.id === "box"}
                label="分组列"
                value={mapping.group_column}
                columns={dataset.columns}
                onChange={(v: string) =>
                  setMapping({ ...mapping, group_column: v })
                }
              />
            )}
          </div>
          {["heatmap", "stacked"].includes(recipe.id) && (
            <Features
              dataset={dataset}
              selection={{ ...mapping, features: mapping.features || [] }}
              onChange={setMapping}
            />
          )}
          <h3>图形设置</h3>
          <PlotOptions value={options} onChange={setOptions} />
          <ErrorText text={error} />
          <div className="form-footer">
            <span>输出 PNG、SVG、PDF 和作图数据</span>
            <button className="primary" disabled={busy}>
              <Play size={16} />
              生成图形
            </button>
          </div>
        </form>
      )}
    </>
  );
}

function RunDetail({ id }: any) {
  const { data: run, error } = useData("/runs/" + id, true),
    { call, go } = useApi(),
    [options, setOptions] = useState<any>({}),
    [template, setTemplate] = useState(""),
    [actionError, setError] = useState(""),
    [tableName, setTable] = useState(""),
    [table, setTableData] = useState<any>(null),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (run?.result?.default_template) setTemplate(run.result.default_template);
  }, [run?.id, run?.status]);
  async function preview(name: string) {
    setTable(name);
    try {
      setTableData(await call(`/runs/${id}/files/${name}?download=false`));
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function replot() {
    setBusy(true);
    try {
      const job = await call("/runs/" + id + "/replot", "POST", {
        template_id: template,
        plot_options: options,
      });
      go("/runs/" + job.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (!run) return error ? <ErrorText text={error} /> : <Busy />;
  const pending = ["queued", "running"].includes(run.status),
    completed = run.status === "succeeded",
    hasFigure = run.files.some((f: any) => f.name === "figure.png"),
    csvs = run.files.filter((f: any) => f.name.endsWith(".csv")),
    sources = run.result?.plot_sources || {};
  return (
    <>
      <Route className="back-link" to="/runs">
        <ArrowLeft size={16} />
        返回运行记录
      </Route>
      <Head
        eyebrow={run.validation ? "EXAMPLE VALIDATION" : "RUN RECORD"}
        title={
          run.validation
            ? "算法示例验证"
            : run.request.algorithm_name || "绘图任务"
        }
        description={
          "任务 " +
          run.id.slice(0, 12) +
          " · " +
          new Date(run.created_at).toLocaleString("zh-CN")
        }
      >
        <Badge state={run.status} />
        {completed && (
          <a className="button primary" href={BASE + "/runs/" + id + "/export"}>
            <Download size={16} />
            下载完整结果
          </a>
        )}
        {pending && (
          <button
            onClick={async () => {
              await call("/runs/" + id + "/cancel", "POST", {});
              go("/runs");
            }}
          >
            停止任务
          </button>
        )}
      </Head>
      <ErrorText text={actionError || run.error} />
      {pending && (
        <section className="panel">
          <div className="row">
            <Loader2 className="spin" />
            正在运行，页面会自动更新。
          </div>
          <p className="hint">
            同时最多运行两个任务；超过时限会停止。离开页面不会取消任务。
          </p>
        </section>
      )}
      {run.algorithm_id && (
        <p>
          <Route to={"/algorithms/" + run.algorithm_id}>
            查看对应算法与固定版本
          </Route>
        </p>
      )}
      {run.parent_run_id && (
        <p>
          基于已有结果重绘：
          <Route to={"/runs/" + run.parent_run_id}>查看原算法运行</Route>
        </p>
      )}
      {completed && (
        <>
          <div className="wb-result-grid">
            <section className="panel">
              <h2>结果预览</h2>
              {hasFigure ? (
                <img
                  className="wb-result-image"
                  src={
                    BASE + "/runs/" + id + "/files/figure.png?download=false"
                  }
                  alt="本次任务绘图结果"
                />
              ) : (
                <p>本次未生成默认图形，可下载结果表后选择绘图。</p>
              )}
              <div className="row wrap">
                {["png", "svg", "pdf"].map(
                  (ext) =>
                    run.files.some((f: any) => f.name === "figure." + ext) && (
                      <a
                        key={ext}
                        className="button"
                        href={BASE + "/runs/" + id + "/files/figure." + ext}
                      >
                        <Download size={15} />
                        {ext.toUpperCase()}
                      </a>
                    ),
                )}
              </div>
            </section>
            <section className="panel">
              <h2>指标与说明</h2>
              {run.result?.metrics && (
                <dl className="wb-metrics">
                  {Object.entries(run.result.metrics).map(([k, v]: any) => (
                    <React.Fragment key={k}>
                      <dt>{k}</dt>
                      <dd>
                        {typeof v === "number"
                          ? Number(v.toPrecision(6))
                          : String(v)}
                      </dd>
                    </React.Fragment>
                  ))}
                </dl>
              )}
              <ul className="wb-notes">
                {run.result?.warnings?.map((s: string, i: number) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          </div>
          {Object.keys(sources).length > 0 && (
            <section className="panel">
              <h2>基于结果重绘</h2>
              <p className="hint">
                复用本次结果表，不重新运行算法。重绘会生成独立记录。
              </p>
              <label>
                绘图模板
                <select
                  value={template}
                  onChange={(e) => setTemplate(e.target.value)}
                >
                  {Object.keys(sources).map((k) => (
                    <option key={k} value={k}>
                      {{
                        scatter: "分组散点图",
                        heatmap: "数值矩阵热图",
                        importance: "特征重要性图",
                      }[k] || k}
                    </option>
                  ))}
                </select>
              </label>
              <PlotOptions value={options} onChange={setOptions} />
              <button
                className="primary"
                disabled={busy || !template}
                onClick={replot}
              >
                <Image size={16} />
                保存重绘结果
              </button>
            </section>
          )}
          <section className="panel">
            <h2>结果表与文件</h2>
            <div className="row wrap">
              {csvs.map((f: any) => (
                <button
                  className={tableName === f.name ? "active" : ""}
                  key={f.name}
                  onClick={() => preview(f.name)}
                >
                  {f.name}
                </button>
              ))}
            </div>
            {table && (
              <>
                <p className="hint">预览前 20 行、30 列；完整数据请下载。</p>
                <Table {...table} />
              </>
            )}
            <div className="wb-file-list">
              {run.files.map((f: any) => (
                <a
                  key={f.name}
                  href={BASE + "/runs/" + id + "/files/" + f.name}
                >
                  <Download size={14} />
                  {f.name}
                  <small>{Math.round(f.size / 1024)} KB</small>
                </a>
              ))}
            </div>
          </section>
        </>
      )}
      <details className="panel">
        <summary>运行参数与日志</summary>
        <pre>{JSON.stringify(run.request, null, 2)}</pre>
        <pre>{run.log || "暂无日志。"}</pre>
      </details>
    </>
  );
}

function RunHistory() {
  const { data, error, reload } = useData("/runs");
  return (
    <>
      <Head eyebrow="RUN HISTORY" title="运行记录">
        <button onClick={reload}>
          <RefreshCw size={16} />
          刷新记录
        </button>
      </Head>
      <ErrorText text={error} />
      {!data && !error ? (
        <Busy />
      ) : (
        <div className="wb-history">
          {data?.items.length ? (
            data.items.map((r: any) => (
              <Route
                className="panel wb-history-row"
                key={r.id}
                to={"/runs/" + r.id}
              >
                <div>
                  <strong>
                    {r.validation
                      ? "示例验证 · "
                      : r.kind === "plot"
                        ? "绘图 · "
                        : ""}
                    {r.request.algorithm_name ||
                      r.request.template_id ||
                      r.kind}
                  </strong>
                  <p className="muted">
                    {r.request.dataset_name || r.request.dataset || "已有结果"}{" "}
                    · <DateText value={r.created_at} />
                  </p>
                </div>
                <div className="row">
                  <Badge state={r.status} />
                  <ArrowRight size={17} />
                </div>
              </Route>
            ))
          ) : (
            <div className="panel">
              还没有运行记录。选择一个算法或绘图模板开始。
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function Workbench({ path, api, go, notify, Modal }: any) {
  const parts = path.split("/").filter(Boolean);
  let page =
    parts[0] === "plots" ? (
      <PlotLibrary />
    ) : parts[0] === "runs" ? (
      parts[1] ? (
        <RunDetail key={parts[1]} id={parts[1]} />
      ) : (
        <RunHistory />
      )
    ) : parts[1] ? (
      <AlgorithmDetail key={parts[1]} id={parts[1]} />
    ) : (
      <Algorithms />
    );
  return (
    <Context.Provider value={{ api, go, notify, Modal }}>
      <div className="wb">{page}</div>
    </Context.Provider>
  );
}
