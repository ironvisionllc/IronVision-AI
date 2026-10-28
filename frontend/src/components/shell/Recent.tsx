import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

type Visit = { path: string; label: string; at: number };
const PATTERNS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^\/systems\/[^/]+\/controls\/([^/?#]+)/, (m) => `Control ${decodeURIComponent(m[1]).toUpperCase()}`],
  [/^\/findings\/([^/?#]+)/, () => "Finding"], [/^\/poams\/([^/?#]+)/, () => "POA&M"], [/^\/policy-auditor\/([^/?#]+)/, () => "Policy analysis"],
  [/^\/(?:systems\/[^/]+\/)?emass-import\/([^/?#]+)/, () => "Import review"], [/^\/assess\/workspace\/([^/?#]+)/, (m) => `Assessment ${decodeURIComponent(m[1]).toUpperCase()}`],
  [/^\/reviews\/([^/?#]+)/, () => "Review request"],
];
const key = (uid?: string) => `iv.recent.${uid || "anon"}`;

export function recentVisits(uid?: string): Visit[] {
  try { return JSON.parse(localStorage.getItem(key(uid)) || "[]"); } catch { return []; }
}

/** Records work objects (controls, findings, POA&Ms…) for "Continue where you left off" and "Recently viewed" (per user, this browser). */
export function useTrackVisits() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  useEffect(() => {
    const hit = PATTERNS.map(([re, f]) => { const m = pathname.match(re); return m ? f(m) : null; }).find(Boolean);
    if (!hit || !user) return;
    const list = [{ path: pathname, label: hit, at: Date.now() }, ...recentVisits(user ? user.id : undefined).filter((v) => v.path !== pathname)].slice(0, 8);
    localStorage.setItem(key(user ? user.id : undefined), JSON.stringify(list));
  }, [pathname, user]);
}

export function RecentlyViewed() {
  const { user } = useAuth();
  useLocation();
  const list = recentVisits((user || null)?.id).slice(0, 4);
  if (!list.length) return null;
  return (
    <div className="mt-3" data-testid="nav-recent">
      <div className="t-label iv-sb-muted px-5 pb-1 !text-[10px]">Recently viewed</div>
      <ul>{list.map((v) => <li key={v.path}><Link to={v.path} className="iv-nav-link !pl-6 !text-[12px]" data-testid="nav-recent-item">{v.label}</Link></li>)}</ul>
    </div>);
}
