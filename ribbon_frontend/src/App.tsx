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
  type Candidate,
  type DesignStyle,
  type GenerateRequest,
  type Job,
  type Selection,
  type Template,
  type User,
  type Version,
  type PatternRole,
  patternRoleChoices,
  normalizedPatternRoles,
  snapshotPatternRoles,
  isDirectLayoutReference,
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
      </div>
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
  design_style: "classic",
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
const zoneNames: Record<string,string> = { left:"左区", center:"中区", right:"右区", top:"上区", bottom:"下区" };
const zonesByMode: Record<string,string[]> = { panels:["left","center","right"], split:["left","right"], stacked:["top","bottom"] };
const roleHints: Record<string,string> = { scene:"选择主图、配角和小点缀，按角色组成场景；完整人物和文字不拆开。", scatter:"主图错落倾斜，小点缀填入空隙；不会自动把人物缩成配饰。", bordered:"主图排在中间。需要小图沿上下边排列时，将它设为上下边饰，也可另选完整边饰条。" };
const advancedHints: Record<string,string> = { scatter:"完整图案以不同角度和大小错落分布，整个单元循环。", bordered:"中央重复主图，上下为连续边线，可选独立边饰。", panels:"左、中、右三区各自排放图案，可分别选择底纹。" };
function layoutSelectionIssue(mode: string | undefined, count: number, modern = false) {
  if (!count) return "";
  if (mode === "fullwidth" && count !== 1)
    return "整幅定位只使用 1 个完整图案，请移除多余图案。";
  if (mode === "ends_open" && count > 2)
    return "两端留白最多使用 2 个图案，请保留 1–2 个。";
  if (mode && (!modern && mode === "bordered" || ["split", "stacked"].includes(mode)) && count < 2)
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
  // These are settings for a new work, not editable capabilities of the
  // displayed historic version. Reuse its choices without downgrading the form.
  return {...value,
    background_tone:value.background_tone ?? snapshot?.background_tone ?? (version ? "original" : "soft"),
    design_density:value.design_density ?? snapshot?.design_density ?? "balanced",
    design_style:value.design_style ?? snapshot?.design_style ?? "classic",
  };
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
      <div className="loop-image"><RecoverableImage src={version.preview_url} decoding="async" alt={`${versionName(version)}的循环单元预览`} /></div>
    </div>
    {/* Keep the same URLs mounted: changing the view only changes visibility,
        never requests a new master or a separately rendered long-strip file. */}
    <div className="loop-continuity" hidden={!continuous}>
      <div className={`loop-continuity-track ${seams ? "show-seams" : ""}`}>
        {[0, 1, 2].map(index => <div className="loop-repeat" key={index}>
          <RecoverableImage src={version.preview_url} decoding="async" alt={index === 0 ? `${versionName(version)}的三次连续效果预览` : ""} />
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
    {loop.status === "needs_review" && <div className="loop-check needs-review">
      <strong>接缝提示</strong>

      {!!loop.issues?.length && <ul aria-label="循环检查提示">
        {loop.issues.map((issue, index) => <li key={`${issue.code}:${index}`} className={issue.severity}>{issue.message}</li>)}
      </ul>}
    </div>}
    {loop.mode_notice && <p className="loop-mode-notice">{loop.mode_notice}</p>}
    {!!loop.motif_resolution?.note && <p className="loop-resolution-note">{loop.motif_resolution.note}</p>}
    <details className="loop-technical-details">
      <summary>输出详情</summary>
      {loop.status==="checked" && <strong>工程循环检查通过</strong>}
      <p>下载为一个原尺寸循环单元。工程检查只核对排版和接缝，印刷效果需另行核样。</p>
      <dl>
        <div><dt>下载尺寸</dt><dd>{sizeLabel || `${loop.width}×${loop.height}px`}</dd></div>
        <div><dt>循环方式</dt><dd>{loop.kind === "panel" ? "定位区段循环" : "图案序列循环"}</dd></div>
        <div><dt>检查引擎</dt><dd>{loop.engine}</dd></div>
        {loop.rhythm && <div><dt>重复节奏</dt><dd>{loop.rhythm.repeats_to_length ? `100cm 约 ${loop.rhythm.repeats_to_length} 个单元` : `${loop.rhythm.unit_width}px 单元`}
          {loop.rhythm.size_variety > 1.05 ? ` · 尺寸差 ${loop.rhythm.size_variety}×` : " · 尺寸一致"}</dd></div>}
        {source && <div><dt>来源配置</dt><dd>{source.name}{source.width && source.height ? ` · ${source.width}×${source.height}px` : ""}</dd></div>}
      </dl>
    </details>
  </div>;
}
function RecoverableImage({src, alt, quiet, ...props}: React.ImgHTMLAttributes<HTMLImageElement> & {src:string; quiet?: boolean}) {
  const [attempt,setAttempt] = useState(0), [failed,setFailed] = useState(false), [loaded,setLoaded] = useState(false);
  useEffect(() => { setAttempt(0); setFailed(false); setLoaded(false); }, [src]);
  const actual = attempt ? src + (src.includes("?")?"&":"?") + "retry=" + attempt : src;
  const retry = () => {setFailed(false);setLoaded(false);setAttempt(a=>a+1);};
  return <>{!failed && <img {...props} src={actual} alt={alt} onLoad={()=>setLoaded(true)} onError={()=>setFailed(true)} />}
    {failed ? (quiet ? <span className="image-quiet" role="presentation" title={`${alt || "图片"}暂不可用`}><Icon name="grid" size={14} /></span> : <span className="image-recovery" role="status"><span>{alt || "图片"}加载失败</span><span role="button" tabIndex={0} className="secondary small" onClick={e=>{e.stopPropagation();retry();}} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();e.stopPropagation();retry();}}}>重新加载图片</span></span>) :
    !loaded && props.loading !== "lazy" && <span className="image-loading">图片加载中…</span>}</>;
}
type CreationDraft = {
  selection: Selection;
  backgroundPrompt: string;
  aiDraftChoice: boolean | null;
  aiDraftReference: {code:string;mode:string} | null;
};
type Pending = {
  path: string;
  body: Record<string, unknown>;
  kind: "background" | "design";
  designId?: string;
};
const phaseNames: Record<string, string> = {
  queued: "等待处理",
  planning: "正在准备设计",
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
  const [authExpired, setAuthExpired] = useState(false);
  const [authRetry, setAuthRetry] = useState(0);
  const authSequence = useRef(0);
  function loseAuthentication() {
    ++authSequence.current;
    setUser(null);
    setAuthLoading(false);
    setAuthExpired(true);
    setAuthError("登录已失效，请重新打开网站后继续。");
  }
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const sequence = ++authSequence.current;
    const controller = new AbortController();
    const stale = () => cancelled || controller.signal.aborted || sequence !== authSequence.current;
    setAuthLoading(true);
    setAuthError("");
    api<User>("/auth/me", { signal: controller.signal })
      .then((value) => { if (!stale()) { setUser(value); setAuthExpired(false); } })
      .catch((error) => {
        if (stale()) return;
        // A failed read does not invalidate an established employee session or
        // discard their in-flight work. Only an authentication rejection does.
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          setAuthExpired(true);
        }
        setAuthError(message(error));
      })
      .finally(() => { if (!stale()) setAuthLoading(false); });
    return () => { cancelled = true; controller.abort(); };
  }, [active, view, authRetry]);
  return <>
    {authLoading && !user && <div className="page-loader"><span className="spinner" /><span>正在连接丝带设计…</span></div>}
    {!authLoading && !user && <div className="notice error" role="alert"><strong>丝带设计暂时无法打开</strong><p>{authError || "连接暂时中断，请重试。"}</p><button type="button" onClick={() => authExpired ? location.reload() : setAuthRetry(value => value + 1)}>{authExpired ? "重新登录" : "重新连接"}</button></div>}
    {user && authError && <div className="notice error" role="alert"><strong>连接暂时中断，已保留当前作品。</strong><p>{authError}</p><button type="button" onClick={() => setAuthRetry(value => value + 1)} disabled={authLoading}>重新连接</button></div>}
    {user && <Workspace key={user.id} user={user} active={active && !authLoading} view={view} onLogout={loseAuthentication} />}
  </>;
}

