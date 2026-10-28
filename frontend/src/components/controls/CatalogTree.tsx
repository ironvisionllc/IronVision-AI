import { KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { ControlSummary } from "@/lib/types";
import { useSystems } from "@/context/SystemContext";
import { BaselinePill, StatusPill } from "@/components/common/StatusPill";
import { ControlDetailDrawer } from "@/components/controls/ControlDetailDrawer";
import { cn, human } from "@/lib/format";
import {
  allKeys, applicability, buildTree, ctlKey, famKey, familyStats, filterTree, Filters, idLabel, loadState, matcher, NO_FILTERS, passes,
  pathTo, saveState, searchTree, SysRow, type FamilyNode,
} from "@/lib/catalogTree";

const FILTERS: [keyof Filters, string, [string, string][], boolean][] = [
  ["baseline", "Baseline", [["low", "Low"], ["moderate", "Moderate"], ["high", "High"], ["privacy", "Privacy"], ["baseline", "In system baseline (FIPS 199 / CNSSI 1253)"],
    ["overlay", "Added by overlay"], ["tailored_in", "Tailored in"]], false],
  ["implementation_status", "Implementation status", ["planned", "partially_implemented", "implemented", "inherited", "not_applicable", "not_implemented"].map((v) => [v, human(v)]), true],
  ["assessment_status", "Assessment status", ["not_assessed", "satisfied", "other_than_satisfied"].map((v) => [v, human(v)]), true],
  ["applicability", "Applicability", [["applicable", "Applicable"], ["not_applicable", "Not applicable"], ["inherited", "Inherited"], ["not_selected", "Not selected for this system"]], true],
];

function Hl({ text, words }: { text: string; words: string[] }) {
  if (!words.length) return <>{text}</>;
  const rx = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig");
  return <>{text.split(rx).map((p, i) => (i % 2 ? <mark key={i} className="rounded bg-amber-200 px-0.5 text-slate-900">{p}</mark> : p))}</>;
}

function useDebounced<T>(v: T, ms = 200): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

type Vis = { key: string; parent?: string; expandKey?: string; id?: string };

export function CatalogTree() {
  const { systems } = useSystems();
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const sysId = params.get("system") || "";
  const openId = params.get("control");
  const saved = useMemo(() => loadState(sysId), [sysId]);
  const [items, setItems] = useState<ControlSummary[] | null>(null);
  const [sys, setSys] = useState<Map<string, SysRow> | null>(null);
  const [cci, setCci] = useState<Record<string, string[]> | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set(saved?.expanded ?? []));
  const [q, setQ] = useState(saved?.q ?? "");
  const [withdrawn, setWithdrawn] = useState(saved?.withdrawn ?? false);
  const [filters, setFilters] = useState<Filters>(saved?.filters ?? NO_FILTERS);
  const [focusKey, setFocusKey] = useState("");
  const preSearch = useRef<Set<string> | null>(null);
  const refs = useRef(new Map<string, HTMLElement>());
  const dq = useDebounced(q);

  useEffect(() => {
    const t0 = performance.now();
    api.get<{ items: ControlSummary[] }>("/controls", { params: { include_withdrawn: true, limit: 2000 } })
      .then((r) => { setItems(r.data.items); (window as unknown as Record<string, unknown>).__catalogTreeLoadMs = Math.round(performance.now() - t0); })
      .catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(() => {
    if (!sysId) { setSys(null); return; }
    api.get<SysRow[]>(`/systems/${sysId}/workbench/controls`, { params: { limit: 5000 } }).then((r) => setSys(new Map(r.data.map((x) => [x.control_id, x])))).catch((e) => setError(errorMessage(e)));
  }, [sysId]);
  const norm = dq.trim().toLowerCase();
  useEffect(() => {
    if (/^cci[-\s]?\d/.test(norm) && !cci) api.get<Record<string, string[]>>("/controls/cci-index").then((r) => setCci(r.data)).catch(() => setCci({}));
  }, [norm, cci]);

  const tree = useMemo(() => buildTree(items ?? [], withdrawn), [items, withdrawn]);
  const filtered = useMemo(() => (Object.values(filters).some(Boolean) ? filterTree(tree, (c) => passes(c, filters, sys)) : tree), [tree, filters, sys]);
  const match = useMemo(() => matcher(dq, cci), [dq, cci]);
  const found = useMemo(() => (match ? searchTree(filtered, match) : null), [filtered, match]);
  const shown: FamilyNode[] = useMemo(() => (found ? filterTree(filtered, (c) => found.matches.has(c.control_id)) : filtered), [filtered, found]);
  const filtering = Object.values(filters).some(Boolean);
  const fit = (c: ControlSummary) => !filtering || passes(c, filters, sys);  // parents shown only as context for a matching enhancement are dimmed
  const words = match && !/^(cci|[a-z]{2}[-\s]?\d)/.test(norm) ? norm.split(/\s+/).filter(Boolean) : [];

  useEffect(() => {  // search expands matching branches; clearing it restores the expansion from before the search
    if (!items) return;
    if (found) {
      if (!preSearch.current) preSearch.current = expanded;
      setExpanded(new Set([...preSearch.current, ...found.expand]));
    } else if (preSearch.current) { setExpanded(preSearch.current); preSearch.current = null; }
  }, [found, items]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {  // deep link: expand family (and parent) and scroll the control into view
    if (!items || !openId) return;
    const p = pathTo(tree, openId);
    if (p.length) setExpanded((e) => new Set([...e, ...p]));
    setTimeout(() => refs.current.get(`n:${openId}`)?.scrollIntoView?.({ block: "center" }), 50);
  }, [items, openId]); // eslint-disable-line react-hooks/exhaustive-deps

  const scrollY = () => document.querySelector("[data-testid=main-content]")?.scrollTop || window.scrollY;
  const persist = useCallback(() => saveState(sysId, { expanded: [...(preSearch.current ?? expanded)], q, withdrawn, filters, scrollY: scrollY() }),
    [sysId, expanded, q, withdrawn, filters]);
  useEffect(() => { persist(); }, [persist]);
  useEffect(() => {  // restore scroll position after returning from a control's details
    if (!items || !saved?.scrollY || openId) return;
    requestAnimationFrame(() => { const m = document.querySelector("[data-testid=main-content]"); if (m) m.scrollTop = saved.scrollY; window.scrollTo(0, saved.scrollY); });
  }, [items]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (k: string, open?: boolean) => setExpanded((e) => { const n = new Set(e); (open ?? !n.has(k)) ? n.add(k) : n.delete(k); return n; });
  const open = (id: string) => {
    persist();
    if (sysId) nav(`/systems/${sysId}/controls/${id}`);
    else { const p = new URLSearchParams(params); p.set("control", id); setParams(p); }
  };
  const closeDrawer = () => { const p = new URLSearchParams(params); p.delete("control"); setParams(p); };

  const vis: Vis[] = [];
  for (const f of shown) {
    vis.push({ key: famKey(f.id), expandKey: famKey(f.id) });
    if (!expanded.has(famKey(f.id))) continue;
    for (const n of f.controls) {
      vis.push({ key: `n:${n.c.control_id}`, parent: famKey(f.id), expandKey: n.enh.length ? ctlKey(n.c.control_id) : undefined, id: n.c.control_id });
      if (expanded.has(ctlKey(n.c.control_id))) for (const e of n.enh) vis.push({ key: `n:${e.control_id}`, parent: `n:${n.c.control_id}`, id: e.control_id });
    }
  }
  const active = vis.some((v) => v.key === focusKey) ? focusKey : vis[0]?.key;
  useEffect(() => { if (focusKey) refs.current.get(focusKey)?.focus(); }, [focusKey]);
  const onKey = (ev: KeyboardEvent) => {
    const i = vis.findIndex((v) => v.key === active), v = vis[i];
    if (!v) return;
    const go = (k?: string) => { if (k) { ev.preventDefault(); setFocusKey(k); } };
    if (ev.key === "ArrowDown") go(vis[i + 1]?.key);
    else if (ev.key === "ArrowUp") go(vis[i - 1]?.key);
    else if (ev.key === "Home") go(vis[0]?.key);
    else if (ev.key === "End") go(vis[vis.length - 1]?.key);
    else if (ev.key === "ArrowRight" && v.expandKey) { ev.preventDefault(); if (!expanded.has(v.expandKey)) toggle(v.expandKey, true); else go(vis[i + 1]?.key); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); if (v.expandKey && expanded.has(v.expandKey)) toggle(v.expandKey, false); else go(v.parent); }
    else if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); if (v.id) open(v.id); else if (v.expandKey) toggle(v.expandKey); }
  };
  const reg = (k: string) => (el: HTMLElement | null) => { if (el) refs.current.set(k, el); else refs.current.delete(k); };
  const total = shown.reduce((a, f) => a + f.base + f.enhancements, 0);
  const sysName = systems.find((s) => s.id === sysId)?.name;

  return (
    <div className="panel animate-fade-up" data-testid="catalog-tree-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-3 py-3 sm:px-4">
        <div className="relative min-w-0 flex-[1_1_240px]">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" aria-hidden />
          <input className="input pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: AC-2(1), ac-2.1, CCI-000015, title or keyword"
            aria-label="Search the control catalog" data-testid="catalog-tree-search" />
        </div>
        <select className="input w-full sm:w-auto" value={sysId} aria-label="System context" data-testid="catalog-tree-system"
          onChange={(e) => { persist(); const p = new URLSearchParams(); if (e.target.value) p.set("system", e.target.value); setParams(p); }}>
          <option value="">Catalog only (no system)</option>
          {systems.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <label className="flex min-h-[40px] items-center gap-2 text-[13px] text-slate-700">
          <input type="checkbox" checked={withdrawn} onChange={(e) => setWithdrawn(e.target.checked)} className="h-4 w-4 accent-blue-700" data-testid="catalog-tree-withdrawn" />
          Show withdrawn
        </label>
        <button className="btn-secondary" onClick={() => setExpanded(new Set(allKeys(shown)))} data-testid="catalog-tree-expand-all">Expand all</button>
        <button className="btn-secondary" onClick={() => setExpanded(new Set())} data-testid="catalog-tree-collapse-all">Collapse all</button>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-3 py-2 sm:px-4" data-testid="catalog-tree-filters">
        {FILTERS.map(([k, label, opts, needsSys]) => (
          <select key={k} className="input w-full text-[12px] sm:w-auto" value={filters[k]} aria-label={label} data-testid={`catalog-tree-filter-${k}`}
            disabled={needsSys && !sysId} title={needsSys && !sysId ? "Choose a system above – this filter uses the system's own status." : label}
            onChange={(e) => setFilters({ ...filters, [k]: e.target.value })}>
            <option value="">{label}: all</option>
            {opts.map(([v, l]) => <option key={v} value={v} disabled={!sysId && ["baseline", "overlay", "tailored_in"].includes(v)}>{l}</option>)}
          </select>))}
        {Object.values(filters).some(Boolean) && <button className="text-[12px] text-blue-800 underline" onClick={() => setFilters(NO_FILTERS)} data-testid="catalog-tree-clear-filters">Clear filters</button>}
      </div>
      <div className="px-3 py-2 text-[12px] text-slate-600 sm:px-4" data-testid="catalog-tree-summary">
        {sysId ? <>System context: <b>{sysName}</b>. Used in RMF Step 3 <b>Select</b> (baseline, tailoring) and Step 4 <b>Implement</b> (status, statements, evidence). Opening a control opens its Control Workbench record.</>
          : <>Catalog only: NIST SP 800-53 Rev 5 reference. Choose a system to see applicability and status.</>}
        <span className="ml-2" data-testid="catalog-tree-count">{found ? `${found.matches.size} match${found.matches.size === 1 ? "" : "es"}` : `${total.toLocaleString()} controls + enhancements`}{withdrawn ? " (incl. withdrawn)" : ""}</span>
      </div>
      {error && <div className="px-4 py-3 text-sm text-rose-700" role="alert" data-testid="catalog-tree-error">{error}</div>}
      {!items && !error && <div className="px-4 py-6 text-sm text-slate-500" data-testid="catalog-tree-loading">Loading catalog…</div>}
      {items && shown.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500" data-testid="catalog-tree-empty">No controls match.</div>}
      <ul role="tree" aria-label="NIST SP 800-53 Rev 5 control families" className="pb-2" onKeyDown={onKey} data-testid="catalog-tree">
        {shown.map((f) => {
          const fk = famKey(f.id), isOpen = expanded.has(fk), st = familyStats(tree.find((x) => x.id === f.id) ?? f, sys);  // whole family, not the filtered view
          return (
            <li key={f.id} role="treeitem" aria-level={1} aria-expanded={isOpen} aria-selected={false} ref={reg(fk)} tabIndex={active === fk ? 0 : -1}
              onFocus={(e) => e.target === e.currentTarget && setFocusKey(fk)} className="border-b border-slate-100 outline-none focus-visible:ring-2 focus-visible:ring-blue-600" data-testid={`tree-family-${f.id}`}>
              <button tabIndex={-1} onClick={() => { setFocusKey(fk); toggle(fk); }} className="flex min-h-[44px] w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left hover:bg-slate-50 sm:px-4" data-testid={`tree-family-toggle-${f.id}`}>
                {isOpen ? <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" aria-hidden /> : <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" aria-hidden />}
                <span className="w-8 font-mono text-[13px] font-bold text-blue-900">{f.id.toUpperCase()}</span>
                <span className="min-w-0 flex-1 basis-[55%] break-words font-medium text-slate-900 sm:basis-auto">{f.title}</span>
                <span className="w-full pl-[60px] text-[11px] text-slate-600 sm:w-auto sm:pl-0" data-testid={`tree-family-counts-${f.id}`}>{f.base} controls · {f.enhancements} enhancements
                  {st && ` · ${st.applicable} applicable · ${st.implemented} implemented · ${st.assessed} assessed`}</span>
              </button>
              {isOpen && <ul role="group">{f.controls.map((n) => {
                const ck = ctlKey(n.c.control_id), cOpen = expanded.has(ck);
                return (
                  <li key={n.c.control_id} role="treeitem" aria-level={2} aria-expanded={n.enh.length ? cOpen : undefined} aria-selected={false} ref={reg(`n:${n.c.control_id}`)}
                    tabIndex={active === `n:${n.c.control_id}` ? 0 : -1} onFocus={(e) => e.target === e.currentTarget && setFocusKey(`n:${n.c.control_id}`)}
                    className="outline-none focus-visible:ring-2 focus-visible:ring-blue-600" data-filter-match={fit(n.c)} data-testid={`tree-control-${n.c.control_id}`}>
                    <Row c={n.c} level={2} dim={!fit(n.c)} words={words} hit={!!found?.matches.has(n.c.control_id)} sys={sys} openId={openId} onOpen={open}
                      toggle={n.enh.length ? <button tabIndex={-1} onClick={() => toggle(ck)} aria-label={`${cOpen ? "Collapse" : "Expand"} enhancements of ${idLabel(n.c)}`}
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded hover:bg-slate-200" data-testid={`tree-control-toggle-${n.c.control_id}`}>
                        {cOpen ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}</button> : <span className="w-8 shrink-0" />}
                      extra={n.enh.length ? <span className="text-[11px] text-slate-500">{n.enh.length} enh.</span> : null} />
                    {cOpen && <ul role="group" className="ml-[52px] border-l-2 border-slate-200 sm:ml-[60px]">{n.enh.map((e) => (
                      <li key={e.control_id} role="treeitem" aria-level={3} aria-selected={false} ref={reg(`n:${e.control_id}`)} tabIndex={active === `n:${e.control_id}` ? 0 : -1}
                        onFocus={(ev) => ev.target === ev.currentTarget && setFocusKey(`n:${e.control_id}`)} className="outline-none focus-visible:ring-2 focus-visible:ring-blue-600" data-filter-match={fit(e)} data-testid={`tree-enhancement-${e.control_id}`}>
                        <Row c={e} level={3} words={words} hit={!!found?.matches.has(e.control_id)} sys={sys} openId={openId} onOpen={open} />
                      </li>))}</ul>}
                  </li>);
              })}</ul>}
            </li>);
        })}
      </ul>
      {!sysId && <ControlDetailDrawer controlId={openId} onClose={closeDrawer} onNavigate={open} />}
    </div>
  );
}

function Row({ c, level, words, hit, sys, openId, onOpen, toggle, extra, dim }: { c: ControlSummary; level: number; words: string[]; hit: boolean; dim?: boolean; sys: Map<string, SysRow> | null;
  openId: string | null; onOpen: (id: string) => void; toggle?: React.ReactNode; extra?: React.ReactNode }) {
  const r = sys?.get(c.control_id), ap = sys ? applicability(r) : null;
  return (
    <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 py-1.5 pr-3 [content-visibility:auto] [contain-intrinsic-size:auto_40px]", level === 2 ? "pl-6 sm:pl-8" : "pl-3",
      hit && "bg-amber-50", openId === c.control_id && "bg-blue-50", dim && "iv-dimmed")}>
      {toggle}
      <button tabIndex={-1} onClick={() => onOpen(c.control_id)} className="flex min-h-[36px] min-w-0 flex-1 basis-[75%] flex-wrap items-center gap-x-2 text-left hover:underline sm:basis-auto" data-testid={`tree-open-${c.control_id}`}>
        <span className={cn("font-mono font-semibold", level === 2 ? "text-[13px] text-blue-900" : "text-[12px] text-blue-700")}>{idLabel(c)}</span>
        <span className={cn("min-w-0 break-words", c.is_withdrawn ? "text-slate-400 line-through" : level === 2 ? "text-slate-900" : "text-slate-700")}><Hl text={c.title} words={words} /></span>
      </button>
      {extra}
      {dim && <span className="text-[11px] italic text-slate-500" data-testid={`tree-context-${c.control_id}`}>shown for its enhancements – does not match the filter</span>}
      {level === 3 && <StatusPill tone="info">Enhancement</StatusPill>}
      {c.is_withdrawn && <span data-testid={`tree-withdrawn-${c.control_id}`}><StatusPill tone="neutral">Withdrawn</StatusPill></span>}
      {c.baselines.map((b) => <BaselinePill key={b} baseline={b} />)}
      {ap && <span className="text-[11px] text-slate-600" data-testid={`tree-status-${c.control_id}`}>
        {ap === "not_selected" ? "Not selected" : `${human(ap)} · ${human(r?.implementation_status)} · ${human(r?.assessment_status)}`}</span>}
    </div>);
}
