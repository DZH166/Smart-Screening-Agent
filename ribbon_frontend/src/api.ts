export type User = { id: string; username: string; role: string };
export type Asset = {
  id: string;
  name: string;
  kind: "pattern" | "background";
  source: string;
  is_demo: boolean;
  shared: boolean;
  url: string;
  thumbnail_url?: string;
  derived_from?: string;
  deduplicated?: boolean;
};
export type Template = {
  id: string;
  name: string;
  version: number;
  mode: string;
  thumbnail_url: string;
  enabled: boolean;
  rules: Record<string, unknown>;
};
export type Profile = {
  id: string;
  version: number;
  name: string;
  is_demo: boolean;
  width?: number;
  height?: number;
  dpi?: number;
};
export type Config = {
  provider: string;
  ai_ready: boolean;
  ai_draft_available?: boolean;
  auth_mode?: string;
  output_profile: Profile;
  max_refinements: number;
  retention_hours?: number;
  editing?: Editing;
};
export type Editing = {
  allowed_operations: string[];
  allowed_parameters: string[];
  composite_edit: boolean;
  composite_edit_reason: string;
  planner_sees_images: boolean;
};
export type Selection = {
  asset_ids: string[];
  pattern_roles?: Record<string, PatternRole>;
  zone_background_refs?: Record<string,string>;
  border_ref?: string;
  background_id: string;
  template_id: string;
  background_tone?: "soft" | "original";
  design_density?: "airy" | "balanced" | "rich";
};
export type GenerateRequest = Selection & {
  idempotency_key: string;
  ai_assisted: boolean;
  reference_code: string | null;
};
export type Loop = {
  engine: "seamless-unit-v1" | "seamless-unit-v2" | "seamless-unit-v3";
  width: number;
  height: number;
  status: "checked" | "needs_review";
  issues: { code: string; message: string; severity: "warning" | "error" }[];
  kind: "sequence" | "panel";
  mode_notice?: string;
  motif_resolution?: { max_upscale: number; note: string };
};
export type Snapshot = {
  asset_refs: string[];
  zone_background_refs?: Record<string,string>;
  border_ref?: string;
  zone_colors?: Record<string,string>;
  pattern_slots?: string[];
  pattern_roles?: Record<string, PatternRole>;
  object_transforms?: {slot_id?: string; x:number; y:number; width:number; height:number}[];
  background_ref: string;
  template_id: string;
  template_mode: string;
  template_version: number;
  output_profile: Profile;
  output_profile_source?: Profile;
  loop?: Loop;
  params: Record<string, unknown>;
  layout_engine?: string;
  background_tone?: "soft" | "original";
  design_density?: "airy" | "balanced" | "rich";
  composite_ref?: string;
};
export type PatternRole = "main" | "support" | "accent" | "border";
export function isDirectLayoutReference(example: {available:boolean; reference_only:boolean; mode_tags:string[]; mode_notes?:Record<string,{fit:string}>}, mode:string): boolean {
  return example.available && !example.reference_only && example.mode_tags.includes(mode) && example.mode_notes?.[mode]?.fit !== "partial";
}
export const patternRoleChoices: Record<string, { value: PatternRole; label: string }[]> = {
  scene: [{value:"main",label:"主图"},{value:"support",label:"配角"},{value:"accent",label:"小点缀"}],
  scatter: [{value:"main",label:"主图"},{value:"accent",label:"小点缀"}],
  bordered: [{value:"main",label:"中间主图"},{value:"border",label:"上下边饰"}],
};

// Wire selections use current asset IDs; saved snapshots use stable slot IDs.
// Never carry a role onto a removed/replaced asset by its array position.
export function normalizedPatternRoles(ids: string[], mode: string, roles?: Record<string, PatternRole>): Record<string, PatternRole> {
  const choices = patternRoleChoices[mode];
  if (!choices) return {};
  return Object.fromEntries(ids.map((id, index) => [id,
    choices.some(choice => choice.value === roles?.[id]) ? roles![id] :
      mode === "scene" && index > 0 ? "support" : "main",
  ]));
}
export function snapshotPatternRoles(snapshot: Snapshot): Record<string, PatternRole> {
  if (snapshot.layout_engine !== "seamless-unit-v3") return {};
  const byAsset: Record<string, PatternRole> = {};
  snapshot.asset_refs.forEach((id, index) => {
    const role = snapshot.pattern_roles?.[snapshot.pattern_slots?.[index] || ""];
    if (role) byAsset[id] = role;
  });
  return normalizedPatternRoles(snapshot.asset_refs, snapshot.template_mode, byAsset);
}
export type Version = {
  id: string;
  design_id: string;
  parent_version_id: string | null;
  sequence: number;
  prompt: string;
  render_kind: string;
  snapshot: Snapshot;
  preview_url: string;
  view_url?: string;
  download_url: string;
  created_at: string;
  provider: string;
  editing?: Editing;
};
export type Job = {
  id: string;
  design_id: string | null;
  kind: string;
  status: string;
  phase: string;
  attempt: number;
  provider: string;
  error: string | null;
  result_version_id: string | null;
  result_asset_id: string | null;
  created_at: string;
  updated_at: string;
  needs_clarification: boolean;
};
export type Design = {
  id: string;
  name: string;
  current_version_id: string | null;
  successful_refinement_count: number;
  active_job_id: string | null;
  revision: number;
  versions: Version[];
  active_job: Job | null;
  deleted_at?: number | null;
};
export type ProviderCall = {
  id: string;
  job_id: string;
  operation: string;
  status: string;
  model?: string;
  request_id?: string;
  elapsed_ms: number;
  error?: string;
  diagnostic?: { category: string; stage: string; http_status: number | null; upstream_code: string | null };
};
export type Overview = {
  provider_calls?: ProviderCall[];
  jobs: Job[];
  templates: Template[];
  output_profiles: Profile[];
  users: User[];
};
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method))
    headers.set("X-HSD-Token", requestToken());
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  // Reads have a deadline; mutations retain unknown-result/idempotency recovery.
  const controller = ["GET", "HEAD"].includes(method) ? new AbortController() : null;
  const abort = () => controller?.abort(options.signal?.reason);
  if (options.signal?.aborted) abort();
  else options.signal?.addEventListener("abort", abort, { once: true });
  const timer = controller ? setTimeout(() => controller.abort(), 15000) : undefined;
  try {
  const response = await fetch(`/api/ribbon${path}`, {
    ...options,
    headers,
    signal: controller?.signal || options.signal,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : typeof data.error === "string" ? data.error : JSON.stringify(data.detail || data);
    } catch {
      /* keep status */
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
  } catch (error) {
    if (controller?.signal.aborted && !options.signal?.aborted)
      throw new ApiError("读取超时，请重试。后台任务不会因此重新提交。", 408);
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}
let requestToken: () => string = () => "";
export function setRequestToken(getToken: () => string) {
  requestToken = getToken;
}
export const post = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const running = (job: Job | null | undefined) =>
  !!job && ["QUEUED", "RUNNING", "RECONCILING"].includes(job.status);
export const versionName = (version: Version) =>
  version.sequence === 0 ? "首稿" : `精修 ${version.sequence}`;
export function loadLocal<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
}
export function saveLocal(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* server remains source of truth */
  }
}