function Workspace({ user, onLogout, active, view }: WorkspaceProps & { user: User; onLogout: () => void }) {
  const prefix = `ribbon:${user.id}:`;
  const [creationUncertain,setCreationUncertain] = useState(() => loadLocal<boolean>(prefix + "creationUncertain",false) === true);
  const [savedCreation] = useState<CreationDraft | null>(() => creationUncertain ? loadLocal(prefix + "creationDraft",null) : null);
  const creationGate = useRef(creationUncertain), creationDraft = useRef(savedCreation);
  const [initRetry,setInitRetry] = useState(0);
  const [initError,setInitError] = useState("");
  const [listLoading,setListLoading] = useState(false);
  const [listError,setListError] = useState("");
  const listAbort = useRef<AbortController|null>(null);
  const [config, setConfig] = useState<Config | null>(null),
    [assets, setAssets] = useState<Asset[]>([]),
    [templates, setTemplates] = useState<Template[]>([]),
    [styles, setStyles] = useState<DesignStyle[]>([{ id: "classic", label: "经典等距", hint: "保持原有节奏" }]),
    [candidates, setCandidates] = useState<Candidate[] | null>(null),
    [trialStyles, setTrialStyles] = useState<string[]>(() => {
      const saved = loadLocal<string[]>(prefix + "trialStyles", []);
      const valid = saved.filter((id) => typeof id === "string");
      return valid.length >= 2 ? valid.slice(0, 3) : ["classic", "hierarchy", "airy"];
    }),
    [candidateBusy, setCandidateBusy] = useState(false),
    [candidateError, setCandidateError] = useState(""),
    [candidateQueue, setCandidateQueue] = useState<string[]>([]),
    [candidateDone, setCandidateDone] = useState(0),
    [designs, setDesigns] = useState<Design[]>([]);
  const [design, setDesign] = useState<Design | null>(null),
    [selection, setSelection] = useState<Selection>(savedCreation?.selection || emptySelection),
    [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  // A ribbon is a very wide strip: "detail" shows it at a readable height and
  // scrolls sideways, "fit" shows the whole length at once.
  const [previewZoom, setPreviewZoom] = useState<"detail" | "fit">("detail");
  const [backgroundPrompt, setBackgroundPrompt] = useState(savedCreation?.backgroundPrompt || ""),
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
  const [libraryRole,setLibraryRole] = useState("");
  useEffect(() => { if (modal !== "pattern" && modal !== "background") setLibraryRole(""); }, [modal]);
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
  const [aiDraftChoice, setAiDraftChoice] = useState<boolean | null>(savedCreation?.aiDraftChoice ?? null);
  const [aiDraftReference, setAiDraftReference] = useState<{ code: string; mode: string } | null>(savedCreation?.aiDraftReference || null);
  useEffect(() => {
    if (!creationUncertain || loading || designTarget) return;
    const value = {selection,backgroundPrompt,aiDraftChoice,aiDraftReference};
    creationDraft.current = value;
    saveLocal(prefix + "creationDraft",value);
  }, [creationUncertain,selection,backgroundPrompt,aiDraftChoice,aiDraftReference,loading,designTarget]);
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
    deletedAbort = useRef<AbortController | null>(null),
    candidateAbort = useRef<AbortController | null>(null),
    candidateSequence = useRef(0),
    candidateScopeRef = useRef("");
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      uploadAbort.current?.abort();
      designAbort.current?.abort();
      deletedAbort.current?.abort();
      listAbort.current?.abort();
      candidateAbort.current?.abort();
      ++candidateSequence.current;
    };
  }, []);
  const isAdmin = user.role === "admin",
    current = design?.versions?.find((v) => v.id === design.current_version_id),
    selected =
      design?.versions?.find((v) => v.id === selectedVersionId) || current;
  const processing = !!design?.active_job_id || running(job),
    backgroundProcessing = running(backgroundJob),
    locked = busy || processing || !!pending || uploading || !!designTarget;
  const isHistory = !!selected && selected.id !== design?.current_version_id;
  const shownProfile = selected?.snapshot?.output_profile;
  const selectedLoop = ["seamless-unit-v1","seamless-unit-v2","seamless-unit-v3"].includes(selected?.snapshot.loop?.engine || "");
  // Settings and trials prepare a new work using the current engine/profile.
  // Saved previews and version downloads keep their immutable old snapshots.
  const modern = true;
  const roleLayout = true;
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
  const zones = modern ? zonesByMode[template?.mode || ""] || [] : [];
  const roleChoices = roleLayout ? patternRoleChoices[template?.mode || ""] : undefined;
  const roles = roleChoices ? normalizedPatternRoles(selection.asset_ids, template?.mode || "", selection.pattern_roles) : {};
  const layoutIssue = layoutSelectionIssue(template?.mode, selection.asset_ids.length, modern) ||
    (roleChoices && selection.asset_ids.length > 0 && !Object.values(roles).includes("main") ? "至少保留一个主图，再安排配角、点缀或边饰。" : "");
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
      (current.snapshot.design_style || "classic") !== (selection.design_style || "classic") ||
      (roleLayout && JSON.stringify(snapshotPatternRoles(current.snapshot)) !== JSON.stringify(roles)) ||
      (current.snapshot.border_ref || "") !== (selection.border_ref || "") ||
      zones.some(key=>current.snapshot.zone_background_refs?.[key] !== selection.zone_background_refs?.[key]) ||
      (current.snapshot.background_tone || "original") !== (selection.background_tone || "original") ||
      (current.snapshot.design_density || "balanced") !== (selection.design_density || "balanced"));
  const candidateScope = JSON.stringify([design?.id, current?.id, selection, trialStyles, active, view]);
  candidateScopeRef.current = candidateScope;
  useEffect(() => {
    cancelCandidatePreview();
    return () => {
      ++candidateSequence.current;
      candidateAbort.current?.abort();
    };
  }, [candidateScope]);
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
  const aiDraftEnabled = aiDraftAvailable && aiDraftChoice !== false;
  const draftReference = aiDraftEnabled && aiDraftReference?.mode === template?.mode ? aiDraftReference : null;
  function templateImage(t: Template) {
    return modern && t.id === t.mode && t.version===1 ? `/static/ribbon/${roleLayout ? "layout-v3" : "layout-v2"}/${t.mode}.webp` : t.thumbnail_url;
  }
  function templateOption(t: Template) {
    return (
      <div key={t.id} className="template-option">
        <button
          className={`template-card ${selection.template_id === t.id ? "selected" : ""}`}
          disabled={locked}
          aria-pressed={selection.template_id === t.id}
          onClick={() => updateSelection({ ...selection, template_id: t.id })}
        >
          <RecoverableImage src={templateImage(t)} alt={`${t.name}样式图`} loading="lazy" decoding="async" quiet />
          <span>{t.name}{selection.template_id === t.id && <Icon name="check" size={14} />}</span>
        </button>
        {selection.template_id === t.id && (
          <button
            type="button"
            className="template-example-button"
            aria-label={`查看${t.name}案例`}
            onClick={() => { setModal(null); setExamplesView({ mode: t.mode, name: t.name }); }}
          >查看案例</button>
        )}
      </div>
    );
  }

  function updateSelection(value: Selection) {
    cancelCandidatePreview();
    if (value.template_id !== selection.template_id) {
      setAiDraftReference(null);
      delete value.zone_background_refs;
      delete value.border_ref;
      delete value.pattern_roles;
    }
    const nextMode = templates.find(t => t.id === value.template_id)?.mode || "";
    if (roleLayout && patternRoleChoices[nextMode]) value.pattern_roles = normalizedPatternRoles(value.asset_ids, nextMode, value.pattern_roles);
    else delete value.pattern_roles;
    setSelection(value);
    saveLocal(prefix + "selection", {
      design_id: designRef.current?.id || null,
      base_version_id: designRef.current?.current_version_id || null,
      value,
    });
  }
  function applyDesign(d: Design, force = false) {
    const changedVersion = lastVersion.current !== d.current_version_id;
    if (force || changedVersion || designRef.current?.id !== d.id) cancelCandidatePreview();
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
        creationGate.current && creationDraft.current ? creationDraft.current.selection :
        force &&
        saved?.design_id === d.id &&
        saved.base_version_id === d.current_version_id
          ? saved.value
          : v
            ? {
                asset_ids: v.snapshot.asset_refs,
                background_id: v.snapshot.background_ref,
                template_id: v.snapshot.template_id,
                zone_background_refs: v.snapshot.zone_background_refs, border_ref:v.snapshot.border_ref,
                ...(v.snapshot.layout_engine === "seamless-unit-v3" ? {pattern_roles:snapshotPatternRoles(v.snapshot)} : {}),
                background_tone: v.snapshot.background_tone || "original",
                design_style: v.snapshot.design_style || "classic",
                ...(["design-rhythm-v1", "design-rhythm-v2", "seamless-unit-v1", "seamless-unit-v2", "seamless-unit-v3"].includes(v.snapshot.layout_engine || "") ? {design_density: v.snapshot.design_density || "balanced"} : {}),
              }
            : emptySelection;
      setSelection(restoreSelection(next, v));
      setSelectedVersionId(d.current_version_id);
      lastVersion.current = d.current_version_id;
    }
    if (d.active_job) setJob(d.active_job);
  }
  function toggleTrialStyle(id: string) {
    const picked = trialStyles.includes(id);
    if (picked && trialStyles.length <= 2) return; // 至少保留两种风格对比
    const next = picked ? trialStyles.filter((item) => item !== id) : [...trialStyles, id];
    if (next.length > 3) return;
    cancelCandidatePreview();
    setTrialStyles(next);
    saveLocal(prefix + "trialStyles", next);
  }

  function cancelCandidatePreview() {
    ++candidateSequence.current;
    candidateAbort.current?.abort();
    candidateAbort.current = null;
    setCandidateBusy(false);
    setCandidateQueue([]);
    setCandidateDone(0);
    setCandidateError("");
    setCandidates(null);
  }

  async function previewCandidates() {
    if (candidateAbort.current || locked || !active || view !== "ribbon") return;
    if (!selection.asset_ids.length || !selection.background_id || !selection.template_id) {
      setCandidateError("先选择图案、底纹和排版");
      return;
    }
    if (trialStyles.length < 2) {
      setCandidateError("至少选择两种风格来对比");
      return;
    }
    const queue = [...trialStyles];
    const controller = new AbortController();
    const sequence = ++candidateSequence.current;
    const scope = candidateScopeRef.current;
    candidateAbort.current = controller;
    const stale = () => !mounted.current || controller.signal.aborted ||
      sequence !== candidateSequence.current || scope !== candidateScopeRef.current;
    setCandidateBusy(true);
    setCandidateError("");
    setCandidates([]);
    setCandidateQueue(queue);
    setCandidateDone(0);
    // One style per request keeps the server responsive and lets the gallery
    // fill in order instead of waiting for the slowest render.
    try {
      for (const style of queue) {
        if (stale()) return;
        try {
          const endpoint = "/candidates/one";
          const row = await api<Candidate>(endpoint, {
            method: "POST", signal: controller.signal,
            body: JSON.stringify({ ...selection, pattern_roles: roleChoices ? roles : undefined, style }),
          });
          if (stale()) return;
          if (row.style !== style) throw new ApiError("试排结果与所选风格不一致，请重新试排。", 409);
          setCandidates((list) => [...(list || []), row]);
        } catch (error) {
          if (stale()) return;
          if (error instanceof ApiError && error.status === 401) { onLogout(); return; }
          setCandidateError(message(error));
        }
        if (!stale()) setCandidateDone((done) => done + 1);
      }
    } finally {
      if (!stale()) {
        candidateAbort.current = null;
        setCandidateBusy(false);
        setCandidateQueue([]);
      }
    }
  }

  async function loadCatalog() {
    const [a, t, c, s] = await Promise.all([
      api<Asset[]>("/assets"),
      api<Template[]>("/templates"),
      api<Config>("/config"),
      api<DesignStyle[]>("/design-styles"),
    ]);
    setAssets(a);
    setTemplates(t);
    setConfig(c);
    if (s.length) setStyles(s);
  }
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    async function init() {
      setLoading(true); setInitError("");
      try {
        const results = await Promise.allSettled([
          api<Asset[]>("/assets", {signal:controller.signal}),
          api<Template[]>("/templates", {signal:controller.signal}),
          api<Config>("/config", {signal:controller.signal}),
          api<Design[]>("/designs?summary=true", {signal:controller.signal}),
          api<DesignStyle[]>("/design-styles", {signal:controller.signal}),
        ] as const);
        if (cancelled) return;
        const [ar,tr,cr,dr,sr] = results;
        if (ar.status==="fulfilled") setAssets(ar.value);
        if (tr.status==="fulfilled") setTemplates(tr.value);
        if (cr.status==="fulfilled") setConfig(cr.value);
        if (dr.status==="fulfilled") setDesigns(dr.value);
        if (sr.status==="fulfilled" && sr.value.length) setStyles(sr.value);
        const failure=results.find(r=>r.status==="rejected");
        if (failure?.status==="rejected") throw failure.reason;
        const a=ar.status==="fulfilled"?ar.value:[], t=tr.status==="fulfilled"?tr.value:[], list=dr.status==="fulfilled"?dr.value:[];
        const savedId = loadLocal<string | null>(prefix + "design", null);
        // An unknown create cannot be claimed by taking the newest list row.
        const id = list.find((x) => x.id === savedId)?.id || (!creationGate.current ? list[0]?.id : undefined);
        if (id) {
          const d = await api<Design>(`/designs/${id}`, {signal:controller.signal});
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
          setSelection(restoreSelection(creationGate.current && creationDraft.current ? creationDraft.current.selection : saved?.value || recommendedSelection(a, t)));
        }
        const bgId = loadLocal<string | null>(prefix + "backgroundJob", null);
        if (bgId) {
          const bg = await api<Job>(`/jobs/${bgId}`, {signal:controller.signal});
          if (!cancelled) setBackgroundJob(bg);
        }
      } catch (e) {
        if (!cancelled) {
          setInitError(message(e));
          if (e instanceof ApiError && e.status === 401) onLogout();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void init();
    return () => { cancelled = true; controller.abort(); };
  }, [initRetry]);

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
        if (offline && !design?.id && !running(backgroundJob))
          await api<Config>("/config", { signal: controller.signal });
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
                  "此次处理未完成，已保存的版本仍可下载。",
                type: "error",
              });
          }
        }
        if (backgroundJob && running(backgroundJob)) {
          const updated = await api<Job>(`/jobs/${backgroundJob.id}`, { signal: controller.signal });
          if (stale()) return;
          setBackgroundJob(updated);
          if (updated.status === "FAILED") {
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
    if (!offline) void tick();
    const timer = processing || backgroundProcessing || offline
      ? window.setInterval(tick, offline && !processing && !backgroundProcessing ? 2500 : 1200) : undefined;
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
    offline,
    design?.id,
    design?.active_job_id,
    backgroundJob?.id,
    backgroundJob?.status,
    job?.id,
    job?.status,
  ]);

  // Refresh derived assets after a content edit; the version snapshot owns the selection.
  useEffect(() => {
    const snapshot=design?.versions.find(v=>v.id===design.current_version_id)?.snapshot;
    if (!snapshot || offline) return;
    const ids=[...snapshot.asset_refs, snapshot.background_ref, ...Object.values(snapshot.zone_background_refs||{}), ...(snapshot.border_ref?[snapshot.border_ref]:[])];
    if (ids.every(id=>assets.some(a=>a.id===id))) return;
    const controller = new AbortController();
    const sequence = designLoadSequence.current;
    void api<Asset[]>("/assets", { signal: controller.signal })
      .then(a => { if (!controller.signal.aborted && mounted.current && sequence === designLoadSequence.current) setAssets(a); })
      .catch(() => { if (!controller.signal.aborted && sequence === designLoadSequence.current) setOffline(true); });
    return () => controller.abort();
  }, [design?.current_version_id, offline]);

  // A completed background job can be recovered even after the browser was closed.
  useEffect(() => {
    if (backgroundJob?.status !== "SUCCEEDED" || !backgroundJob.result_asset_id)
      return;
    const stored = loadLocal<string | null>(prefix + "backgroundJob", null);
    if (stored !== backgroundJob.id || offline) return;
    const controller=new AbortController();
    void api<Asset[]>("/assets", {signal:controller.signal})
      .then((a) => {
        if (controller.signal.aborted || !mounted.current) return;
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
      .catch(() => {if (!controller.signal.aborted && mounted.current) setOffline(true);});
    return ()=>controller.abort();
  }, [backgroundJob?.id, backgroundJob?.status, offline]);

  async function executePending(operation: Pending) {
    const legacyRead = /\/refinements$/.test(operation.path);
    setPending(operation);
    saveLocal(prefix + "pending", operation);
    try {
      if (!legacyRead && operation.path !== "/background-jobs" &&
          !/^\/designs\/[^/]+\/generate$/.test(operation.path)) {
        setPending(null); saveLocal(prefix + "pending", null);
        throw new ApiError("这项旧提交无法继续，请刷新作品列表查看已保存结果。", 410);
      }
      // Compatibility is read-only: a stored old edit can recover an accepted
      // job, but can never send a new or repeated editing request.
      const key = operation.body.idempotency_key;
      if (legacyRead && (typeof key !== "string" || !key || !operation.designId))
        throw new ApiError("这项旧提交缺少恢复信息，请查看已保存作品。", 410);
      const result = legacyRead
        ? await api<Job>(`/jobs/by-request/${encodeURIComponent(String(key))}`)
        : await post<Job>(operation.path, operation.body);
      if (legacyRead && (result.kind !== "refine" || result.design_id !== operation.designId))
        throw new ApiError("旧任务类型或作品不一致，请刷新作品列表查看。", 409);
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
        e.status !== 408 &&
        !(legacyRead && [401,403,429].includes(e.status))
      ) {
        setPending(null);
        saveLocal(prefix + "pending", null);
      }
      if (e instanceof ApiError && e.status === 401) {
        onLogout();
        return;
      }
      setNotice({
        text:
          e instanceof ApiError &&
          e.status >= 400 &&
          e.status < 500 &&
          e.status !== 408
            ? /\/refinements$/.test(operation.path) && [404,410].includes(e.status)
              ? "旧任务不存在或已过期，请查看已保存作品；需要新结果可生成新作品。"
              : message(e)
            : /\/refinements$/.test(operation.path)
              ? "暂时无法读取旧任务状态，请点击“重试读取任务”；不会重新发送图片处理。"
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
  function blockUncertainCreation() {
    const value = {selection,backgroundPrompt,aiDraftChoice,aiDraftReference};
    creationGate.current = true;
    creationDraft.current = value;
    setCreationUncertain(true);
    saveLocal(prefix + "creationDraft",value);
    saveLocal(prefix + "creationUncertain",true);
  }
  function clearCreationBlock() {
    creationGate.current = false;
    creationDraft.current = null;
    setCreationUncertain(false);
    saveLocal(prefix + "creationUncertain",null);
    saveLocal(prefix + "creationDraft",null);
  }
  async function createWork(name:string) {
    try {
      return await post<Design>("/designs",{name});
    } catch (e) {
      if (!(e instanceof ApiError) || e.status === 408 || e.status >= 500) {
        blockUncertainCreation();
        throw new Error("作品建立结果尚未确认。请从“我的作品”刷新后选择要继续的作品，暂不重复创建。");
      }
      // Definite authentication or input rejection never claims acceptance.
      throw e;
    }
  }
  async function generate() {
    if (creationGate.current || locked || !ready) return;
    // Capture choices before selecting the newly created, initially empty work.
    // Never write a new first draft into a saved work or a historical version.
    const chosen = structuredClone({...selection, pattern_roles: roleChoices ? roles : undefined});
    const request: GenerateRequest = {idempotency_key: crypto.randomUUID(), ...chosen,
      ai_assisted: aiDraftEnabled, reference_code: draftReference?.code || null};
    await action(async () => {
      let d = design;
      if (!d || d.current_version_id || d.versions?.length) {
        d = await createWork(`丝带设计 ${new Date().toLocaleDateString("zh-CN")}`);
        lastVersion.current = null;
        applyDesign(d, true);
        setSelection(chosen);
        saveLocal(prefix + "selection", {design_id:d.id, base_version_id:null, value:chosen});
        setJob(null);
      }
      await executePending({
        path: `/designs/${d.id}/generate`, body: request,
        kind: "design", designId: d.id,
      });
    });
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
        text: "已返回上一保存版本。",
        type: "success",
      });
    });
  }
  async function newDesign() {
    if (creationGate.current || busy || pending || backgroundProcessing || uploading) return;
    cancelCandidatePreview();
    ++designLoadSequence.current;
    designAbort.current?.abort();
    setDesignTarget(null);
    await action(async () => {
      const d = await createWork(`丝带设计 ${designs.length + 1}`);
      setAiDraftChoice(null);
      setAiDraftReference(null);
      lastVersion.current = null;
      applyDesign(d, true);
      updateSelection(recommendedSelection(assets, templates));
      setJob(null);
      setNotice(null);
      setModal(null);
    });
  }
  async function switchDesign(id: string) {
    if (busy || pending || backgroundProcessing || uploading) return;
    const uncertainDraft = creationGate.current ? creationDraft.current : null;
    cancelCandidatePreview();
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
    setAiDraftChoice(null);
    setAiDraftReference(null);
    setNotice(null);
    setModal(null);
    try {
      const d = await api<Design>(`/designs/${id}`, { signal: controller.signal });
      if (!mounted.current || sequence !== designLoadSequence.current || controller.signal.aborted) return;
      // Only an explicit, successfully loaded work resolves unknown creation.
      // Keep the employee's choices when they select the new empty work.
      if (creationGate.current) clearCreationBlock();
      applyDesign(d, true);
      if (uncertainDraft && !d.current_version_id && !d.versions?.length) {
        const chosen = restoreSelection(uncertainDraft.selection);
        setSelection(chosen);
        setBackgroundPrompt(uncertainDraft.backgroundPrompt);
        setAiDraftChoice(uncertainDraft.aiDraftChoice);
        setAiDraftReference(uncertainDraft.aiDraftReference);
        saveLocal(prefix + "selection",{design_id:d.id,base_version_id:null,value:chosen});
      }
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
  async function openDesigns() {
    setModal("designs"); setShowDeleted(false); setDeleteTarget(null); setListError("");
    listAbort.current?.abort();
    const controller=new AbortController(); listAbort.current=controller; setListLoading(true);
    try {
      const list=await api<Design[]>("/designs?summary=true",{signal:controller.signal});
      if (!controller.signal.aborted && mounted.current) setDesigns(list);
    } catch(e) {
      if (!controller.signal.aborted && mounted.current) setListError(message(e));
    } finally {
      if (!controller.signal.aborted && mounted.current) setListLoading(false);
    }
  }
  async function loadDeletedDesigns() {
    deletedAbort.current?.abort();
    const controller = new AbortController();
    deletedAbort.current = controller;
    setDeletedLoading(true);
    try {
      const list = await api<Design[]>("/designs?deleted=true&summary=true", { signal: controller.signal });
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
          setAiDraftChoice(null);
        setAiDraftReference(null);
        setSelection(recommendedSelection(assets, templates));
        saveLocal(prefix + "design", null);
        saveLocal(prefix + "selection", null);
      }
      setDeleteTarget(null);
      setNotice({ text: `作品已删除，可在“已删除作品”中恢复；保留 ${config?.retention_hours ?? 50} 小时。`, type: "success" });
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
      setNotice({ text: "作品已恢复，原有版本仍可查看和下载。", type: "success" });
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
        background_id: selection.background_id === asset.id ? "" : selection.background_id,
        border_ref: selection.border_ref === asset.id ? undefined : selection.border_ref,
        zone_background_refs: selection.zone_background_refs && Object.fromEntries(
          Object.entries(selection.zone_background_refs).filter(([,id])=>id!==asset.id)) ,
      });
    });
  }
  const status = designTarget ? designTarget.loading ? "正在打开作品" : "作品打开失败" : processing
    ? phaseNames[job?.phase || ""] ||
      job?.phase ||
      phaseNames[job?.status || ""] ||
      "正在处理"
    : current
      ? "已保存"
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
          <button
            className="secondary"
            disabled={creationUncertain || busy || !!pending || backgroundProcessing || uploading}
            onClick={() => void newDesign()}
          >
            <Icon name="plus" />
            新建作品
          </button>
          <button className="text-button" onClick={() => void openDesigns()}>
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
        {config && (testMode || !aiAvailable || config.output_profile?.is_demo) && <div className="environment-strip compact-status">
          {testMode && <span className={current ? undefined : "test-limit"}>测试模型 · 演示模式（测试替身）</span>}
          {config.output_profile?.is_demo && <span>演示输出 · 未经业务验收</span>}
          {!aiAvailable && <span>AI 尚未配置，可用已有素材排版。</span>}
        </div>}
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
        {creationUncertain && <div className="notice error" role="alert">
          <span>作品可能已经建立，暂不重复创建。请打开“我的作品”，刷新后选择要继续的作品。</span>
          <button className="secondary small" onClick={() => void openDesigns()}>查看作品</button>
        </div>}
        {pending && (
          <div className="notice info">
            <span>{/\/refinements$/.test(pending.path) ? "有一项旧任务状态尚未读取，只会查询已受理的任务。" : "有一项提交尚未确认；恢复使用原幂等键，不会重复提交已受理的处理。"}</span>
            <button
              className="secondary small"
              disabled={busy}
              onClick={() => void action(() => executePending(pending))}
            >
              {/\/refinements$/.test(pending.path) ? "重试读取任务" : "恢复提交"}
            </button>
          </div>
        )}
        {initError && <div className="notice error" role="alert"><span>工作台读取未完成：{initError}</span><button className="secondary small" onClick={()=>setInitRetry(n=>n+1)}>重新读取工作台</button></div>}
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
                  <h2>素材与排版</h2>
                  <p className="panel-sub">选择完成后生成，试排可预览当前设置</p>
                </div>
              </div>
              <section className="source-section">
                <div className="section-label">
                  <h3><span className="step-index">1</span>图案</h3>
                  <span className="section-meta">{selection.asset_ids.length ? `已选 ${selection.asset_ids.length}` : "未选"}</span>
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
                  <div className={`selected-patterns${roleChoices ? " has-pattern-roles" : ""}`}>
                    {selectedPatterns.map((a, index) => (
                      <div className="pattern-tile" key={a.id}>
                        <div className="checker">
                          <RecoverableImage src={a.thumbnail_url || a.url} alt={a.name} decoding="async" />
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
                        {roleChoices && <select className="pattern-role" aria-label={`图案 ${index + 1} 的排版角色`} value={roles[a.id]} disabled={locked}
                          onChange={event => updateSelection({...selection, pattern_roles:{...roles,[a.id]:event.target.value as PatternRole}})}>
                          {roleChoices.map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
                        </select>}
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
                    <span>从素材库选择，或上传图案</span>
                    <small>支持透明 PNG</small>
                  </button>
                )}
              </section>
              <section className="source-section">
                <div className="section-label">
                  <h3><span className="step-index">2</span>排版</h3>
                  <button type="button" className="quiet-link" onClick={() => setExamplesView({ mode: null, name: "全部排版案例" })}>全部案例</button>
                </div>
                {template && !basicLayoutModes.has(template.mode) && <div className="chosen-layout">
                  <strong>已选：{template.name}</strong>
                  <button type="button" className="quiet-link" onClick={() => setExamplesView({ mode: template.mode, name: template.name })}>查看案例</button>
                </div>}
                {layoutIssue && <p className="layout-selection-issue" id="ribbon-layout-issue" role="alert">{layoutIssue}</p>}
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
                {template && ((modern && advancedHints[template.mode]) || layoutHints[template.mode]) && (
                  <details className="layout-help">
                    <summary>这个排法怎么排</summary>
                    <p>{roleLayout && roleHints[template.mode] || modern && advancedHints[template.mode] || layoutHints[template.mode]}</p>
                  </details>
                )}

                  <label className="inline-field">画面密度
                    <select aria-label="画面密度" value={selection.design_density || "balanced"} disabled={locked}
                      onChange={(event) => updateSelection({ ...selection, design_density: event.target.value as Selection["design_density"] })}>
                      <option value="airy">疏朗</option>
                      <option value="balanced">均衡</option>
                      <option value="rich">饱满</option>
                    </select>
                  </label>
                {modern && <div className="style-control" role="group" aria-label="设计风格">
                  <span className="field-label">设计风格</span>
                  <div className="style-chips">
                    {styles.map((style) => (
                      <button key={style.id} type="button" disabled={locked}
                        className={`style-chip ${(selection.design_style || "classic") === style.id ? "selected" : ""}`}
                        aria-pressed={(selection.design_style || "classic") === style.id}
                        title={style.hint}
                        onClick={() => updateSelection({ ...selection, design_style: style.id })}>
                        {style.label}
                      </button>
                    ))}
                  </div>
                  {!!styles.find((s) => s.id === (selection.design_style || "classic"))?.hint && (
                    <p className="style-hint">{styles.find((s) => s.id === (selection.design_style || "classic"))?.hint}</p>
                  )}
                </div>}
                {modern && <details className="trial-box" open={!!candidates || candidateBusy}>
                  <summary>
                    <span>试排对比</span>
                    <small>选 2–3 种风格，本地预览，不调用AI</small>
                  </summary>
                  <div className="trial-body">
                    <div className="trial-chips" role="group" aria-label="试排风格">
                      {styles.map((style) => {
                        const picked = trialStyles.includes(style.id);
                        return (
                          <button key={style.id} type="button" disabled={locked || candidateBusy}
                            className={`trial-chip ${picked ? "selected" : ""}`}
                            aria-pressed={picked}
                            onClick={() => toggleTrialStyle(style.id)}>
                            <span className="trial-check" aria-hidden="true">{picked ? "✓" : ""}</span>
                            {style.label}
                          </button>
                        );
                      })}
                    </div>
                    <button type="button" className="primary small" disabled={locked || candidateBusy}
                      onClick={() => void previewCandidates()}>
                      {candidateBusy ? `正在试排 ${candidateDone}/${candidateQueue.length}` : `试排这 ${trialStyles.length} 种风格`}
                    </button>
                    {candidateBusy && (
                      <div className="trial-progress" role="progressbar"
                        aria-valuemin={0} aria-valuemax={candidateQueue.length} aria-valuenow={candidateDone}>
                        <span style={{ width: `${candidateQueue.length ? (candidateDone / candidateQueue.length) * 100 : 0}%` }} />
                      </div>
                    )}
                    {candidateError && <p className="style-hint" role="alert">{candidateError}</p>}
                  </div>
                </details>}
                {!!candidates && <div className="candidate-gallery" aria-label="风格试排">
                  {candidateQueue.filter((style) => !candidates.some((row) => row.style === style)).map((style) => (
                    <figure key={`pending-${style}`} className="candidate-card is-pending" aria-busy="true">
                      <div className="candidate-skeleton"><span className="spinner tiny" /></div>
                      <figcaption>
                        <strong>{styles.find((s) => s.id === style)?.label || style}</strong>
                        <span>正在本地渲染…</span>
                      </figcaption>
                    </figure>
                  ))}
                  {candidates.map((candidate) => (
                    <figure key={candidate.style} className={`candidate-card ${(selection.design_style || "classic") === candidate.style ? "selected" : ""}`}>
                      <img src={candidate.image} alt={`${candidate.label}试排`} />
                      <figcaption>
                        <strong>{candidate.label}</strong>
                        <span>{candidate.rhythm?.repeats_to_length ? `100cm 约 ${candidate.rhythm.repeats_to_length} 个单元` : `${candidate.width}px 单元`}</span>
                        <button type="button" className="secondary small" disabled={locked}
                          onClick={() => { updateSelection({ ...selection, design_style: candidate.style }); setCandidates(null); }}>
                          用这个风格
                        </button>
                      </figcaption>
                    </figure>
                  ))}
                  <button type="button" className="quiet-link close-trial" onClick={cancelCandidatePreview}>收起试排</button>
                </div>}
              </section>
              {modern && (zones.length>0 || template?.mode==="bordered") && <details className="optional-layers" key={template?.mode}>
                <summary>{zones.length ? "分区底纹" : "独立边饰"}</summary>
                {(zones.length ? zones : ["border"]).map(key=>{
                  const ref=key==="border"? selection.border_ref : selection.zone_background_refs?.[key];
                  return <div key={key}><span>{zoneNames[key] || "上下边饰"}</span><button aria-label={key==="border"?"选择上下边饰":`选择${zoneNames[key]}底纹`} disabled={locked} className="secondary small" onClick={()=>{
                    setLibraryRole(key);setSearch("");setModal(key==="border"?"pattern":"background");
                  }}>{(ref && assetIndex.get(ref)?.name) || (key==="border"?"选择边饰":"选择底纹")}</button>{ref && <button disabled={locked} className="text-button" onClick={()=>{
                    const next={...selection,zone_background_refs:{...selection.zone_background_refs}};
                    if(key==="border") delete next.border_ref;else delete next.zone_background_refs[key];updateSelection(next);
                  }}>恢复默认</button>}</div>;
                })}
              </details>}
              <section className="source-section">
                <div className="section-label">
                  <h3><span className="step-index">3</span>底图</h3>
                  {background?.is_demo && <span className="section-meta">演示素材</span>}
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
                <details className="background-prompt-box">
                  <summary>写一句底图要求<small>可不填</small></summary>
                  <textarea
                    id="background-prompt"
                    className="background-prompt"
                    value={backgroundPrompt}
                    onChange={(event) => setBackgroundPrompt(event.target.value)}
                    maxLength={2000}
                    rows={2}
                    disabled={locked || backgroundProcessing || !aiAvailable}
                    placeholder="例如：浅蓝色细条纹，不要文字。"
                    aria-describedby={!aiAvailable ? "background-ai-unavailable" : undefined}
                  />
                  {!aiAvailable && <p className="model-help" id="background-ai-unavailable">AI 尚未配置，仍可从底图库选图。</p>}
                </details>
                {background ? (
                  <div className="background-selected">
                    <RecoverableImage src={background.thumbnail_url || background.url} alt="选中的底图" loading="lazy" decoding="async" />
                    <div>
                      <strong>{background.name}</strong>
                      <small>{background.source === "upload" ? "已上传" : "已选择"}</small>
                    </div>
                    <Icon name="check" size={16} />
                  </div>
                ) : (
                  <div className="empty-background">选择底图，为图案定下基调</div>
                )}
                {backgroundProcessing && (
                  <p className="microcopy">
                    {testMode ? "正在生成测试底图…" : "AI 正在生成底图…"}可离开后恢复。
                  </p>
                )}
                <label className="inline-field">底纹处理
                  <select aria-label="底纹处理" value={selection.background_tone || "soft"}
                    disabled={locked || backgroundProcessing}
                    onChange={(event) => updateSelection({ ...selection, background_tone: event.target.value as Selection["background_tone"] })}>
                    <option value="original">保持原色</option>
                    <option value="soft">柔和，突出主图</option>
                    <option value="quiet">更淡，图案为主</option>
                  </select>
                </label>
              </section>
              {current && changed && (
                <div className="selection-warning">
                  选择已更改，点击“生成新作品”保存结果。
                </div>
              )}
            </aside>
            <section className="center-column">
              <div className="panel preview-panel">
                <div className="panel-heading">
                  <div>
                    
                    <h2>{designTarget?.name || design?.name || "设计预览"}</h2>
                  </div>
                  {processing && (
                    <span className="state-pill working">
                      <span className="status-dot" />
                      {status}
                    </span>
                  )}
                </div>
                <div className="generate-area">
                  <div className="workspace-actions">
                    <button
                      className="primary generation-button"
                      disabled={creationUncertain || !ready || locked || backgroundProcessing}
                      aria-describedby={layoutIssue ? "ribbon-layout-issue" : undefined}
                      onClick={() => void generate()}
                    >
                      {processing ? (
                        <span className="spinner tiny" />
                      ) : (
                        <Icon name="spark" />
                      )}
                      {busy ? "正在提交…" : processing ? "正在生成…" : current || design?.versions?.length ? "生成新作品" : "生成首稿"}
                      <Icon name="arrow" size={16} />
                    </button>
                    {selected && (<div className="result-actions">
                      {!!current?.parent_version_id && (
                        <button
                          className="secondary"
                          disabled={locked}
                          onClick={() => void rollback()}
                        >
                          <Icon name="back" size={17} />
                          回退上一版
                        </button>
                      )}
                      <a
                        className="secondary"
                        href={selected.download_url}
                        download
                      >
                        <Icon name="download" size={17} />
                        {isHistory ? "下载所选版本" : selectedLoop ? "下载循环单元" : "下载当前图"}
                      </a>
                    </div>)}
                  </div>
                    {!designTarget && aiDraftAvailable && <div className="ai-draft-options">
                      <label>
                        <input type="checkbox" checked={aiDraftEnabled} disabled={locked || backgroundProcessing}
                          onChange={event => { setAiDraftChoice(event.target.checked); if (!event.target.checked) setAiDraftReference(null); }} />
                        AI搭配底纹与装饰
                      </label>
                      {aiDraftEnabled ? <>
                        <p>按原图保留人物文字。选择的案例会发送给Seedream。</p>
                        {draftReference ? <div className="ai-draft-reference"><span>参考案例：<strong>{draftReference.code}</strong></span><button type="button" disabled={locked} onClick={() => setAiDraftReference(null)}>取消案例参考</button></div> :
                          <button type="button" className="ai-reference-picker" disabled={locked || !template} onClick={() => setExamplesView({ mode: template?.mode || null, name: template?.name || "全部排版案例" })}>选择案例参考</button>}
                      </> : <p>按原素材直接排版，不调用AI搭配。</p>}
                    </div>}
                    <small>
                      {!selection.asset_ids.length
                        ? "请先选择至少一个图案"
                        : !selection.template_id
                          ? "请选择一种排版模式"
                          : !selection.background_id
                            ? "请选择或生成底图"
                            : layoutIssue || (current ? "按当前选择生成独立作品。" : "按当前选择生成作品")}
                    </small>
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
                  {designTarget ? (
                    <div className="empty-canvas design-loading" role="status" aria-live="polite">
                      {designTarget.loading ? <><span className="spinner" /><h3>正在打开作品…</h3><p>正在读取所选作品的版本和素材。</p></> : <><h3>作品打开失败</h3><p>请重试，或从“我的作品”选择其他作品。</p><button className="secondary" onClick={() => void switchDesign(designTarget.id)}>重试打开作品</button></>}
                    </div>
                  ) : selected && selectedLoop ? (
                    <LoopPreview key={`${design?.id}:${selected.id}`} version={selected} sizeLabel={sizeLabel} />
                  ) : selected ? (
                    <>
                      <div className={`ribbon-display ${previewZoom}`}>
                        <RecoverableImage
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
                      <h3>首稿预览</h3>
                      {template && (
                        <div className="template-peek">
                          <RecoverableImage
                            src={templateImage(template)}
                            alt="当前排版参考"
                            quiet
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
                </div>
                {selected ? (
                  <>
                    {(isHistory || selected.provider==="test") && <div className="preview-caption"><span>{isHistory ? "正在查看历史保存版本" : "测试模式结果"}</span></div>}
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
              {!!design?.versions?.length && <details className="panel history-panel" key={design.id}>
                <summary className="history-heading">版本记录（{design.versions.length}）</summary>
                {design?.versions?.length ? (
                  <div className="version-grid">
                    {design.versions.map((v) => (
                      <button
                        key={v.id}
                        className={`version-card ${v.id === selected?.id ? "selected" : ""}`}
                        onClick={() => setSelectedVersionId(v.id)}
                        aria-pressed={v.id === selected?.id}
                      >
                        <RecoverableImage
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
              </details>}
            </section>
          </div>
        )}
        <footer className="page-footer">
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
            legacyLayout={!roleLayout}
            onChooseReference={aiDraftEnabled && !locked && !backgroundProcessing ? example => {
              if (!template || !isDirectLayoutReference(example, template.mode)) return;
              setAiDraftReference({ code: example.code, mode: template.mode });
              setExamplesView(null);
            } : undefined}
          />
        </Modal>
      )}
      {(modal === "pattern" || modal === "background") && (
        <Modal
          title={libraryRole==="border" ? "选择边饰" : libraryRole ? zoneNames[libraryRole]+"底纹" : modal === "pattern" ? "图案素材库" : "底图素材库"}
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
            {!libraryRole && <label
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
            </label>}
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
              const picked = libraryRole ? (libraryRole==="border" ? selection.border_ref : selection.zone_background_refs?.[libraryRole])===a.id :
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
                      libraryRole === "border" ? updateSelection({...selection,border_ref:a.id}) :
                      libraryRole ? updateSelection({...selection,zone_background_refs:{...selection.zone_background_refs,[libraryRole]:a.id}}) :
                      modal === "pattern"
                        ? togglePattern(a.id)
                        : updateSelection({ ...selection, background_id: a.id })
                    }
                  >
                    <div
                      className={`library-image ${modal === "pattern" ? "checker" : ""}`}
                    >
                      <RecoverableImage src={a.thumbnail_url || a.url} alt={a.name} loading="lazy" decoding="async" />
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
              {libraryRole ? (libraryRole==="border"?"选择一个完整边饰":"选择该区域的底纹") : modal === "pattern"
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
          {listLoading && !showDeleted && <p role="status">正在更新作品列表…</p>}
          {listError && !showDeleted && <div className="notice error" role="alert"><span>{listError}</span><button className="secondary small" onClick={()=>void openDesigns()}>重试读取作品</button></div>}
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
                    {d.current_version_id ? "已有保存版本" : "尚未生成首稿"}
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
            <span>{showDeleted ? `删除后保留 ${config?.retention_hours ?? 50} 小时，可恢复` : "作品与版本会自动保存"}</span>
            <button
              className="primary"
              disabled={creationUncertain || busy || !!pending || backgroundProcessing || uploading}
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
