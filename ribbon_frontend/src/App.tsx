import {
  useEffect,
  useMemo,
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
  type GenerateRequest,
  type Job,
  type Selection,
  type Template,
  type User,
  type Version,
} from "./api";
import Admin from "./Admin";
import LayoutExamples, { type LayoutExamplesCatalog } from "./LayoutExamples";

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
  className = "",
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  className?: string;
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
          "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex=\"0\"]",
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
        className={`modal ${wide ? "modal-wide" : ""} ${className}`}
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
  background_tone: "soft",
  design_density: "balanced",
};
const basicLayoutModes = new Set(["grid", "stagger", "scatter", "single", "ends", "panels"]);
const layoutHints: Record<string, string> = {
  grid: "完整图案按行排列，保持比例；可用画面密度选择疏朗或饱满。",
  stagger: "相邻行错开，整组图案连续重复；文字和装饰作为一个整体保留。",
  scatter: "轻微错落排列，默认保持图案朝向；不会自动拆出小装饰。",
  single: "适合文字或较大的主体，多个图案按选择顺序整组重复。",
  bordered: "第一个图案放中间，其余图案做上下边饰；至少选择 2 个图案。",
  scene: "第一个图案作主图，其余稍小、底部对齐，再整组循环；辅助装饰需自行选入。",
  fullwidth: "只选 1 张完整设计，保持比例；循环作品会将整幅作为一个单元重复。",
  alternating: "图案一大一小依次重复，可选择 1–12 个图案。",
  ends_open: "选 1–2 个图案放在两端，中间留白；循环作品会将两端与留白作为完整面板重复。",
  split: "至少选择 2 个图案，前半组放左侧，后半组放右侧。",
  stacked: "至少选择 2 个图案，前半组放上方，后半组放下方。",
  opposed: "相邻图案正向、倒置交替，旋转 180°，不会镜像翻字。",
};
function layoutSelectionIssue(mode: string | undefined, count: number) {
  if (!count) return "";
  if (mode === "fullwidth" && count !== 1)
    return "整幅定位只使用 1 个完整图案，请移除多余图案。";
  if (mode === "ends_open" && count > 2)
    return "两端留白最多使用 2 个图案，请保留 1–2 个。";
  if (mode && ["bordered", "split", "stacked"].includes(mode) && count < 2)
    return "这类排版至少需要 2 个图案，请再选择一个。";
  return "";
}
function recommendedSelection(
  assets: Asset[],
  templates: Template[],
): Selection {
  return {
    asset_ids: ["demo-flower", "demo-star", "demo-ring"].filter((id) =>
      assets.some((a) => a.id === id),
    ),
    background_id: assets.find((a) => a.id === "demo-bg-sage")?.id || "",
    background_tone: "soft",
    design_density: "balanced",
    template_id:
      templates.find((t) => t.mode === "stagger" && t.enabled)?.id ||
      templates.find((t) => t.enabled)?.id ||
      "",
  };
}

function restoreSelection(value: Selection, version?: Version): Selection {
  const snapshot = version?.snapshot;
  const modern = !version || ["design-rhythm-v1", "design-rhythm-v2", "seamless-unit-v1"].includes(snapshot?.layout_engine || "");
  const next: Selection = {
    ...value,
    background_tone: value.background_tone ?? snapshot?.background_tone ?? (modern ? "soft" : "original"),
  };
  if (modern) {
    next.design_density = value.design_density ?? snapshot?.design_density ?? "balanced";
  } else {
    // A cached draft cannot grant a legacy version the new layout controls.
    delete next.design_density;
  }
  return next;
}

