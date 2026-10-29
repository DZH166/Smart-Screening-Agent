import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  post,
  ApiError,
  running,
  versionName,
  loadLocal,
  saveLocal,
  type Asset,
  type Config,
  type Design,
  type Job,
  type Selection,
  type Template,
  type User,
  type Version,
} from "./api";
import Admin from "./Admin";

type IconName =
  | "spark"
  | "upload"
  | "grid"
  | "back"
  | "download"
  | "plus"
  | "close"
  | "check"
  | "folder"
  | "arrow"
  | "logout"
  | "settings";
export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    spark: (
      <>
        <path d="m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3Z" />
        <path d="m20 2 .7 2.3L23 5l-2.3.7L20 8l-.7-2.3L17 5l2.3-.7Z" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    back: (
      <>
        <path d="m8 4-5 5 5 5M3 9h10a7 7 0 0 1 0 14" />
      </>
    ),
    download: (
      <>
        <path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4" />
      </>
    ),
    plus: <path d="M12 4v16M4 12h16" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    check: <path d="m4 12 5 5L20 6" />,
    folder: <path d="M3 6h7l2 3h9v11H3ZM3 6V4h7l2 2" />,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    logout: (
      <>
        <path d="M9 4H3v16h6m5-13 5 5-5 5M8 12h11" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="m12 2 2 3 4-1 1 4 3 2-2 3 1 4-4 1-2 3-3-2-4 1-1-4-3-2 2-3-1-4 4-1Z" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const scope = ref.current?.getRootNode() as Document | ShadowRoot;
    const old = scope?.activeElement as HTMLElement;
    const first = ref.current?.querySelector<HTMLElement>(
      "button,input,select,textarea",
    );
    first?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const focusables = ref.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]",
        );
        if (!focusables?.length) return;
        const firstEl = focusables[0],
          last = focusables[focusables.length - 1];
        if (e.shiftKey && scope?.activeElement === firstEl) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && scope?.activeElement === last) {
          e.preventDefault();
          firstEl.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", key);
      document.body.style.overflow = overflow;
      old?.focus();
    };
  }, []);
  return (
    <div
      className="modal-scrim"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        className={`modal ${wide ? "modal-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">RIBBON STUDIO</span>
            <h2>{title}</h2>
          </div>
          <button
            className="icon-button"
            aria-label="关闭弹窗"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
function Brand() {
  return (
    <div className="brand">
      <span className="brand-icon">
        <svg width="26" height="30" viewBox="0 0 26 30" fill="none">
          <path d="M5 3h16v12L13 9 5 15V3Z" fill="currentColor" />
          <path
            d="M5 19v8l8-5 8 5V16l-8-5-8 5"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      </span>
      <div>
        <strong>丝带设计助手</strong>
        <small>RIBBON DESIGN STUDIO</small>
      </div>
      <span className="version-tag">V1</span>
    </div>
  );
}
function message(e: unknown) {
  return e instanceof Error ? e.message : "发生未知错误，请重试。";
}
const emptySelection: Selection = {
  asset_ids: [],
  background_id: "",
  template_id: "",
};
function recommendedSelection(
  assets: Asset[],
  templates: Template[],
): Selection {
  return {
    asset_ids: ["demo-flower", "demo-star", "demo-ring"].filter((id) =>
      assets.some((a) => a.id === id),
    ),
    background_id: assets.find((a) => a.id === "demo-bg-sage")?.id || "",
    template_id:
      templates.find((t) => t.mode === "stagger" && t.enabled)?.id ||
      templates.find((t) => t.enabled)?.id ||
      "",
  };
}
type Pending = {
  path: string;
  body: Record<string, unknown>;
  kind: "background" | "design";
  designId?: string;
};
const phaseNames: Record<string, string> = {
  queued: "等待处理",
  planning: "正在理解修改要求",
  rendering: "正在生成设计",
  editing: "正在编辑图像",
  saving: "正在保存结果",
  completed: "已保存",
  generating: "正在生成底图",
  validating: "正在检查结果",
  reconciling: "正在恢复任务",
  QUEUED: "等待处理",
  RUNNING: "正在处理",
  RECONCILING: "正在恢复任务",
  SUCCEEDED: "已保存",
  FAILED: "处理未完成",
};

type WorkspaceProps = { active: boolean; view: "ribbon" | "ribbon-admin" };
export default function App({ active, view }: WorkspaceProps) {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setAuthLoading(true);
    api<User>("/auth/me")
      .then((value) => { if (!cancelled) setUser(value); })
      .catch((error) => { if (!cancelled) { setUser(null); setAuthError(message(error)); } })
      .finally(() => { if (!cancelled) setAuthLoading(false); });
    return () => { cancelled = true; };
  }, [active, view]);
  return <>
    {authLoading && <div className="page-loader"><span className="spinner" /><span>正在连接丝带设计…</span></div>}
    {!authLoading && !user && <div className="notice error" role="alert"><strong>丝带设计暂时无法打开</strong><p>{authError || "登录已失效，请重新打开网站后继续。"}</p><button type="button" onClick={() => location.reload()}>重新载入</button></div>}
    {user && <div hidden={authLoading}><Workspace key={user.id} user={user} active={active && !authLoading} view={view} onLogout={() => { setUser(null); setAuthError("登录已失效，请重新打开网站后继续。"); }} /></div>}
  </>;
}

function Workspace({ user, onLogout, active, view }: WorkspaceProps & { user: User; onLogout: () => void }) {
  const prefix = `ribbon:${user.id}:`;
  const [config, setConfig] = useState<Config | null>(null),
    [assets, setAssets] = useState<Asset[]>([]),
    [templates, setTemplates] = useState<Template[]>([]),
    [designs, setDesigns] = useState<Design[]>([]);
  const [design, setDesign] = useState<Design | null>(null),
    [selection, setSelection] = useState<Selection>(emptySelection),
    [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  // A ribbon is a very wide strip: "detail" shows it at a readable height and
  // scrolls sideways, "fit" shows the whole length at once.
  const [previewZoom, setPreviewZoom] = useState<"detail" | "fit">("detail");
  const [prompt, setPrompt] = useState(""),
    [job, setJob] = useState<Job | null>(null),
    [backgroundJob, setBackgroundJob] = useState<Job | null>(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState<{
      text: string;
      type: "error" | "success" | "info";
    } | null>(null),
    [modal, setModal] = useState<
      "pattern" | "background" | "designs" | "admin" | null
    >(null),
    [pending, setPending] = useState<Pending | null>(() =>
      loadLocal(prefix + "pending", null),
    );
  const [search, setSearch] = useState(""),
    [uploading, setUploading] = useState(false),
    [sharedUpload, setSharedUpload] = useState(false);
  const gate = useRef(false),
    uploadRef = useRef<HTMLInputElement>(null),
    lastVersion = useRef<string | null>(null),
    designRef = useRef<Design | null>(null);
  const isAdmin = user.role === "admin",
    current = design?.versions?.find((v) => v.id === design.current_version_id),
    selected =
      design?.versions?.find((v) => v.id === selectedVersionId) || current;
  const remaining = Math.max(0, 2 - (design?.successful_refinement_count || 0));
  const processing = !!design?.active_job_id || running(job),
    backgroundProcessing = running(backgroundJob),
    locked = busy || processing || !!pending || uploading;
  const isHistory = !!selected && selected.id !== design?.current_version_id;
  const shownProfile = selected?.snapshot?.output_profile;
  const sizeLabel =
    shownProfile?.width && shownProfile?.height && shownProfile?.dpi
      ? `${shownProfile.width}×${shownProfile.height}px · ${shownProfile.dpi} DPI · ` +
        `${((shownProfile.width / shownProfile.dpi) * 2.54).toFixed(1)}×` +
        `${((shownProfile.height / shownProfile.dpi) * 2.54).toFixed(1)} cm`
      : "";
  const ready =
    selection.asset_ids.length > 0 &&
    !!selection.background_id &&
    !!selection.template_id;
  const changed =
    !!current &&
    (JSON.stringify(current.snapshot.asset_refs) !==
      JSON.stringify(selection.asset_ids) ||
      current.snapshot.background_ref !== selection.background_id ||
      current.snapshot.template_id !== selection.template_id);
  const selectedPatterns = selection.asset_ids
    .map((id) => assets.find((a) => a.id === id))
    .filter(Boolean) as Asset[];
  const background = assets.find((a) => a.id === selection.background_id),
    template = templates.find((t) => t.id === selection.template_id);
  const testMode = config?.provider === "test";

  function updateSelection(value: Selection) {
    setSelection(value);
    saveLocal(prefix + "selection", {
      design_id: designRef.current?.id || null,
      base_version_id: designRef.current?.current_version_id || null,
      value,
    });
  }
  function applyDesign(d: Design, force = false) {
    const changedVersion = lastVersion.current !== d.current_version_id;
    designRef.current = d;
    setDesign(d);
    saveLocal(prefix + "design", d.id);
    setDesigns((prev) => [d, ...prev.filter((p) => p.id !== d.id)]);
    if (force || changedVersion) {
      const v = d.versions?.find((x) => x.id === d.current_version_id);
      const saved = loadLocal<{
        design_id: string;
        base_version_id: string | null;
        value: Selection;
      } | null>(prefix + "selection", null);
      const next =
        force &&
        saved?.design_id === d.id &&
        saved.base_version_id === d.current_version_id
          ? saved.value
          : v
            ? {
                asset_ids: v.snapshot.asset_refs,
                background_id: v.snapshot.background_ref,
                template_id: v.snapshot.template_id,
              }
            : emptySelection;
      setSelection(next);
      setSelectedVersionId(d.current_version_id);
      lastVersion.current = d.current_version_id;
      if (changedVersion) setPrompt("");
    }
    if (d.active_job) setJob(d.active_job);
  }
  async function loadCatalog() {
    const [a, t, c] = await Promise.all([
      api<Asset[]>("/assets"),
      api<Template[]>("/templates"),
      api<Config>("/config"),
    ]);
    setAssets(a);
    setTemplates(t);
    setConfig(c);
  }
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const [a, t, c, list] = await Promise.all([
          api<Asset[]>("/assets"),
          api<Template[]>("/templates"),
          api<Config>("/config"),
          api<Design[]>("/designs"),
        ]);
        if (cancelled) return;
        setAssets(a);
        setTemplates(t);
        setConfig(c);
        setDesigns(list);
        const savedId = loadLocal<string | null>(prefix + "design", null);
        const id = list.find((x) => x.id === savedId)?.id || list[0]?.id;
        if (id) {
          const d = await api<Design>(`/designs/${id}`);
          if (!cancelled) {
            applyDesign(d, true);
            if (d.active_job_id)
              setNotice({
                text: "已恢复作品，正在同步后台任务。离开页面不会中断处理。",
                type: "info",
              });
          }
        } else {
          const saved = loadLocal<{ value: Selection } | null>(
            prefix + "selection",
            null,
          );
          setSelection(saved?.value || recommendedSelection(a, t));
        }
        const bgId = loadLocal<string | null>(prefix + "backgroundJob", null);
        if (bgId) {
          const bg = await api<Job>(`/jobs/${bgId}`);
          if (!cancelled) setBackgroundJob(bg);
        }
      } catch (e) {
        if (!cancelled) {
          setNotice({ text: message(e), type: "error" });
          if (e instanceof ApiError && e.status === 401) onLogout();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void init();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!active || (!design?.id && !backgroundJob?.id)) return;
    let cancelled = false,
      inflight = false;
    const tick = async () => {
      if (inflight || document.hidden) return;
      inflight = true;
      try {
        if (design?.id) {
          const d = await api<Design>(`/designs/${design.id}`);
          if (cancelled) return;
          const previous = designRef.current;
          applyDesign(d);
          const id = d.active_job_id || previous?.active_job_id || job?.id;
          if (id) {
            const updated = await api<Job>(`/jobs/${id}`);
            if (cancelled) return;
            setJob(updated);
            if (updated.status === "FAILED" && job?.status !== "FAILED")
              setNotice({
                text:
                  updated.error ||
                  "此次处理未完成，已保留原结果，不扣精修次数。",
                type: "error",
              });
          }
        }
        if (backgroundJob && running(backgroundJob)) {
          const updated = await api<Job>(`/jobs/${backgroundJob.id}`);
          if (cancelled) return;
          setBackgroundJob(updated);
          if (updated.status === "SUCCEEDED" && updated.result_asset_id) {
            const a = await api<Asset[]>("/assets");
            if (cancelled) return;
            setAssets(a);
            const target = loadLocal<{ design_id: string | null } | null>(
              prefix + "backgroundTarget",
              null,
            );
            if (!target || target.design_id === (designRef.current?.id || null))
              setSelection((prev) => {
                const value = {
                  ...prev,
                  background_id: updated.result_asset_id!,
                };
                saveLocal(prefix + "selection", {
                  design_id: designRef.current?.id || null,
                  base_version_id:
                    designRef.current?.current_version_id || null,
                  value,
                });
                return value;
              });
            saveLocal(prefix + "backgroundJob", null);
            setNotice({
              text: testMode
                ? "测试底图已生成并选中。"
                : "AI 底图已生成并选中。",
              type: "success",
            });
          } else if (updated.status === "FAILED") {
            saveLocal(prefix + "backgroundJob", null);
            setNotice({
              text: updated.error || "底图未能生成，请重试。",
              type: "error",
            });
          }
        }
        setOffline(false);
      } catch (e) {
        if (!cancelled) {
          setOffline(true);
          if (e instanceof ApiError && e.status === 401) onLogout();
        }
      } finally {
        inflight = false;
      }
    };
    // Refresh on workspace re-entry and tab focus. Finished work does not poll.
    void tick();
    const timer = processing || backgroundProcessing
      ? window.setInterval(tick, 1200) : undefined;
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("focus", tick);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("focus", tick);
    };
  }, [
    active,
    design?.id,
    design?.active_job_id,
    backgroundJob?.id,
    backgroundJob?.status,
    job?.id,
    job?.status,
  ]);

  // Refresh derived assets after a content edit; the version snapshot owns the selection.
  useEffect(() => {
    if (!design?.current_version_id) return;
    void api<Asset[]>("/assets")
      .then(setAssets)
      .catch(() => setOffline(true));
  }, [design?.current_version_id]);

  // A completed background job can be recovered even after the browser was closed.
  useEffect(() => {
    if (backgroundJob?.status !== "SUCCEEDED" || !backgroundJob.result_asset_id)
      return;
    const stored = loadLocal<string | null>(prefix + "backgroundJob", null);
    if (stored !== backgroundJob.id) return;
    void api<Asset[]>("/assets")
      .then((a) => {
        setAssets(a);
        const target = loadLocal<{ design_id: string | null } | null>(
          prefix + "backgroundTarget",
          null,
        );
        if (!target || target.design_id === (designRef.current?.id || null))
          setSelection((prev) => {
            const value = {
              ...prev,
              background_id: backgroundJob.result_asset_id!,
            };
            saveLocal(prefix + "selection", {
              design_id: designRef.current?.id || null,
              base_version_id: designRef.current?.current_version_id || null,
              value,
            });
            return value;
          });
        saveLocal(prefix + "backgroundJob", null);
        setNotice({ text: "已恢复上次完成的底图。", type: "success" });
      })
      .catch(() => setOffline(true));
  }, [backgroundJob?.id, backgroundJob?.status]);

  async function executePending(operation: Pending) {
    setPending(operation);
    saveLocal(prefix + "pending", operation);
    try {
      const result = await post<Job>(operation.path, operation.body);
      setPending(null);
      saveLocal(prefix + "pending", null);
      setNotice(null);
      if (operation.kind === "background") {
        saveLocal(prefix + "backgroundTarget", {
          design_id: operation.designId || null,
        });
        setBackgroundJob(result);
        saveLocal(prefix + "backgroundJob", result.id);
      } else {
        setJob(result);
        if (operation.designId) {
          try {
            const d = await api<Design>(`/designs/${operation.designId}`);
            applyDesign(d);
          } catch {
            setOffline(true);
            setNotice({
              text: "任务已接受，正在等待连接恢复以同步结果。",
              type: "info",
            });
          }
        }
      }
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status >= 400 &&
        e.status < 500 &&
        e.status !== 408
      ) {
        setPending(null);
        saveLocal(prefix + "pending", null);
      }
      setNotice({
        text:
          e instanceof ApiError &&
          e.status >= 400 &&
          e.status < 500 &&
          e.status !== 408
            ? message(e)
            : "连接中断，提交结果尚未确认。请点击“恢复提交”，将使用原请求安全查询或继续。",
        type: "error",
      });
    }
  }
  async function action(fn: () => Promise<void>) {
    if (gate.current) return;
    gate.current = true;
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setNotice({ text: message(e), type: "error" });
    } finally {
      gate.current = false;
      setBusy(false);
    }
  }
  async function generate() {
    if (locked || !ready) return;
    await action(async () => {
      let d = design;
      if (!d) {
        d = await post<Design>("/designs", {
          name: `丝带设计 ${new Date().toLocaleDateString("zh-CN")}`,
        });
        applyDesign(d);
      }
      await executePending({
        path: `/designs/${d.id}/generate`,
        body: { idempotency_key: crypto.randomUUID(), ...selection },
        kind: "design",
        designId: d.id,
      });
    });
  }
  async function refine() {
    if (
      locked ||
      !current ||
      remaining === 0 ||
      isHistory ||
      !ready ||
      (!prompt.trim() && !changed)
    )
      return;
    await action(() =>
      executePending({
        path: `/designs/${design!.id}/refinements`,
        body: {
          idempotency_key: crypto.randomUUID(),
          base_version_id: current.id,
          prompt: prompt.trim() || (changed ? "应用所选配置" : ""),
          ...(changed ? { selection } : {}),
        },
        kind: "design",
        designId: design!.id,
      }),
    );
  }
  async function rollback() {
    if (locked || !current?.parent_version_id) return;
    await action(async () => {
      const d = await post<Design>(`/designs/${design!.id}/rollback`, {
        expected_version_id: current.id,
      });
      applyDesign(d);
      setJob(null);
      setNotice({
        text: "已回退到当前版本的父版本。累计精修次数保持不变。",
        type: "success",
      });
    });
  }
  async function newDesign() {
    if (busy || pending || backgroundProcessing || uploading) return;
    await action(async () => {
      const d = await post<Design>("/designs", {
        name: `丝带设计 ${designs.length + 1}`,
      });
      lastVersion.current = null;
      applyDesign(d, true);
      updateSelection(recommendedSelection(assets, templates));
      setPrompt("");
      setJob(null);
      setNotice(null);
      setModal(null);
    });
  }
  async function switchDesign(id: string) {
    if (busy || pending || backgroundProcessing || uploading) return;
    await action(async () => {
      const d = await api<Design>(`/designs/${id}`);
      applyDesign(d, true);
      setJob(d.active_job || null);
      setPrompt("");
      setNotice(null);
      setModal(null);
    });
  }
  async function generateBackground() {
    if (locked || backgroundProcessing) return;
    await action(() =>
      executePending({
        path: "/background-jobs",
        body: { idempotency_key: crypto.randomUUID() },
        kind: "background",
        designId: design?.id,
      }),
    );
  }
  async function upload(
    files: FileList | null,
    kind: "pattern" | "background",
  ) {
    if (!files?.length) return;
    setUploading(true);
    setNotice(null);
    const added: Asset[] = [];
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        form.append("kind", kind);
        form.append("name", file.name.replace(/\.[^.]+$/, ""));
        form.append("shared", String(isAdmin && sharedUpload));
        added.push(await api<Asset>("/assets", { method: "POST", body: form }));
      }
      const all = await api<Asset[]>("/assets");
      setAssets(all);
      if (kind === "pattern")
        updateSelection({
          ...selection,
          asset_ids: [
            ...new Set([...selection.asset_ids, ...added.map((a) => a.id)]),
          ].slice(0, 12),
        });
      else updateSelection({ ...selection, background_id: added.at(-1)!.id });
      setNotice({
        text: `已上传 ${added.length} 个${kind === "pattern" ? "图案" : "底图"}。`,
        type: "success",
      });
    } catch (e) {
      if (added.length) {
        setAssets((prev) => [...prev, ...added]);
        setNotice({
          text: `已上传 ${added.length} 个，其余未完成：${message(e)}`,
          type: "error",
        });
      } else setNotice({ text: message(e), type: "error" });
    } finally {
      setUploading(false);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  }
  function togglePattern(id: string) {
    if (locked) return;
    if (!selection.asset_ids.includes(id) && selection.asset_ids.length >= 12) {
      setNotice({ text: "每份设计最多选择 12 个图案。", type: "info" });
      return;
    }
    updateSelection({
      ...selection,
      asset_ids: selection.asset_ids.includes(id)
        ? selection.asset_ids.filter((x) => x !== id)
        : [...selection.asset_ids, id],
    });
  }
  useEffect(() => {
    if (!active) { setModal(null); return; }
    if (view === "ribbon-admin") {
      if (isAdmin) setModal("admin");
      else setNotice({ text: "排版与规格维护仅供管理员使用。", type: "error" });
    }
  }, [active, view, isAdmin]);
  async function hideAsset(asset: Asset) {
    await action(async () => {
      await api(`/assets/${asset.id}`, { method: "DELETE" });
      setAssets((prev) => prev.filter((a) => a.id !== asset.id));
      updateSelection({
        ...selection,
        asset_ids: selection.asset_ids.filter((id) => id !== asset.id),
        background_id:
          selection.background_id === asset.id ? "" : selection.background_id,
      });
    });
  }
  const status = processing
    ? phaseNames[job?.phase || ""] ||
      job?.phase ||
      phaseNames[job?.status || ""] ||
      "正在处理"
    : current
      ? remaining
        ? "可继续精修"
        : "精修已用完"
      : ready
        ? "可以生成首稿"
        : "等待选择素材";
  const library = assets.filter(
    (a) =>
      a.kind === modal &&
      a.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
  );

  return (
    <div className="app-shell">
      <header className="topbar">
        <Brand />
        <div className="header-actions">
          <button className="text-button" onClick={() => setModal("designs")}>
            <Icon name="folder" />
            我的作品<span className="count">{designs.length}</span>
          </button>
          {isAdmin && (
            <button className="text-button" onClick={() => setModal("admin")}>
              <Icon name="settings" />
              排版与规格
            </button>
          )}
        </div>
      </header>
      <main>
        <div className="workspace-title">
          <div>
            <h1>选择图案，开始设计</h1>
            <p>选择图案、排版和底图，生成首稿后可继续精修。</p>
          </div>
          <button
            className="secondary"
            disabled={busy || !!pending || backgroundProcessing || uploading}
            onClick={() => void newDesign()}
          >
            <Icon name="plus" />
            新建作品
          </button>
        </div>
        <div className="environment-strip">
          <div>
            <span className={`status-dot ${testMode ? "amber" : ""}`} />
            <strong>
              {testMode
                ? "测试模型 · 演示模式"
                : config?.ai_ready
                  ? "真实 AI 已配置"
                  : "AI 尚未配置"}
            </strong>
            <span>
              {testMode
                ? "底图和内容编辑使用明确的测试替身，非真实 AI 效果。"
                : config?.ai_ready
                  ? "模型结果仍需人工检查。"
                  : "请由内部人员配置模型服务。"}
            </span>
          </div>
          <span className="outline-pill">
            {config?.output_profile?.is_demo
              ? "演示输出 · 未经业务验收"
              : "内部输出配置"}
          </span>
        </div>
        {notice && (
          <div
            className={`notice ${notice.type}`}
            role={notice.type === "error" ? "alert" : "status"}
          >
            <span>{notice.text}</span>
            <button
              aria-label="关闭提示"
              className="icon-button"
              onClick={() => setNotice(null)}
            >
              <Icon name="close" size={15} />
            </button>
          </div>
        )}
        {offline && (
          <div className="notice error" role="status">
            连接暂时中断，正在重连。后台任务和已保存版本不会因此重置。
          </div>
        )}
        {pending && (
          <div className="notice info">
            <span>有一项提交尚未确认；恢复使用原幂等键，不会重复扣次。</span>
            <button
              className="secondary small"
              disabled={busy}
              onClick={() => void action(() => executePending(pending))}
            >
              恢复提交
            </button>
          </div>
        )}
        {loading ? (
          <div className="page-loader in-page">
            <span className="spinner" />
            正在恢复作品和素材…
          </div>
        ) : (
          <div className="workspace-grid">
            <aside className="panel source-panel">
              <div className="panel-heading">
                <div>
                  <span className="step-label">01 / COMPOSE</span>
                  <h2>素材与排版</h2>
                </div>
                <Icon name="grid" />
              </div>
              <section className="source-section">
                <div className="section-label">
                  <h3>图案</h3>
                  <span>已选 {selection.asset_ids.length} 个</span>
                </div>
                <div className="two-actions">
                  <button
                    className="secondary"
                    disabled={locked || uploading}
                    onClick={() => {
                      setSharedUpload(false);
                      uploadRef.current?.click();
                    }}
                  >
                    <Icon name="upload" size={16} />
                    {uploading ? "上传中…" : "上传图案"}
                  </button>
                  <button
                    className="secondary"
                    disabled={locked}
                    onClick={() => {
                      setSearch("");
                      setModal("pattern");
                    }}
                  >
                    <Icon name="folder" size={16} />
                    素材库
                  </button>
                </div>
                <input
                  ref={uploadRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  hidden
                  onChange={(e) => void upload(e.target.files, "pattern")}
                />
                {selectedPatterns.length ? (
                  <div className="selected-patterns">
                    {selectedPatterns.map((a) => (
                      <div className="pattern-tile" key={a.id}>
                        <div className="checker">
                          <img src={a.url} alt={a.name} />
                          <button
                            className="remove-asset"
                            disabled={locked}
                            aria-label={`移除${a.name}`}
                            onClick={() => togglePattern(a.id)}
                          >
                            ×
                          </button>
                        </div>
                        <span title={a.name}>{a.name}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <button
                    className="empty-patterns"
                    disabled={locked}
                    onClick={() => {
                      setSearch("");
                      setModal("pattern");
                    }}
                  >
                    <Icon name="plus" />
                    <span>从素材库开始，或上传已有图案</span>
                    <small>支持多个透明 PNG 图案</small>
                  </button>
                )}
              </section>
              <section className="source-section">
                <div className="section-label">
                  <h3>排版模式</h3>
                  <span>选择一种排列方式</span>
                </div>
                <div className="template-grid">
                  {templates
                    .filter((t) => t.enabled || t.id === selection.template_id)
                    .map((t) => (
                      <button
                        key={t.id}
                        className={`template-card ${selection.template_id === t.id ? "selected" : ""}`}
                        disabled={locked}
                        aria-pressed={selection.template_id === t.id}
                        onClick={() =>
                          updateSelection({ ...selection, template_id: t.id })
                        }
                      >
                        <img src={t.thumbnail_url} alt={`${t.name}样式图`} />
                        <span>
                          {t.name}
                          {selection.template_id === t.id && (
                            <Icon name="check" size={14} />
                          )}
                        </span>
                      </button>
                    ))}
                </div>
              </section>
              <section className="source-section background-section">
                <div className="section-label">
                  <h3>底图</h3>
                  {background?.is_demo && (
                    <span className="tiny-pill">演示素材</span>
                  )}
                </div>
                <div className="two-actions">
                  <button
                    className="secondary"
                    disabled={locked}
                    onClick={() => {
                      setSearch("");
                      setModal("background");
                    }}
                  >
                    <Icon name="folder" size={16} />
                    底图库
                  </button>
                  <button
                    className="secondary"
                    disabled={locked || backgroundProcessing}
                    onClick={() => void generateBackground()}
                  >
                    {backgroundProcessing ? (
                      <span className="spinner tiny" />
                    ) : (
                      <Icon name="spark" size={16} />
                    )}
                    AI 随机
                  </button>
                </div>
                {background ? (
                  <div className="background-selected">
                    <img src={background.url} alt="选中的底图" />
                    <div>
                      <strong>{background.name}</strong>
                      <small>
                        {background.source === "upload" ? "已上传" : "已选择"}
                      </small>
                    </div>
                    <Icon name="check" size={16} />
                  </div>
                ) : (
                  <div className="empty-background">
                    选择底图，为图案定下基调
                  </div>
                )}
                {backgroundProcessing && (
                  <p className="microcopy">
                    {testMode ? "正在生成测试底图…" : "AI 正在生成底图…"}{" "}
                    可离开后恢复。
                  </p>
                )}
              </section>
              {current && changed && (
                <div className="selection-warning">
                  素材或排版已更改。点击右侧“开始精修”应用，会计入本作品精修次数。
                </div>
              )}
            </aside>
            <section className="center-column">
              <div className="panel preview-panel">
                <div className="panel-heading">
                  <div>
                    <span className="step-label">02 / PREVIEW</span>
                    <h2>{design?.name || "设计预览"}</h2>
                  </div>
                  <span className={`state-pill ${processing ? "working" : ""}`}>
                    <span className="status-dot" />
                    {status}
                  </span>
                </div>
                <div className={`preview-stage ${!selected ? "is-empty" : "is-filled"}`}>
                  <div className="stage-topline">
                    <span>
                      {selected
                        ? `V${selected.sequence} · ${versionName(selected)}`
                        : "你的设计画布"}
                    </span>
                    {selected && (
                      <span>
                        {selected.id === design?.current_version_id
                          ? "当前版本"
                          : "历史版本"}
                      </span>
                    )}
                  </div>
                  {selected ? (
                    <>
                      <div className={`ribbon-display ${previewZoom}`}>
                        <img
                          src={selected.preview_url}
                          alt={`${versionName(selected)}的设计预览`}
                        />
                      </div>
                      <div className="ribbon-tools">
                        <div className="ribbon-zoom" role="group" aria-label="预览缩放">
                          <button
                            type="button"
                            className={previewZoom === "detail" ? "is-active" : ""}
                            aria-pressed={previewZoom === "detail"}
                            onClick={() => setPreviewZoom("detail")}
                          >
                            细节
                          </button>
                          <button
                            type="button"
                            className={previewZoom === "fit" ? "is-active" : ""}
                            aria-pressed={previewZoom === "fit"}
                            onClick={() => setPreviewZoom("fit")}
                          >
                            整条
                          </button>
                        </div>
                        <span className="ribbon-metrics">{sizeLabel}</span>
                        <span className="ribbon-hint">
                          {previewZoom === "detail" ? "左右拖动查看整条" : ""}
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className="empty-canvas">
                      <div className="empty-symbol">
                        <Icon name="spark" size={29} />
                      </div>
                      <h3>好设计，从一个图案开始</h3>
                      <p>
                        在左侧选择图案、排版与底图
                        <br />
                        准备好后，生成你的第一稿。
                      </p>
                      {template && (
                        <div className="template-peek">
                          <img
                            src={template.thumbnail_url}
                            alt="当前排版参考"
                          />
                          <span>{template.name} · 排版参考</span>
                        </div>
                      )}
                    </div>
                  )}
                  {processing && (
                    <div className="processing-overlay" role="status">
                      <span className="spinner" />
                      <strong>
                        {phaseNames[job?.phase || ""] ||
                          job?.phase ||
                          "正在处理设计…"}
                      </strong>
                      <span>完成后自动更新，已有版本仍可下载</span>
                    </div>
                  )}
                  <div className="stage-bottomline">
                    <span>
                      {selected ? "已保存的设计版本" : "图案 · 排版 · 底图"}
                    </span>
                    <span>
                      {selected?.snapshot.output_profile?.is_demo || !selected
                        ? "DEMO OUTPUT"
                        : "SAVED DESIGN"}
                    </span>
                  </div>
                </div>
                {selected ? (
                  <>
                    <div className="preview-caption">
                      <span>
                        <Icon name="check" size={14} />
                        {isHistory ? "正在查看历史保存版本" : "当前设计已保存"}
                      </span>
                      <span>
                        {selected.provider === "test" ? "测试模式结果" : ""}
                      </span>
                    </div>
                    <div className="result-actions">
                      <button
                        className="secondary"
                        disabled={locked || !current?.parent_version_id}
                        onClick={() => void rollback()}
                      >
                        <Icon name="back" size={17} />
                        回退上一版
                      </button>
                      <a
                        className="primary"
                        href={selected.download_url}
                        download
                      >
                        <Icon name="download" size={17} />
                        {isHistory ? "下载所选版本" : "下载当前图"}
                      </a>
                    </div>
                    {isHistory && (
                      <div className="history-hint">
                        历史预览不改变当前版本。
                        <button
                          onClick={() =>
                            setSelectedVersionId(design!.current_version_id)
                          }
                        >
                          返回当前版本
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="generate-area">
                    <button
                      className="primary full"
                      disabled={!ready || locked || backgroundProcessing}
                      onClick={() => void generate()}
                    >
                      {processing ? (
                        <span className="spinner tiny" />
                      ) : (
                        <Icon name="spark" />
                      )}
                      {processing ? "正在生成首稿…" : "生成首稿"}
                      <Icon name="arrow" size={16} />
                    </button>
                    <small>
                      {!selection.asset_ids.length
                        ? "请先选择至少一个图案"
                        : !selection.template_id
                          ? "请选择一种排版模式"
                          : !selection.background_id
                            ? "请选择或生成底图"
                            : "素材已就绪 · 首稿不占用精修次数"}
                    </small>
                  </div>
                )}
              </div>
              <div className="panel history-panel">
                <div className="history-heading">
                  <h3>版本记录</h3>
                  <span>每一步灵感，都有迹可循</span>
                </div>
                {design?.versions?.length ? (
                  <div className="version-grid">
                    {design.versions.map((v) => (
                      <button
                        key={v.id}
                        className={`version-card ${v.id === selected?.id ? "selected" : ""}`}
                        onClick={() => setSelectedVersionId(v.id)}
                        aria-pressed={v.id === selected?.id}
                      >
                        <img
                          src={v.preview_url}
                          alt={`${versionName(v)}缩略图`}
                        />
                        <div>
                          <strong>{versionName(v)}</strong>
                          {v.id === design.current_version_id ? (
                            <span className="tiny-pill">当前</span>
                          ) : (
                            <small>V{v.sequence}</small>
                          )}
                        </div>
                        <small className="version-parent">
                          {v.parent_version_id
                            ? `基于 V${design.versions.find((p) => p.id === v.parent_version_id)?.sequence ?? "?"}`
                            : "初始版本"}
                          {v.prompt ? ` · ${v.prompt}` : ""}
                        </small>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="empty-history">
                    <span className="history-line" />
                    <span>生成首稿后，版本将保存在这里</span>
                    <span className="history-line" />
                  </div>
                )}
              </div>
              <div className="handoff-note">
                <span className="note-icon">
                  <Icon name="download" size={17} />
                </span>
                <div>
                  <strong>设计完成后，交给我们继续实现</strong>
                  <span>下载所选保存版本，由内部人员对接后续制作流程。</span>
                </div>
              </div>
            </section>
            <aside className="panel refinement-panel">
              <div className="panel-heading">
                <div>
                  <span className="step-label">03 / REFINE</span>
                  <h2>文字精修</h2>
                </div>
                <Icon name="spark" />
              </div>
              <div
                className={`quota-card ${remaining === 0 ? "exhausted" : ""}`}
              >
                <div>
                  <span>剩余精修次数</span>
                  <strong>
                    {remaining}
                    <small> / 2</small>
                  </strong>
                </div>
                <div className="quota-dots">
                  {[0, 1].map((i) => (
                    <span
                      key={i}
                      className={i < remaining ? "available" : ""}
                    />
                  ))}
                </div>
              </div>
              <div className="refinement-body">
                <label htmlFor="refinement">告诉我们，你想怎么改</label>
                <p>一次可填写多项要求，让设计更接近你的想法。</p>
                <textarea
                  id="refinement"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  maxLength={2000}
                  disabled={!current || locked || remaining === 0 || isHistory}
                  placeholder="例如：把图案缩小一些，间距拉开一点，保留现在的底色。"
                />
                <div className="text-limit">{prompt.length} / 2000</div>
                <div className="suggestions">
                  <span>
                    {testMode ? "可试试这些测试指令" : "给灵感一点提示"}
                  </span>
                  {[
                    "图案缩小一些，间距拉开一点",
                    "背景添加波点",
                    "给第一个图案添加星光",
                  ].map((text) => (
                    <button
                      key={text}
                      disabled={
                        !current || locked || remaining === 0 || isHistory
                      }
                      onClick={() => setPrompt(text)}
                    >
                      {text}
                      <Icon name="plus" size={13} />
                    </button>
                  ))}
                </div>
                <button
                  className="primary full refine-button"
                  disabled={
                    !current ||
                    locked ||
                    remaining === 0 ||
                    isHistory ||
                    !ready ||
                    (!prompt.trim() && !changed)
                  }
                  onClick={() => void refine()}
                >
                  {processing ? (
                    <span className="spinner tiny" />
                  ) : (
                    <Icon name="spark" />
                  )}
                  {processing
                    ? "正在处理…"
                    : remaining === 0
                      ? "精修次数已用完"
                      : "开始精修"}
                </button>
                <p className="refine-help">
                  {!current
                    ? "先生成首稿，再开始细化你的设计。"
                    : isHistory
                      ? "请返回当前版本后继续精修。"
                      : remaining === 0
                        ? "仍可查看历史、回退和下载。"
                        : changed
                          ? "本次将同时应用左侧的素材与排版选择。"
                          : "成功完成后计一次，系统失败不扣次。"}
                </p>
              </div>
              <div className="refine-footer">
                <div>
                  <Icon name="back" size={16} />
                  <strong>放心尝试，保留每个版本</strong>
                </div>
                <p>回退到当前版本的父版本；回退不会返还已使用的精修次数。</p>
                {testMode && (
                  <p className="test-limit">
                    测试替身仅支持已列明的参数与内容示例。其他要求会提示补充说明，真实
                    AI 尚未接通。
                  </p>
                )}
              </div>
            </aside>
          </div>
        )}
        <footer className="page-footer">
          <span>丝带设计助手 · V1</span>
          <span>{config?.output_profile?.name || "正在读取输出配置"}</span>
          <span>个人作品与素材保留 {config?.retention_hours ?? 50} 小时，请及时下载。</span>
        </footer>
      </main>
      {(modal === "pattern" || modal === "background") && (
        <Modal
          title={modal === "pattern" ? "图案素材库" : "底图素材库"}
          onClose={() => setModal(null)}
          wide
        >
          <div className="library-toolbar">
            <input
              aria-label="搜索素材"
              placeholder="搜索素材名称…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <label
              className={`secondary upload-label ${uploading ? "disabled" : ""}`}
            >
              <Icon name="upload" />
              {uploading ? "上传中…" : "上传素材"}
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                hidden
                disabled={uploading || locked}
                onChange={(e) => void upload(e.target.files, modal)}
              />
            </label>
          </div>
          {isAdmin && (
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={sharedUpload}
                onChange={(e) => setSharedUpload(e.target.checked)}
              />
              上传为共享素材，供所有账号使用
            </label>
          )}
          <p className="muted library-note">
            {modal === "pattern"
              ? "可选择多个已处理好的图案。"
              : "选择一种底图，作为设计背景。"}{" "}
            标记“演示”的素材仅供联调。
          </p>
          <div className="library-grid">
            {library.map((a) => {
              const picked =
                modal === "pattern"
                  ? selection.asset_ids.includes(a.id)
                  : selection.background_id === a.id;
              return (
                <div className="library-item" key={a.id}>
                  <button
                    className={`library-card ${picked ? "selected" : ""}`}
                    disabled={locked}
                    aria-pressed={picked}
                    onClick={() =>
                      modal === "pattern"
                        ? togglePattern(a.id)
                        : updateSelection({ ...selection, background_id: a.id })
                    }
                  >
                    <div
                      className={`library-image ${modal === "pattern" ? "checker" : ""}`}
                    >
                      <img src={a.url} alt={a.name} />
                      {picked && (
                        <span className="check-mark">
                          <Icon name="check" size={14} />
                        </span>
                      )}
                    </div>
                    <strong>{a.name}</strong>
                    <span>
                      {a.is_demo ? "演示 · " : ""}
                      {a.shared ? "共享素材" : "私有素材"}
                    </span>
                  </button>
                  {(!a.shared || isAdmin) && (
                    <button
                      className="hide-asset"
                      disabled={locked}
                      onClick={() => void hideAsset(a)}
                    >
                      从素材库移除
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          {!library.length && (
            <div className="empty-library">
              没有找到素材，可上传新的图案或底图。
            </div>
          )}
          <div className="modal-footer">
            <span>
              {modal === "pattern"
                ? `已选 ${selection.asset_ids.length} 个图案`
                : background
                  ? `已选：${background.name}`
                  : "尚未选择底图"}
            </span>
            <button className="primary" onClick={() => setModal(null)}>
              完成选择
              <Icon name="check" size={16} />
            </button>
          </div>
        </Modal>
      )}
      {modal === "designs" && (
        <Modal title="我的作品" onClose={() => setModal(null)} wide>
          <div className="design-library">
            {designs.map((d) => (
              <button
                key={d.id}
                disabled={
                  busy || !!pending || backgroundProcessing || uploading
                }
                className={`design-list-item ${d.id === design?.id ? "selected" : ""}`}
                onClick={() => void switchDesign(d.id)}
              >
                <span className="design-list-icon">
                  <Icon name="folder" size={23} />
                </span>
                <div>
                  <strong>{d.name}</strong>
                  <small>
                    {d.current_version_id ? "已有保存版本" : "尚未生成首稿"} ·
                    已精修 {d.successful_refinement_count} / 2 次
                  </small>
                </div>
                {d.active_job_id && <span className="tiny-pill">处理中</span>}
                <Icon name="arrow" />
              </button>
            ))}
          </div>
          {!designs.length && (
            <div className="empty-library">
              你的第一份作品，即将从这里开始。
            </div>
          )}
          <div className="modal-footer">
            <span>作品、额度和版本均保存在服务端</span>
            <button
              className="primary"
              disabled={busy || !!pending || backgroundProcessing || uploading}
              onClick={() => void newDesign()}
            >
              <Icon name="plus" />
              新建作品
            </button>
          </div>
        </Modal>
      )}
      {modal === "admin" && isAdmin && (
        <Admin onClose={() => setModal(null)} onChanged={loadCatalog} />
      )}
    </div>
  );
}
