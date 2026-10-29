/** Auto-save engine (framework-free, unit-tested): 1,500 ms debounce, immediate flush, local browser draft, retry with backoff,
 * conflict (409) / locked (423) / SoD-confirm (428) / validation (422) handling and undo of the last saved value. */
export type AsState = "idle" | "pending" | "saving" | "saved" | "error" | "conflict" | "locked" | "confirm" | "invalid";
export const DEBOUNCE_MS = 1500;
export const BACKOFF_MS = [2000, 5000, 15000, 30000, 60000];

export interface AsError { status?: number; detail?: unknown }
export interface AsSnap<T> {
  state: AsState; savedAt: number | null; message: string; invalid: string[]; theirs: T | null; failures: number;
  nextRetryMs: number | null; canUndo: boolean; restore: T | null; dirty: boolean;
}
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
type Timers = { set: (f: () => void, ms: number) => unknown; clear: (h: unknown) => void };
export interface AsOpts<T> {
  key: string; initial: T; version?: string | null;
  save: (v: T, base: string | null, confirmed: boolean) => Promise<{ version?: string | null } | void>;
  onChange?: (s: AsSnap<T>) => void; storage?: Store; timers?: Timers; now?: () => number; debounce?: number;
}

export const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const fieldsOf = (detail: unknown): string[] => Array.isArray(detail)
  ? detail.map((d) => (d as { loc?: unknown[] })?.loc?.slice(-1)[0]).filter((x): x is string => typeof x === "string") : [];

export class AutoSaver<T> {
  value: T; saved: T; prev: T | undefined; version: string | null; theirVersion: string | null = null;
  confirmed = false; private o: AsOpts<T>; private t: Timers; private st: Store; private h: unknown = null; private r: unknown = null;
  private busy = false; private again = false;
  snap: AsSnap<T>;

