import { AutoSaver, BACKOFF_MS, DEBOUNCE_MS, REGISTRY, anyDirty, anyFailed } from "@/lib/autosave";

const mem = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), m }; };
const tick = () => new Promise((r) => jest.requireActual("timers").setImmediate(r));
const err = (status?: number, detail?: unknown) => ({ status, detail });

beforeEach(() => jest.useFakeTimers());
afterEach(() => { jest.useRealTimers(); REGISTRY.clear(); });

test("debounce: saves once, 1500 ms after typing stops", async () => {
  const save = jest.fn().mockResolvedValue({ version: "v2" });
  const s = new AutoSaver({ key: "k", initial: { a: "" }, version: "v1", save, storage: mem() });
  s.edit({ a: "x" }); jest.advanceTimersByTime(1000); s.edit({ a: "xy" }); jest.advanceTimersByTime(DEBOUNCE_MS - 1);
  expect(save).not.toHaveBeenCalled(); expect(s.snap.state).toBe("pending");
  jest.advanceTimersByTime(1); await tick();
  expect(save).toHaveBeenCalledTimes(1); expect(save).toHaveBeenCalledWith({ a: "xy" }, "v1", false);
  expect(s.snap.state).toBe("saved"); expect(s.version).toBe("v2"); expect(s.snap.savedAt).not.toBeNull();
});

test("flush (blur / Ctrl+S / navigation) saves immediately; nothing to save → no call", async () => {
  const save = jest.fn().mockResolvedValue({});
  const s = new AutoSaver({ key: "k", initial: "a", save, storage: mem() });
  await s.flush(); expect(save).not.toHaveBeenCalled();
  s.edit("b"); await s.flush(); expect(save).toHaveBeenCalledTimes(1); expect(s.snap.state).toBe("saved");
});

test("network failure: Not saved, local draft kept, backoff 2/5/15/30/60/60 s, Retry now, cleared on success", async () => {
  const st = mem();
  const save = jest.fn().mockRejectedValue(err(undefined));
  const s = new AutoSaver({ key: "k", initial: "a", save, storage: st });
  REGISTRY.add(s as AutoSaver<unknown>);
  s.edit("b"); await s.flush();
  expect(s.snap.state).toBe("error"); expect(s.snap.failures).toBe(1); expect(s.snap.nextRetryMs).toBe(2000);
  expect(JSON.parse(st.getItem("k")!).v).toBe("b"); expect(anyDirty()).toBe(true); expect(anyFailed()).toBe(true);
  const waits: number[] = [];
  for (let i = 0; i < 5; i++) { waits.push(s.snap.nextRetryMs!); jest.advanceTimersByTime(s.snap.nextRetryMs!); await tick(); await tick(); }
  expect(waits).toEqual(BACKOFF_MS); expect(s.snap.nextRetryMs).toBe(60000); expect(save).toHaveBeenCalledTimes(6);
  save.mockResolvedValue({ version: "v9" }); await s.retryNow();
  expect(s.snap.state).toBe("saved"); expect(st.getItem("k")).toBeNull(); expect(anyDirty()).toBe(false);
});

test("local draft is offered on reload (Restore unsaved changes?) and can be discarded", () => {
  const st = mem(); st.setItem("k", JSON.stringify({ v: "unsaved", base: "v1" }));
  const s = new AutoSaver({ key: "k", initial: "server", save: jest.fn(), storage: st });
  expect(s.snap.restore).toBe("unsaved");
  expect(s.acceptRestore()).toBe("unsaved"); expect(s.value).toBe("unsaved"); expect(s.snap.state).toBe("pending");
  const s2 = new AutoSaver({ key: "k", initial: "server", save: jest.fn(), storage: st });
  s2.discardRestore(); expect(st.getItem("k")).toBeNull();
  expect(new AutoSaver({ key: "k", initial: "same", save: jest.fn(), storage: (() => { const m = mem(); m.setItem("k", JSON.stringify({ v: "same" })); return m; })() }).snap.restore).toBeNull();
});

test("conflict 409: dialog state with theirs; Keep mine re-saves on their version, Use theirs adopts it", async () => {
  const save = jest.fn().mockRejectedValueOnce(err(409, { code: "conflict", version: "v5", theirs: { a: "theirs" } })).mockResolvedValue({ version: "v6" });
  const s = new AutoSaver({ key: "k", initial: { a: "base" }, version: "v1", save, storage: mem() });
  s.edit({ a: "mine" }); await s.flush();
  expect(s.snap.state).toBe("conflict"); expect(s.snap.theirs).toEqual({ a: "theirs" });
  s.edit({ a: "mine2" }); jest.advanceTimersByTime(5000); await tick(); expect(save).toHaveBeenCalledTimes(1);  // never overwrite silently
  await s.keepMine(); expect(save).toHaveBeenLastCalledWith({ a: "mine2" }, "v5", false); expect(s.snap.state).toBe("saved");
  const s2 = new AutoSaver({ key: "k2", initial: { a: "base" }, version: "v1", save: jest.fn().mockRejectedValue(err(409, { code: "conflict", version: "v7", theirs: { a: "t" } })), storage: mem() });
  s2.edit({ a: "m" }); await s2.flush(); expect(s2.useTheirs()).toEqual({ a: "t" }); expect(s2.version).toBe("v7"); expect(s2.snap.state).toBe("saved");
});

test("locked 423 and SoD 428 pause auto-save until the explicit decision", async () => {
  const save = jest.fn().mockRejectedValueOnce(err(428, { message: "Editing makes you the preparer" })).mockResolvedValue({});
  const s = new AutoSaver({ key: "k", initial: "a", save, storage: mem() });
  s.edit("b"); await s.flush(); expect(s.snap.state).toBe("confirm");
  s.edit("c"); jest.advanceTimersByTime(3000); await tick(); expect(save).toHaveBeenCalledTimes(1);
  await s.confirmSod(); expect(save).toHaveBeenLastCalledWith("c", null, true); expect(s.snap.state).toBe("saved");
  const l = new AutoSaver({ key: "l", initial: "a", save: jest.fn().mockRejectedValue(err(423, { message: "approved" })), storage: mem() });
  l.edit("b"); await l.flush(); expect(l.snap.state).toBe("locked"); expect(l.snap.message).toBe("approved");
});

test("validation 422: valid fields are saved, invalid ones highlighted", async () => {
  const save = jest.fn().mockRejectedValueOnce(err(422, [{ loc: ["body", "title"], msg: "too short" }])).mockResolvedValue({});
  const s = new AutoSaver({ key: "k", initial: { title: "Good title", plan: "" }, save, storage: mem() });
  s.edit({ title: "x", plan: "new plan" }); await s.flush();
  expect(save).toHaveBeenLastCalledWith({ title: "Good title", plan: "new plan" }, null, false);
  expect(s.snap.state).toBe("invalid"); expect(s.snap.invalid).toEqual(["title"]);
});

test("undo restores the previous saved value", async () => {
  const save = jest.fn().mockResolvedValue({});
  const s = new AutoSaver({ key: "k", initial: "one", save, storage: mem() });
  s.edit("two"); await s.flush(); expect(s.snap.canUndo).toBe(true);
  expect(s.undo()).toBe("one"); await tick(); expect(save).toHaveBeenLastCalledWith("one", null, false); expect(s.saved).toBe("one");
});
