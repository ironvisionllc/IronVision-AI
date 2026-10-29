import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { usePref } from "@/lib/prefs";
import { AsSnap, AutoSaver, REGISTRY, same } from "@/lib/autosave";

type Method = "put" | "patch" | "post";
/** Auto-save request: X-Autosave marks it (coalesced audit, draft-only rules), X-Base-Version = the record version the edit started from. */
export async function autosaveCall<R = Record<string, unknown>>(method: Method, url: string, body: unknown, base: string | null, confirmed = false) {
  try {
    const headers: Record<string, string> = { "X-Autosave": "1" };
    if (base) headers["X-Base-Version"] = base;
    if (confirmed) headers["X-Sod-Confirmed"] = "1";
    return (await api.request<R>({ method, url, data: body, headers })).data;
  } catch (e) {
    const r = (e as { response?: { status: number; data?: { detail?: unknown } } }).response;
    throw { status: r?.status, detail: r?.data?.detail };
  }
}

export interface AutoSaveOpts<T> {
  id: string | null;            // record key; null = not ready / nothing to save
  value: T;                     // current form value
  initial: T;                   // the saved (server) value the editor started from
  version?: string | null;      // record updated_at when the editor loaded
  resetKey?: string;            // change it when the record is reloaded after an explicit action
  save: (v: T, base: string | null, confirmed: boolean) => Promise<{ version?: string | null } | void>;
  apply: (v: T) => void;        // put a value back into the form (undo, restore, use theirs)
  disabled?: boolean;           // locked / read-only for the role
  sync?: boolean;               // false: the form value is already live when the editor opens (no wait for the saved value)
}
export interface AutoSave<T> { on: boolean; setOn: (v: boolean) => void; snap: AsSnap<T> | null; saver: AutoSaver<T> | null; apply: (v: T) => void; flush: () => void }

export function useAutoSave<T>(o: AutoSaveOpts<T>): AutoSave<T> {
  const { user } = useAuth();
  const [on, setOn] = usePref("autosave", true);
  const [snap, setSnap] = useState<AsSnap<T> | null>(null);
  const ref = useRef<AutoSaver<T> | null>(null);
  const synced = useRef(false);
  const saveRef = useRef(o.save); saveRef.current = o.save;
  const u = user || null;
  const active = on && !o.disabled && !!o.id && !!u;
  const key = `iv.draft.${u?.id}.${u?.org_id}.${o.id}`;
  // a reload resets the editor only when it brings someone else's version (not the echo of our own save) and nothing is pending
  const [tok, setTok] = useState(0);
  useEffect(() => {
    const s = ref.current;
    if (s && o.version !== s.version && !s.snap.dirty && s.snap.state !== "saving") setTok((t) => t + 1);
  }, [o.resetKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!active) return;
    synced.current = false;
    const s = new AutoSaver<T>({ key, initial: o.initial, version: o.version, save: (v, b, c) => saveRef.current(v, b, c), onChange: setSnap });
    ref.current = s; setSnap(s.snap); REGISTRY.add(s as AutoSaver<unknown>);
    return () => {
      REGISTRY.delete(s as AutoSaver<unknown>); void s.flush().finally(() => api.post("/autosave/close", {}).catch(() => undefined)); s.dispose();
      ref.current = null; setSnap(null);
    };
  }, [active, key, tok]); // eslint-disable-line react-hooks/exhaustive-deps
  // forms often fill their state from the server one render later – edits count only once the form shows the saved value
  useEffect(() => {
    const s = ref.current;
    if (!s) return;
    if (!synced.current) { if (o.sync === false || same(o.value, o.initial)) synced.current = true; else return; }
    s.edit(o.value);
  }, [o.value, snap === null]); // eslint-disable-line react-hooks/exhaustive-deps
  return { on, setOn, snap, saver: ref.current, apply: o.apply, flush: () => void ref.current?.flush() };
}