  constructor(o: AsOpts<T>) {
    this.o = o; this.value = o.initial; this.saved = o.initial; this.version = o.version ?? null;
    this.t = o.timers || { set: (f, ms) => setTimeout(f, ms), clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>) };
    this.st = o.storage || localStorage;
    let restore: T | null = null;
    try { const raw = this.st.getItem(o.key); const d = raw ? JSON.parse(raw) : null; if (d && !same(d.v, o.initial)) restore = d.v; } catch { /* corrupt local draft */ }
    this.snap = { state: "idle", savedAt: null, message: "", invalid: [], theirs: null, failures: 0, nextRetryMs: null, canUndo: false, restore, dirty: false };
  }

  private now() { return (this.o.now || Date.now)(); }
  private set(p: Partial<AsSnap<T>>) {
    this.snap = { ...this.snap, ...p, canUndo: this.prev !== undefined, dirty: !same(this.value, this.saved) || ["error", "conflict", "confirm"].includes(p.state ?? this.snap.state) };
    this.o.onChange?.(this.snap);
  }
  private clearTimers() { if (this.h) this.t.clear(this.h); if (this.r) this.t.clear(this.r); this.h = this.r = null; }

  edit(v: T) {
    if (same(v, this.value)) return;
    this.value = v;
    try { this.st.setItem(this.o.key, JSON.stringify({ v, base: this.version, at: this.now() })); } catch { /* storage full */ }
    if (["conflict", "locked", "confirm"].includes(this.snap.state)) { this.set({}); return; }  // wait for the user's decision
    if (this.h) this.t.clear(this.h);
    this.h = this.t.set(() => { this.h = null; void this.flush(); }, this.o.debounce ?? DEBOUNCE_MS);
    this.set({ state: this.busy ? "saving" : "pending" });
  }

  async flush(): Promise<void> {
    if (this.h) { this.t.clear(this.h); this.h = null; }
    if (["conflict", "locked", "confirm"].includes(this.snap.state)) return;
    if (same(this.value, this.saved) && this.snap.state !== "error") return;
    if (this.busy) { this.again = true; return; }
    await this.run(this.value);
  }

  private async run(v: T) {
    this.busy = true; this.set({ state: "saving" });
    try {
      const res = await this.o.save(v, this.version, this.confirmed);
      this.prev = this.saved; this.saved = v; this.version = (res && res.version) || this.version;
      if (same(v, this.value)) { try { this.st.removeItem(this.o.key); } catch { /* ignore */ } }
      if (this.r) { this.t.clear(this.r); this.r = null; }
      this.set({ state: "saved", savedAt: this.now(), failures: 0, nextRetryMs: null, message: "", invalid: [] });
    } catch (e) {
      const { status, detail } = (e || {}) as AsError;
      const d = (detail || {}) as Record<string, unknown>;
      const msg = typeof detail === "string" ? detail : String(d.message || "");
      if (status === 409 && d.code === "conflict") { this.theirVersion = (d.version as string) || null; this.set({ state: "conflict", theirs: (d.theirs as T) ?? null, message: msg }); }
      else if (status === 423) this.set({ state: "locked", message: msg });
      else if (status === 428) this.set({ state: "confirm", message: msg });
      else if (status === 422 || status === 413 || status === 409) {
        const bad = fieldsOf(detail);
        if (bad.length && v && typeof v === "object" && !Array.isArray(v)) {  // save the valid fields, keep the invalid ones highlighted
          const partial = { ...(v as object) } as Record<string, unknown>;
          for (const k of bad) partial[k] = (this.saved as Record<string, unknown>)?.[k];
          this.busy = false;
          if (!same(partial, v) && !same(partial, this.saved)) { await this.run(partial as T); this.value = v; }
          this.set({ state: "invalid", invalid: bad, message: "Some fields are invalid – the other changes were saved" });
          return;
        }
        this.set({ state: "invalid", invalid: [], message: msg || "Not saved – fix the highlighted value" });
      } else {
        const n = this.snap.failures + 1, wait = BACKOFF_MS[Math.min(n - 1, BACKOFF_MS.length - 1)];
        this.set({ state: "error", failures: n, nextRetryMs: wait, message: msg || "Network error" });
        if (this.r) this.t.clear(this.r);
        this.r = this.t.set(() => { this.r = null; void this.flush(); }, wait);
      }
    } finally {
      this.busy = false;
      if (this.again) { this.again = false; void this.flush(); }
    }
  }

  retryNow() { if (this.r) { this.t.clear(this.r); this.r = null; } return this.run(this.value); }
  confirmSod() { this.confirmed = true; this.set({ state: "pending" }); return this.run(this.value); }
  /** Undo: put back the previous saved value (returned so the form can show it) and save it. */
  undo(): T | undefined { const p = this.prev; if (p === undefined) return undefined; this.value = p; this.prev = undefined; void this.run(p); return p; }
  keepMine() { this.version = this.theirVersion; this.set({ state: "pending", theirs: null }); return this.run(this.value); }
  useTheirs(): T | null {
    const th = this.snap.theirs; this.version = this.theirVersion;
    if (th !== null) { this.value = this.saved = th; }
    try { this.st.removeItem(this.o.key); } catch { /* ignore */ }
    this.set({ state: "saved", theirs: null, savedAt: this.now() }); return th;
  }
  acceptRestore(): T | null { const v = this.snap.restore; this.set({ restore: null }); if (v !== null) this.edit(v); return v; }
  discardRestore() { try { this.st.removeItem(this.o.key); } catch { /* ignore */ } this.set({ restore: null }); }
  dispose() { this.clearTimers(); }
  /** The record was submitted explicitly (e.g. Register) – drop pending changes and the local draft. */
  discard() { this.clearTimers(); this.saved = this.value; try { this.st.removeItem(this.o.key); } catch { /* ignore */ } this.set({ state: "idle" }); }
}

export const REGISTRY = new Set<AutoSaver<unknown>>();
export const anyDirty = () => [...REGISTRY].some((s) => s.snap.dirty);
export const anyFailed = () => [...REGISTRY].some((s) => s.snap.dirty && (["error", "conflict", "confirm", "invalid"].includes(s.snap.state) || s.snap.failures > 0));
export const flushAll = () => Promise.all([...REGISTRY].map((s) => s.flush()));
if (typeof window !== "undefined") (window as unknown as Record<string, unknown>).__ivAutosave = { anyDirty, anyFailed, size: () => REGISTRY.size, states: () => [...REGISTRY].map((s) => s.snap.state) };
