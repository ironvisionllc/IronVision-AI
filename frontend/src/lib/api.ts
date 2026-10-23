import axios from "axios";

export const TOKEN_KEY = "aegis.access_token";
export const API_BASE = `${process.env.REACT_APP_BACKEND_URL || ""}/api/v1`;

export const api = axios.create({ baseURL: API_BASE, timeout: 90000 });

api.interceptors.request.use((cfg) => {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) cfg.headers.set("Authorization", `Bearer ${token}`);
  return cfg;
});

export const MUTATED_EVENT = "iv:mutated";

api.interceptors.response.use((r) => {
  if (["post", "put", "patch", "delete"].includes((r.config.method || "").toLowerCase()) && !String(r.config.url).startsWith("/sandbox/onboarding"))
    window.dispatchEvent(new Event(MUTATED_EVENT));
  return r;
});

export function errorStatus(e: unknown): number | undefined {
  return axios.isAxiosError(e) ? e.response?.status : undefined;
}

export const ROLE_LABEL: Record<string, string> = {
  isso: "ISSO", issm: "ISSM", sca: "SCA", ao: "AO", system_owner: "System Owner", devsecops: "DevSecOps",
  leadership_viewer: "Leadership", platform_admin: "Admin",
};

export type Denied = { permission: string; roles: string[] };

export function deniedInfo(e: unknown): Denied | null {
  if (!axios.isAxiosError(e) || e.response?.status !== 403) return null;
  const d = (e.response?.data as { detail?: Record<string, unknown> } | undefined)?.detail;
  return d && typeof d === "object" && d.code === "missing_permission" ? { permission: String(d.permission), roles: (d.roles as string[]) ?? [] } : null;
}

let actingLabel = "";
export const setActingLabel = (v: string) => { actingLabel = v; };
export const getActingLabel = () => actingLabel;
let deniedFmt: ((perm: string, roles: string[]) => string) | null = null;
export const setDeniedFormatter = (f: (perm: string, roles: string[]) => string) => { deniedFmt = f; };

export function errorMessage(e: unknown): string {
  const den = deniedInfo(e);
  if (den) {
    window.dispatchEvent(new CustomEvent("iv:denied", { detail: { perm: den.permission, roles: den.roles } }));
    return deniedFmt ? deniedFmt(den.permission, den.roles)
      : `Your role can't do this (needs “${den.permission}”${den.roles.length ? `, held by ${den.roles.map((r) => ROLE_LABEL[r] ?? r).join(", ")}` : ""}).`;
  }
  if (!axios.isAxiosError(e)) return e instanceof Error ? e.message : "Unexpected error";
  const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && typeof d.msg === "string" ? d.msg : JSON.stringify(d))).join(" ");
  }
  return e.message || "Request failed";
}
