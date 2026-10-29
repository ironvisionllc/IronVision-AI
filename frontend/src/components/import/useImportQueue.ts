import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import type { Row } from "@/lib/useApi";
import type { QFile } from "./queue";
import { classify, removable, route, target, targetDecision } from "./queue";

/** Queue of uploaded files: detect → ready / needs decision → import (existing pipelines + their review screens) → result. */
export function useImportQueue(sid: string, types: Row, preset: string | undefined, canRegister: boolean, onChange: () => void) {
  const [files, setFiles] = useState<QFile[]>([]);
  const [running, setRunning] = useState(false);
  const [summaryKeys, setSummary] = useState<string[] | null>(null);
  const summary = summaryKeys && files.filter((f) => summaryKeys.includes(f.key));  // live: reflects later decisions/removals
  const ref = useRef<QFile[]>([]);
  const set = useCallback((fn: (fs: QFile[]) => QFile[]) => { ref.current = fn(ref.current); setFiles(ref.current); }, []);
  useEffect(() => {  // target system / permissions changed → re-check files that have not been sent yet
    set((fs) => fs.map((f) => f.det && (f.state === "ready" || (f.state === "detecting" && f.det) || (f.state === "failed" && f.blocked) ||
      (f.state === "needs_decision" && f.decision?.kind !== "target")) ? classify({ ...f, decision: undefined, error: undefined }, types, preset) : f));
  }, [types, preset, set]);
  const patch = useCallback((key: string, p: Partial<QFile> | ((f: QFile) => QFile)) =>
    set((fs) => fs.map((f) => f.key === key ? (typeof p === "function" ? p(f) : { ...f, ...p }) : f)), [set]);

  const add = useCallback(async (list: FileList | File[]) => {
    const fresh: QFile[] = Array.from(list).map((file, i) => ({ key: `f${Date.now().toString(36)}${i}${Math.random().toString(36).slice(2, 6)}`, file, det: null, type: "", state: "uploaded" }));
    set((fs) => [...fs, ...fresh]);
    for (const f of fresh) {
      patch(f.key, { state: "detecting" });
      const fd = new FormData(); fd.append("file", f.file); if (sid) fd.append("system_id", sid);
      try { const det = (await api.post<Row>("/import-center/detect", fd)).data; patch(f.key, (x) => classify({ ...x, det }, types, preset)); }
      catch (e) { patch(f.key, { state: "failed", error: errorMessage(e) }); }
    }
  }, [sid, types, preset, set, patch]);

  const runOne = useCallback(async (key: string) => {
    const f = ref.current.find((x) => x.key === key);
    if (!f || f.state !== "ready" || !sid) return;
    patch(key, { state: "importing", error: undefined });
    try {
      const res = await route(f.type, sid, f.file);
      if (res.pending_target) patch(key, { state: "needs_decision", emassId: res.emass_id, decision: targetDecision(res.mismatch, canRegister), res: { target_done: false } });
      else patch(key, { state: "imported", res, emassId: res.emass_id });
      onChange();
    } catch (e) { patch(key, { state: "failed", error: errorMessage(e) }); }
  }, [sid, canRegister, patch, onChange]);

  const importAll = useCallback(async () => {
    setRunning(true); setSummary(null);
    for (const f of ref.current.filter((x) => x.state === "ready")) await runOne(f.key);  // one at a time: per-file progress, no pipeline overload
    setRunning(false); setSummary(ref.current.filter((x) => x.state !== "removed").map((x) => x.key));
  }, [runOne]);

  const resolveOne = useCallback(async (f: QFile, v: string) => {
    const d = f.decision!;
    if (v === "__remove") return "remove";
    if (d.kind === "type" || d.kind === "override") patch(f.key, (x) => classify({ ...x, type: v, decision: undefined }, types, preset));
    else if (d.kind === "policy_ai") patch(f.key, (x) => classify({ ...x, policyOk: true, decision: undefined }, types, preset));
    else if (d.kind === "target" && f.emassId) {
      try {
        const res = await target(f.emassId, v as "update" | "register" | "cancel", sid, f.type);
        patch(f.key, res.cancelled ? { state: "removed", decision: undefined } : { state: "imported", decision: undefined, res, emassId: res.emass_id });
        onChange();
      } catch (e) { patch(f.key, { state: "failed", error: errorMessage(e), decision: undefined }); }
    }
    return "ok";
  }, [sid, types, preset, patch, onChange]);

  const remove = useCallback(async (keys: string[]) => {
    const fs = ref.current.filter((f) => keys.includes(f.key) && removable(f));
    if (!fs.length || !window.confirm(`Remove ${fs.length} file(s) before import? Nothing from them has been applied; uploaded copies are deleted. This is recorded in the audit log.`)) return;
    try {
      const r = (await api.post<Row>("/import-center/remove", { system_id: sid || null, items: fs.map((f) => ({ file_name: f.file.name, size_bytes: f.file.size, state: f.state, emass_import_id: f.emassId || null })) })).data;
      const skipped = new Map((r.skipped || []).map((s: Row) => [s.file_name, s.reason]));
      set((all) => all.map((f) => !fs.some((x) => x.key === f.key) ? f : skipped.has(f.file.name) ? { ...f, error: String(skipped.get(f.file.name)) } : { ...f, state: "removed", decision: undefined }));
      toast.success(`${r.removed.length} file(s) removed${r.skipped.length ? `, ${r.skipped.length} kept (${r.skipped[0].reason})` : ""}`);
      onChange();
    } catch (e) { toast.error(errorMessage(e)); }
  }, [sid, set, onChange]);

  const resolve = useCallback(async (key: string, v: string, all: boolean) => {
    const f = ref.current.find((x) => x.key === key);
    if (!f?.decision) return;
    const same = all && f.decision.batchSafe ? ref.current.filter((x) => x.state === "needs_decision" && x.decision?.kind === f.decision!.kind) : [f];
    const drop: string[] = [];
    for (const x of same) if ((await resolveOne(x, v)) === "remove") drop.push(x.key);
    if (drop.length) await remove(drop);
  }, [resolveOne, remove]);

  const setType = useCallback((key: string, t: string) => patch(key, (x) => classify({ ...x, type: t, decision: undefined }, types, preset)), [patch, types, preset]);
  return { files, add, runOne, importAll, resolve, remove, setType, running, summary, closeSummary: () => setSummary(null) };
}
