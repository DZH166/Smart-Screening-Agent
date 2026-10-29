export type User = { id: string; username: string; role: string };
export type Asset = {
  id: string;
  name: string;
  kind: "pattern" | "background";
  source: string;
  is_demo: boolean;
  shared: boolean;
  url: string;
  derived_from?: string;
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
  auth_mode: string;
  output_profile: Profile;
  max_refinements: number;
  retention_hours?: number;
};
export type Selection = {
  asset_ids: string[];
  background_id: string;
  template_id: string;
};
export type Snapshot = {
  asset_refs: string[];
  background_ref: string;
  template_id: string;
  template_mode: string;
  template_version: number;
  output_profile: Profile;
  params: Record<string, unknown>;
  composite_ref?: string;
};
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
};
export type Overview = {
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
  const response = await fetch(`/api/ribbon${path}`, {
    ...options,
    headers,
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
  return response.json() as Promise<T>;
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
