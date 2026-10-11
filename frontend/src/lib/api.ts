import axios from "axios";

export const TOKEN_KEY = "aegis.access_token";
export const API_BASE = `${process.env.REACT_APP_BACKEND_URL || ""}/api/v1`;

export const api = axios.create({ baseURL: API_BASE, timeout: 90000 });

api.interceptors.request.use((cfg) => {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) cfg.headers.set("Authorization", `Bearer ${token}`);
  return cfg;
});

export function errorStatus(e: unknown): number | undefined {
  return axios.isAxiosError(e) ? e.response?.status : undefined;
}

export function errorMessage(e: unknown): string {
  if (!axios.isAxiosError(e)) return e instanceof Error ? e.message : "Unexpected error";
  const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && typeof d.msg === "string" ? d.msg : JSON.stringify(d))).join(" ");
  }
  return e.message || "Request failed";
}