function LoopPreview({ version, sizeLabel }: { version: Version; sizeLabel: string }) {
  const [continuous, setContinuous] = useState(false);
  const [seams, setSeams] = useState(false);
  const loop = version.snapshot.loop!;
  const source = version.snapshot.output_profile_source;
  return <div className="loop-preview">
    <div className="loop-view-heading">
      <strong>{continuous ? "连续效果预览" : "循环单元"}</strong>
      <span>{continuous ? "同一单元横向重复 3 次" : sizeLabel}</span>
    </div>
    <div className="loop-unit-view" hidden={continuous}>
      <img src={version.preview_url} decoding="async" alt={`${versionName(version)}的循环单元预览`} />
    </div>
    {/* Keep the same URLs mounted: changing the view only changes visibility,
        never requests a new master or a separately rendered long-strip file. */}
    <div className="loop-continuity" hidden={!continuous}>
      <div className={`loop-continuity-track ${seams ? "show-seams" : ""}`}>
        {[0, 1, 2].map(index => <div className="loop-repeat" key={index}>
          <img src={version.preview_url} decoding="async" alt={index === 0 ? `${versionName(version)}的三次连续效果预览` : ""} />
        </div>)}
      </div>
    </div>
    <div className="loop-preview-tools">
      <button type="button" className="loop-view-button" aria-pressed={continuous}
        onClick={() => setContinuous(value => !value)}>
        {continuous ? "返回循环单元" : "查看连续效果"}
      </button>
      {continuous && <label className="loop-seam-toggle">
        <input type="checkbox" checked={seams} onChange={event => setSeams(event.target.checked)} />显示接缝位置
      </label>}
    </div>
    <p className="loop-preview-note">页面展示缩小预览；下载为一个原尺寸循环单元，连续效果仅供查看。</p>
    <div className={`loop-check ${loop.status === "checked" ? "checked" : "needs-review"}`}>
      <strong>{loop.status === "checked" ? "工程循环检查通过" : "循环效果需要复核"}</strong>
      {loop.status === "checked" && <span>画面与印刷效果仍需人工确认。</span>}
      {!!loop.issues?.length && <ul aria-label="循环检查提示">
        {loop.issues.map((issue, index) => <li key={`${issue.code}:${index}`} className={issue.severity}>{issue.message}</li>)}
      </ul>}
    </div>
    {loop.mode_notice && <p className="loop-mode-notice">{loop.mode_notice}</p>}
    <details className="loop-technical-details">
      <summary>技术详情</summary>
      <dl>
        <div><dt>下载尺寸</dt><dd>{sizeLabel || `${loop.width}×${loop.height}px`}</dd></div>
        <div><dt>循环方式</dt><dd>{loop.kind === "panel" ? "定位区段循环" : "图案序列循环"}</dd></div>
        <div><dt>检查引擎</dt><dd>{loop.engine}</dd></div>
        {source && <div><dt>来源配置</dt><dd>{source.name}{source.width && source.height ? ` · ${source.width}×${source.height}px` : ""}</dd></div>}
      </dl>
    </details>
  </div>;
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
    [backgroundPrompt, setBackgroundPrompt] = useState(""),
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
      "pattern" | "background" | "designs" | "layouts" | "admin" | null
    >(null),
    [pending, setPending] = useState<Pending | null>(() =>
      loadLocal(prefix + "pending", null),
    );
  const [search, setSearch] = useState(""),
    [uploading, setUploading] = useState(false),
    [uploadProgress, setUploadProgress] = useState<{ completed: number; total: number } | null>(null),
    [sharedUpload, setSharedUpload] = useState(false);
  const [examplesView, setExamplesView] = useState<{ mode: string | null; name: string } | null>(null);
  const [libraryPage, setLibraryPage] = useState(0);
  const [designTarget, setDesignTarget] = useState<{ id: string; name: string; loading: boolean } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Design | null>(null);
  const [deletedDesigns, setDeletedDesigns] = useState<Design[]>([]);
  const [showDeleted, setShowDeleted] = useState(false);
  const [deletedLoading, setDeletedLoading] = useState(false);
  // The default follows the server capability. An explicit opt-out lasts for
  // this draft only; switching works clears both the choice and its reference.
  const [aiDraftChoice, setAiDraftChoice] = useState<boolean | null>(null);
  const [aiDraftReference, setAiDraftReference] = useState<{ code: string; mode: string } | null>(null);
  const examplesCache = useRef<LayoutExamplesCatalog | null>(null);
  useEffect(() => {
    if (!active || view !== "ribbon") {
      setExamplesView(null);
      examplesCache.current = null;
    }
  }, [active, view]);
  const gate = useRef(false),
    uploadRef = useRef<HTMLInputElement>(null),
    libraryUploadRef = useRef<HTMLInputElement>(null),
    uploadGate = useRef(false),
    uploadAbort = useRef<AbortController | null>(null),
    mounted = useRef(true),
    lastVersion = useRef<string | null>(null),
    designRef = useRef<Design | null>(null),
    designLoadSequence = useRef(0),
    designAbort = useRef<AbortController | null>(null),
    deletedAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      uploadAbort.current?.abort();
      designAbort.current?.abort();
      deletedAbort.current?.abort();
    };
  }, []);
  const isAdmin = user.role === "admin",
    current = design?.versions?.find((v) => v.id === design.current_version_id),
    selected =
      design?.versions?.find((v) => v.id === selectedVersionId) || current;
  const remaining = Math.max(0, 2 - (design?.successful_refinement_count || 0));
  const processing = !!design?.active_job_id || running(job),
    backgroundProcessing = running(backgroundJob),
    locked = busy || processing || !!pending || uploading || !!designTarget;
  const isHistory = !!selected && selected.id !== design?.current_version_id;
  const shownProfile = selected?.snapshot?.output_profile;
  const selectedLoop = selected?.snapshot.loop?.engine === "seamless-unit-v1";
  const sizeLabel =
    shownProfile?.width && shownProfile?.height && shownProfile?.dpi
      ? `${shownProfile.width}×${shownProfile.height}px · ${shownProfile.dpi} DPI · ` +
        `${((shownProfile.width / shownProfile.dpi) * 2.54).toFixed(1)}×` +
        `${((shownProfile.height / shownProfile.dpi) * 2.54).toFixed(1)} cm`
      : "";
  const assetIndex = useMemo(() => new Map(assets.map(a => [a.id, a])), [assets]);
  const catalog = useMemo(() => {
    const result: Record<Asset["kind"], { asset: Asset; query: string }[]> = { pattern: [], background: [] };
    for (const asset of assets) result[asset.kind].push({ asset, query: asset.name.toLocaleLowerCase() });
    return result;
  }, [assets]);
  const template = templates.find((t) => t.id === selection.template_id);
  const layoutIssue = layoutSelectionIssue(template?.mode, selection.asset_ids.length);
  const ready =
    selection.asset_ids.length > 0 &&
    !!selection.background_id &&
    !!template &&
    !layoutIssue;
  const changed =
    !!current &&
    (JSON.stringify(current.snapshot.asset_refs) !==
      JSON.stringify(selection.asset_ids) ||
      current.snapshot.background_ref !== selection.background_id ||
      current.snapshot.template_id !== selection.template_id ||
      (current.snapshot.background_tone || "original") !== (selection.background_tone || "original") ||
      (current.snapshot.design_density || "balanced") !== (selection.design_density || "balanced"));
  const selectedPatterns = selection.asset_ids
    .map((id) => assetIndex.get(id))
    .filter(Boolean) as Asset[];
  const background = assetIndex.get(selection.background_id);
  const visibleTemplates = templates.filter((t) => t.enabled || t.id === selection.template_id);
  const basicTemplates = visibleTemplates.filter((t) => basicLayoutModes.has(t.mode));
  const moreTemplates = visibleTemplates.filter((t) => !basicLayoutModes.has(t.mode));
  const testMode = config?.provider === "test";
  // Local/demo fixtures do not hold real model credentials. They remain
  // explicitly marked test operations; employee services must never use them.
  const aiAvailable = testMode ? config?.auth_mode !== "hsd" : config?.ai_ready === true;
  const aiDraftAvailable = config?.provider === "deepseek_seedream" && config?.ai_ready === true && config?.ai_draft_available === true;
  const isFirstDraft = !current && !design?.versions?.length;
  const aiDraftEnabled = isFirstDraft && aiDraftAvailable && aiDraftChoice !== false;
  const draftReference = aiDraftEnabled && aiDraftReference?.mode === template?.mode ? aiDraftReference : null;
  // A changed selection can be applied by the compositor without a model.
  // Keep this path available when an administrator has disabled AI.
  const selectionOnly = changed && (!prompt.trim() || ["应用所选配置", "应用新的素材与排版"].includes(prompt.trim()));
  const savedEditing = current?.editing || config?.editing;
  // Reselecting assets recreates independent layers, but retains this work's
  // immutable output profile. The global profile may have changed meanwhile.
  const editing = changed && savedEditing && ["test", "openai", "deepseek_seedream"].includes(config?.provider || "")
    ? { ...savedEditing,
        allowed_operations: ["parameters", "edit_asset", "edit_background", ...(savedEditing.composite_edit ? ["edit_composite"] : [])],
        allowed_parameters: ["scale", "rotation", "offset_x", "offset_y", "background_color",
          ...(["fullwidth", "ends_open"].includes(template?.mode || "") ? [] : ["spacing"])],
      }
    : savedEditing;
  const aiRefinementUnavailable = !selectionOnly && (!aiAvailable || editing?.allowed_operations.length === 0);
  const canPlanOperation = (kind: string) => !editing || editing.allowed_operations.includes(kind);
  const spacingAvailable = template?.mode !== "fullwidth" && template?.mode !== "ends_open" &&
    (!editing || editing.allowed_parameters.includes("spacing"));
  const suggestions = [
    ...(canPlanOperation("parameters") ? [spacingAvailable ? "图案缩小一些，间距拉开一点" : "图案缩小一些"] : []),
    ...(canPlanOperation("edit_background") ? ["背景添加波点"] : []),
    ...(canPlanOperation("edit_asset") ? ["给第一个图案添加星光"] : []),
    ...(canPlanOperation("edit_composite") ? ["给画面添加星光"] : []),
  ];
  function templateOption(t: Template) {
    return (
      <div key={t.id} className="template-option">
        <button
          className={`template-card ${selection.template_id === t.id ? "selected" : ""}`}
          disabled={locked}
          aria-pressed={selection.template_id === t.id}
          onClick={() => updateSelection({ ...selection, template_id: t.id })}
        >
          <img src={t.thumbnail_url} alt={`${t.name}样式图`} loading="lazy" decoding="async" />
          <span>{t.name}{selection.template_id === t.id && <Icon name="check" size={14} />}</span>
        </button>
        <button
          type="button"
          className="template-example-button"
          aria-label={`查看${t.name}案例`}
          onClick={() => { setModal(null); setExamplesView({ mode: t.mode, name: t.name }); }}
        >查看案例</button>
      </div>
    );
  }

  function updateSelection(value: Selection) {
    if (value.template_id !== selection.template_id) setAiDraftReference(null);
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
      // Show both ends on the first view of a work or newly saved version.
      // Same-version polling must preserve the employee's zoom choice.
      setPreviewZoom(v && ["ends", "ends_open"].includes(v.snapshot.template_mode) ? "fit" : "detail");
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
                background_tone: v.snapshot.background_tone || "original",
                ...(["design-rhythm-v1", "design-rhythm-v2", "seamless-unit-v1"].includes(v.snapshot.layout_engine || "") ? {design_density: v.snapshot.design_density || "balanced"} : {}),
              }
            : emptySelection;
      setSelection(restoreSelection(next, v));
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
          setSelection(restoreSelection(saved?.value || recommendedSelection(a, t)));
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
    const controller = new AbortController();
    const sequence = designLoadSequence.current;
    const targetId = design?.id;
    const stale = () => cancelled || !mounted.current || sequence !== designLoadSequence.current ||
      (targetId !== undefined && designRef.current?.id !== targetId);
    let cancelled = false,
      inflight = false;
    const tick = async () => {
      if (inflight || document.hidden) return;
      inflight = true;
      try {
        if (design?.id) {
          const d = await api<Design>(`/designs/${design.id}`, { signal: controller.signal });
          if (stale()) return;
          const previous = designRef.current;
          applyDesign(d);
          const id = d.active_job_id || previous?.active_job_id || job?.id;
          if (id) {
            const updated = await api<Job>(`/jobs/${id}`, { signal: controller.signal });
            if (stale()) return;
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
          const updated = await api<Job>(`/jobs/${backgroundJob.id}`, { signal: controller.signal });
          if (stale()) return;
          setBackgroundJob(updated);
          if (updated.status === "SUCCEEDED" && updated.result_asset_id) {
            const a = await api<Asset[]>("/assets", { signal: controller.signal });
            if (stale()) return;
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
        if (!stale()) {
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
      controller.abort();
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
    const controller = new AbortController();
    const sequence = designLoadSequence.current;
    void api<Asset[]>("/assets", { signal: controller.signal })
      .then(a => { if (!controller.signal.aborted && mounted.current && sequence === designLoadSequence.current) setAssets(a); })
      .catch(() => { if (!controller.signal.aborted && sequence === designLoadSequence.current) setOffline(true); });
    return () => controller.abort();
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
        body: { idempotency_key: crypto.randomUUID(), ...selection,
          ai_assisted: aiDraftEnabled, reference_code: draftReference?.code || null,
        } satisfies GenerateRequest,
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
      aiRefinementUnavailable ||
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
    ++designLoadSequence.current;
    designAbort.current?.abort();
    setDesignTarget(null);
    setAiDraftChoice(null);
    setAiDraftReference(null);
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
    const sequence = ++designLoadSequence.current;
    designAbort.current?.abort();
    const controller = new AbortController();
    designAbort.current = controller;
    // Clear both the render and synchronous references before requesting the
    // target. A previous preview, polling response or download is never its UI.
    const name = designs.find(d => d.id === id)?.name || "所选作品";
    setDesignTarget({ id, name, loading: true });
    designRef.current = null;
    setDesign(null);
    setSelectedVersionId(null);
    setSelection(emptySelection);
    lastVersion.current = null;
    setJob(null);
    setPrompt("");
    setAiDraftChoice(null);
    setAiDraftReference(null);
    setNotice(null);
    setModal(null);
    try {
      const d = await api<Design>(`/designs/${id}`, { signal: controller.signal });
      if (!mounted.current || sequence !== designLoadSequence.current || controller.signal.aborted) return;
      applyDesign(d, true);
      setDesignTarget(null);
      setJob(d.active_job || null);
      setOffline(false);
    } catch (e) {
      if (!mounted.current || sequence !== designLoadSequence.current || controller.signal.aborted) return;
      setDesignTarget({ id, name, loading: false });
      setNotice({ text: message(e), type: "error" });
      if (e instanceof ApiError && e.status === 401) onLogout();
    }
  }
  async function loadDeletedDesigns() {
    deletedAbort.current?.abort();
    const controller = new AbortController();
    deletedAbort.current = controller;
    setDeletedLoading(true);
    try {
      const list = await api<Design[]>("/designs?deleted=true", { signal: controller.signal });
      if (!controller.signal.aborted && mounted.current) setDeletedDesigns(list);
    } catch (e) {
      if (!controller.signal.aborted && mounted.current) setNotice({ text: message(e), type: "error" });
    } finally {
      if (!controller.signal.aborted && mounted.current) setDeletedLoading(false);
    }
  }
  async function deleteDesign(d: Design) {
    if (busy || pending || uploading || backgroundProcessing || designTarget?.loading || d.active_job_id) return;
    await action(async () => {
      await api(`/designs/${d.id}`, { method: "DELETE" });
      if (!mounted.current) return;
      deletedAbort.current?.abort();
      setDeletedLoading(false);
      setDesigns(previous => previous.filter(item => item.id !== d.id));
      setDeletedDesigns(previous => [d, ...previous.filter(item => item.id !== d.id)]);
      if (designRef.current?.id === d.id || designTarget?.id === d.id) {
        ++designLoadSequence.current;
        designAbort.current?.abort();
        designRef.current = null;
        setDesign(null);
        setDesignTarget(null);
        setSelectedVersionId(null);
        lastVersion.current = null;
        setJob(null);
        setPrompt("");
        setAiDraftChoice(null);
        setAiDraftReference(null);
        setSelection(recommendedSelection(assets, templates));
        saveLocal(prefix + "design", null);
        saveLocal(prefix + "selection", null);
      }
      setDeleteTarget(null);
      setNotice({ text: `作品已删除，可在“已删除作品”中恢复；保留 ${config?.retention_hours ?? 50} 小时，累计精修次数不变。`, type: "success" });
    });
  }
  async function restoreDesign(d: Design) {
    deletedAbort.current?.abort();
    setDeletedLoading(false);
    await action(async () => {
      const restored = await post<Design>(`/designs/${d.id}/restore`, {});
      if (!mounted.current) return;
      setDesigns(previous => [restored, ...previous.filter(item => item.id !== d.id)]);
      setDeletedDesigns(previous => previous.filter(item => item.id !== d.id));
      setNotice({ text: "作品已恢复，版本与累计精修次数保持不变。", type: "success" });
    });
  }
  async function generateBackground() {
    if (locked || backgroundProcessing) return;
    if (!aiAvailable) {
      setNotice({ text: "AI 服务尚未配置，请联系管理员；仍可使用已有底图生成首稿。", type: "info" });
      return;
    }
    await action(() =>
      executePending({
        path: "/background-jobs",
        body: { idempotency_key: crypto.randomUUID(), prompt: backgroundPrompt.trim() },
        kind: "background",
        designId: design?.id,
      }),
    );
  }
  async function upload(
    files: FileList | null,
    kind: "pattern" | "background",
  ) {
    if (!files?.length || uploadGate.current || locked) return;
    const batch = Array.from(files);
    const shared = isAdmin && sharedUpload;
    uploadGate.current = true;
    const controller = new AbortController();
    uploadAbort.current = controller;
    setUploading(true);
    setUploadProgress({ completed: 0, total: batch.length });
    setNotice({ text: `正在上传第 1 / ${batch.length} 张…`, type: "info" });
    const added: Asset[] = [];
    try {
      // Keep requests serial to avoid multiplying image conversion memory.
      // Publish each acknowledged asset immediately instead of waiting for
      // the whole batch and another full catalog request.
      for (const [index, file] of batch.entries()) {
        if (!mounted.current) return;
        const form = new FormData();
        form.append("file", file);
        form.append("kind", kind);
        form.append("name", file.name.replace(/\.[^.]+$/, ""));
        form.append("shared", String(shared));
        const asset = await api<Asset>("/assets", { method: "POST", body: form, signal: controller.signal });
        if (!mounted.current) return;
        added.push(asset);
        setAssets((previous) => previous.some((item) => item.id === asset.id)
          ? previous.map((item) => item.id === asset.id ? asset : item)
          : [...previous, asset]);
        setSelection((previous) => {
          const value = kind === "pattern"
            ? { ...previous, asset_ids: [...new Set([...previous.asset_ids, asset.id])].slice(0, 12) }
            : { ...previous, background_id: asset.id };
          saveLocal(prefix + "selection", {
            design_id: designRef.current?.id || null,
            base_version_id: designRef.current?.current_version_id || null,
            value,
          });
          return value;
        });
        setUploadProgress({ completed: added.length, total: batch.length });
        if (index + 1 < batch.length)
          setNotice({ text: `已上传 ${added.length} / ${batch.length} 张，正在上传第 ${index + 2} 张…`, type: "info" });
      }
      setNotice({
        text: `已上传 ${added.length} 个${kind === "pattern" ? "图案" : "底图"}。`,
        type: "success",
      });
    } catch (e) {
      if (!mounted.current) return;
      if (e instanceof ApiError && e.status === 401) onLogout();
      const failure = e instanceof ApiError ? message(e)
        : "本张上传结果尚未确认。请重新载入网页，在素材库查看后再决定是否重传。";
      setNotice({ text: added.length ? `已上传 ${added.length} 个，其余未完成：${failure}` : failure, type: "error" });
    } finally {
      uploadGate.current = false;
      uploadAbort.current = null;
      if (mounted.current) {
        setUploading(false);
        setUploadProgress(null);
      }
      if (uploadRef.current) uploadRef.current.value = "";
      if (libraryUploadRef.current) libraryUploadRef.current.value = "";
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
  const status = designTarget ? designTarget.loading ? "正在打开作品" : "作品打开失败" : processing
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
  const library = useMemo(() => {
    if (modal !== "pattern" && modal !== "background") return [];
    const query = search.toLocaleLowerCase().trim();
    return query ? catalog[modal].filter(item => item.query.includes(query)).map(item => item.asset)
      : catalog[modal].map(item => item.asset);
  }, [catalog, modal, search]);
  const pageCount = Math.max(1, Math.ceil(library.length / 36));
  const shownPage = Math.min(libraryPage, pageCount - 1);
  const libraryItems = library.slice(shownPage * 36, (shownPage + 1) * 36);
  useEffect(() => { setLibraryPage(0); }, [modal, search]);

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
                  ? "AI 服务已配置"
                  : "AI 尚未配置"}
            </strong>
            <span>
              {testMode
                ? "底图和内容编辑使用明确的测试替身，非真实 AI 效果。"
                : config?.ai_ready
                  ? "AI 理解要求并改图，程序按原规格重新排版。"
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
                    {uploading ? `上传 ${uploadProgress?.completed || 0}/${uploadProgress?.total || 0}` : "上传图案"}
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
                    {selectedPatterns.map((a, index) => (
                      <div className="pattern-tile" key={a.id}>
                        <div className="checker">
                          <img src={a.thumbnail_url || a.url} alt={a.name} decoding="async" />
                          <button
                            className="remove-asset"
                            disabled={locked}
                            aria-label={`移除${a.name}`}
                            onClick={() => togglePattern(a.id)}
                          >
                            ×
                          </button>
                        </div>
                        <span title={`第 ${index + 1} 个图案：${a.name}`}>{index + 1}. {a.name}</span>
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
                  <button type="button" className="template-examples-all" onClick={() => setExamplesView({ mode: null, name: "全部排版案例" })}>查看全部案例</button>
                </div>
                <div className="template-grid">
                  {basicTemplates.map(templateOption)}
                </div>
                {moreTemplates.length > 0 && (
                  <div className="more-layouts">
                    <button type="button" className="more-layouts-toggle"
                      aria-expanded={modal === "layouts"} aria-haspopup="dialog"
                      onClick={() => setModal("layouts")}>
                      <span>更多排法（{moreTemplates.length}）</span>
                      <span aria-hidden="true">›</span>
                    </button>
                  </div>
                )}
                {template && !basicLayoutModes.has(template.mode) && <div className="chosen-layout">
                  <strong>已选：{template.name}</strong>
                  <button type="button" className="template-example-button" onClick={() => setExamplesView({ mode: template.mode, name: template.name })}>查看{template.name}案例</button>
                </div>}
                {template && layoutHints[template.mode] && (
                  <p className="layout-selection-help">{layoutHints[template.mode]}</p>
                )}
                {layoutIssue && <p className="layout-selection-issue" id="ribbon-layout-issue" role="alert">{layoutIssue}</p>}
                {(!current || ["design-rhythm-v1", "design-rhythm-v2", "seamless-unit-v1"].includes(current.snapshot.layout_engine || "")) && (
                  <label className="density-control">画面密度
                    <select aria-label="画面密度" value={selection.design_density || "balanced"} disabled={locked}
                      onChange={(event) => updateSelection({ ...selection, design_density: event.target.value as Selection["design_density"] })}>
                      <option value="airy">疏朗</option>
                      <option value="balanced">均衡</option>
                      <option value="rich">饱满</option>
                    </select>
                  </label>
                )}
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
                    disabled={locked || backgroundProcessing || !aiAvailable}
                    onClick={() => void generateBackground()}
                  >
                    {backgroundProcessing ? (
                      <span className="spinner tiny" />
                    ) : (
                      <Icon name="spark" size={16} />
                    )}
                    {testMode ? "生成测试底图" : "AI 生成底图"}
                  </button>
                </div>
                <label className="background-prompt-label" htmlFor="background-prompt">底图要求（可不填）</label>
                <textarea
                  id="background-prompt"
                  className="background-prompt"
                  value={backgroundPrompt}
                  onChange={(event) => setBackgroundPrompt(event.target.value)}
                  maxLength={2000}
                  rows={2}
                  disabled={locked || backgroundProcessing || !aiAvailable}
                  placeholder="例如：浅蓝色细条纹，不要文字；不填则随机生成。"
                  aria-describedby={!aiAvailable ? "background-ai-unavailable" : undefined}
                />
                {!aiAvailable && <p className="model-help" id="background-ai-unavailable">AI 尚未配置，仍可从底图库选图或上传后生成首稿。</p>}
                {background ? (
                  <div className="background-selected">
                    <img src={background.thumbnail_url || background.url} alt="选中的底图" loading="lazy" decoding="async" />
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
                <label className="background-tone-control">
                  <input type="checkbox"
                    checked={selection.background_tone === "soft"}
                    disabled={locked || backgroundProcessing}
                    onChange={(event) => updateSelection({ ...selection, background_tone: event.target.checked ? "soft" : "original" })}
                  />
                  柔和底纹，突出主图
                </label>
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
                    <h2>{designTarget?.name || design?.name || "设计预览"}</h2>
                  </div>
                  <span className={`state-pill ${processing ? "working" : ""}`}>
                    <span className="status-dot" />
                    {status}
                  </span>
                </div>
                {selected ? (
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
                        {isHistory ? "下载所选版本" : selectedLoop ? "下载循环单元" : "下载当前图"}
                      </a>
                    </div>
                ) : (
                  <div className="generate-area">
                    <button
                      className="primary full"
                      disabled={!ready || locked || backgroundProcessing}
                      aria-describedby={layoutIssue ? "ribbon-layout-issue" : undefined}
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
                    {isFirstDraft && !designTarget && aiDraftAvailable && <div className="ai-draft-options">
                      <label>
                        <input type="checkbox" checked={aiDraftEnabled} disabled={locked || backgroundProcessing}
                          onChange={event => { setAiDraftChoice(event.target.checked); if (!event.target.checked) setAiDraftReference(null); }} />
                        AI搭配底纹与装饰
                      </label>
                      {aiDraftEnabled ? <>
                        <p>原人物文字不重画；所选案例会发送给Seedream。未选案例则不发送案例图。</p>
                        {draftReference ? <div className="ai-draft-reference"><span>参考案例：<strong>{draftReference.code}</strong></span><button type="button" disabled={locked} onClick={() => setAiDraftReference(null)}>取消案例参考</button></div> :
                          <button type="button" className="ai-reference-picker" disabled={locked || !template} onClick={() => setExamplesView({ mode: template?.mode || null, name: template?.name || "全部排版案例" })}>选择案例参考</button>}
                      </> : <p>按原素材直接排版，首稿不调用AI搭配。</p>}
                    </div>}
                    <small>
                      {!selection.asset_ids.length
                        ? "请先选择至少一个图案"
                        : !selection.template_id
                          ? "请选择一种排版模式"
                          : !selection.background_id
                            ? "请选择或生成底图"
                            : layoutIssue || "素材已就绪 · 首稿不占用精修次数"}
                    </small>
                  </div>
                )}
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
                  {designTarget ? (
                    <div className="empty-canvas design-loading" role="status" aria-live="polite">
                      {designTarget.loading ? <><span className="spinner" /><h3>正在打开作品…</h3><p>正在读取所选作品的版本和素材。</p></> : <><h3>作品打开失败</h3><p>请重试，或从“我的作品”选择其他作品。</p><button className="secondary" onClick={() => void switchDesign(designTarget.id)}>重试打开作品</button></>}
                    </div>
                  ) : selected && selectedLoop ? (
                    <LoopPreview key={`${design?.id}:${selected.id}`} version={selected} sizeLabel={sizeLabel} />
                  ) : selected ? (
                    <>
                      <div className={`ribbon-display ${previewZoom}`}>
                        <img
                          key={`${design?.id}:${selected.id}:${previewZoom}`}
                          decoding="async"
                          src={
                            previewZoom === "detail"
                              ? selected.view_url || selected.preview_url
                              : selected.preview_url
                          }
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
                  null
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
                          loading="lazy"
                          decoding="async"
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
                <p>可写“第一个图案”或图案名称，再说清要改什么。</p>
                {editing && !editing.composite_edit && <p className="model-edit-boundary">{editing.composite_edit_reason || "当前长条请修改独立图案或底图，再按原规格重新排版。"}</p>}
                <textarea
                  id="refinement"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  maxLength={2000}
                  disabled={!current || locked || remaining === 0 || isHistory}
                  placeholder={!spacingAvailable
                    ? "例如：把图案缩小一些，保留现在的底色。"
                    : "例如：把图案缩小一些，间距拉开一点，保留现在的底色。"}
                />
                <div className="text-limit">{prompt.length} / 2000</div>
                <div className="suggestions">
                  <span>
                    {testMode ? "可试试这些测试指令" : "给灵感一点提示"}
                  </span>
                  {suggestions.map((text) => (
                    <button
                      key={text}
                      disabled={
                        !current || locked || remaining === 0 || isHistory || !aiAvailable
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
                  aria-describedby={layoutIssue ? "ribbon-layout-issue" : undefined}
                  disabled={
                    !current ||
                    locked ||
                    remaining === 0 ||
                    isHistory ||
                    !ready ||
                    aiRefinementUnavailable ||
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
                        : !aiAvailable
                          ? changed ? "AI 尚未配置；清空文字可仅应用所选素材与排版，成功后计一次。" : "AI 尚未配置，仍可查看、下载或更换素材后应用所选配置。"
                          : editing?.allowed_operations.length === 0 && !selectionOnly
                            ? "当前版本不支持直接修改，请重新选择素材与排版后应用。"
                        : changed
                          ? "本次将同时应用左侧的素材与排版选择。"
                          : "成功完成后计一次，系统失败不扣次。"}
                </p>
              </div>
              <div className="refine-footer">
                <details className="model-workflow-help">
                  <summary>AI 怎么参与</summary>
                  <p>DeepSeek 根据文字和所选图案的名称、顺序理解要求；当前不把图片发给它审图。对象不明确时请补充说明。</p>
                  <p>Seedream 负责生成底图、修改图案或底图；程序负责原尺寸排版、版本与下载。首稿使用原素材，不由模型重画。</p>
                  <p>模型配置齐全不等于效果已验收。实际生成的颜色、文字和细节仍请核对。</p>
                </details>
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
      {modal === "layouts" && (
        <Modal title="选择排版模式" onClose={() => setModal(null)} wide className="layout-picker-modal">
          <p className="muted library-note">选择排法后点击完成。案例只作排版参考，正式规格由内部配置决定。</p>
          <div className="layout-picker-grid template-grid">{visibleTemplates.map(templateOption)}</div>
          <div className="modal-footer">
            <span>已选：{template?.name || "尚未选择排版"}</span>
            <button className="primary" onClick={() => setModal(null)}>完成选择<Icon name="check" size={16} /></button>
          </div>
        </Modal>
      )}
      {examplesView && active && view === "ribbon" && (
        <Modal
          title={examplesView.mode ? `${examplesView.name} · 案例` : "全部排版案例"}
          onClose={() => setExamplesView(null)}
          wide
          className="layout-examples-modal"
        >
          <LayoutExamples
            mode={examplesView.mode}
            cache={examplesCache}
            onUnauthorized={onLogout}
            onViewAll={() => setExamplesView({ mode: null, name: "全部排版案例" })}
            referenceMode={template?.mode}
            onChooseReference={aiDraftEnabled && !locked && !backgroundProcessing ? example => {
              if (!template || !example.available || example.reference_only || !example.mode_tags.includes(template.mode)) return;
              setAiDraftReference({ code: example.code, mode: template.mode });
              setExamplesView(null);
            } : undefined}
          />
        </Modal>
      )}
      {(modal === "pattern" || modal === "background") && (
        <Modal
          title={modal === "pattern" ? "图案素材库" : "底图素材库"}
          onClose={() => setModal(null)}
          wide
          className="asset-library-modal"
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
              {uploading ? `上传 ${uploadProgress?.completed || 0}/${uploadProgress?.total || 0}` : "上传素材"}
              <input
                ref={libraryUploadRef}
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
                disabled={locked}
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
            {libraryItems.map((a) => {
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
                      <img src={a.thumbnail_url || a.url} alt={a.name} loading="lazy" decoding="async" />
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
          {library.length > 36 && <nav className="library-pagination" aria-label="素材分页">
            <button className="secondary small" disabled={shownPage === 0} onClick={() => setLibraryPage(shownPage - 1)}>上一页</button>
            <span role="status">第 {shownPage + 1} / {pageCount} 页 · 共 {library.length} 项</span>
            <button className="secondary small" disabled={shownPage + 1 >= pageCount} onClick={() => setLibraryPage(shownPage + 1)}>下一页</button>
          </nav>}
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
        <Modal title="我的作品" onClose={() => { setModal(null); setDeleteTarget(null); }} wide className="design-library-modal">
          <div className="design-list-tabs" role="group" aria-label="作品列表">
            <button className={!showDeleted ? "selected" : ""} onClick={() => { setShowDeleted(false); setDeleteTarget(null); }}>我的作品</button>
            <button className={showDeleted ? "selected" : ""} onClick={() => { setShowDeleted(true); setDeleteTarget(null); void loadDeletedDesigns(); }}>已删除作品</button>
          </div>
          {deleteTarget && <div className="delete-design-confirm" role="alert">
            <p>删除“{deleteTarget.name}”？删除后保留 {config?.retention_hours ?? 50} 小时，可恢复；已有下载仍绑定原版本。</p>
            <div><button className="secondary small" disabled={busy} onClick={() => setDeleteTarget(null)}>取消</button><button className="danger-button" disabled={busy} onClick={() => void deleteDesign(deleteTarget)}>确认删除</button></div>
          </div>}
          {deletedLoading && showDeleted && <p role="status">正在读取已删除作品…</p>}
          <div className="design-library">
            {(showDeleted ? deletedDesigns : designs).map((d) => (
              <div key={d.id} className="design-list-row"><button
                disabled={
                  busy || !!pending || backgroundProcessing || uploading
                }
                className={`design-list-item ${d.id === design?.id ? "selected" : ""}`}
                onClick={() => showDeleted ? void restoreDesign(d) : void switchDesign(d.id)}
                aria-label={showDeleted ? `恢复${d.name}` : undefined}
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
                {showDeleted ? <span>恢复</span> : <Icon name="arrow" />}
              </button>{!showDeleted && <button type="button" className="delete-design-button" aria-label={`删除${d.name}`} title={d.active_job_id ? "作品正在处理，完成后可删除" : `删除${d.name}`} disabled={busy || !!pending || uploading || backgroundProcessing || !!designTarget?.loading || !!d.active_job_id} onClick={() => setDeleteTarget(d)}>删除</button>}</div>
            ))}
          </div>
          {!(showDeleted ? deletedDesigns : designs).length && !deletedLoading && (
            <div className="empty-library">
              {showDeleted ? "没有可恢复的已删除作品。" : "你的第一份作品，即将从这里开始。"}
            </div>
          )}
          <div className="modal-footer">
            <span>{showDeleted ? `删除后保留 ${config?.retention_hours ?? 50} 小时，可恢复` : "作品、额度和版本均保存在服务端"}</span>
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
