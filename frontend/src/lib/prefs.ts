import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/** Per-user UI preferences: server-side (/me/preferences) with a localStorage fallback when offline or not yet loaded. */
const EVT = "iv-prefs-changed";
const lk = (uid: string | undefined, key: string) => `iv.pref.${uid || "anon"}.${key}`;
let server: Promise<Record<string, unknown>> | null = null;
let serverUid: string | undefined;

function loadServer(uid?: string) {
  if (!server || serverUid !== uid) { serverUid = uid; server = api.get<Record<string, unknown>>("/me/preferences").then((r) => r.data).catch(() => ({})); }
  return server;
}

export function readLocal(uid: string | undefined, key: string): string | null { return localStorage.getItem(lk(uid, key)); }

export function writePref(uid: string | undefined, key: string, value: string | boolean) {
  localStorage.setItem(lk(uid, key), String(value));
  window.dispatchEvent(new Event(EVT));
  if (uid) {
    server = (server || Promise.resolve({})).then((p) => ({ ...p, [key]: value }));
    api.put("/me/preferences", { [key]: value }).catch(() => undefined);
  }
}

/** Raw string value (null = never set). Server value wins once loaded; localStorage is the fallback. */
export function usePrefRaw(key: string): [string | null, (v: string | boolean) => void] {
  const { user } = useAuth();
  const uid = (user || null)?.id as string | undefined;
  const [v, setV] = useState<string | null>(readLocal(uid, key));
  useEffect(() => {
    const f = () => setV(readLocal(uid, key)); f();
    if (uid) loadServer(uid).then((p) => { if (p[key] !== undefined && p[key] !== null) { localStorage.setItem(lk(uid, key), String(p[key])); f(); } });
    window.addEventListener(EVT, f); return () => window.removeEventListener(EVT, f);
  }, [uid, key]);
  return [v, (val) => writePref(uid, key, val)];
}

export function usePref(key: string, dflt: boolean): [boolean, (v: boolean) => void] {
  const [raw, set] = usePrefRaw(key);
  return [raw === null ? dflt : raw === "true" || raw === "on", set];
}
