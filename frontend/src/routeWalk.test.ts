import fs from "fs";
import path from "path";
import { NAV_ITEMS, activeNavId } from "@/lib/nav";

// Route walk (COMPAT.md): every route in App.tsx stays defined, every nav item points at a route, every route has a nav owner.
const app = fs.readFileSync(path.join(__dirname, "App.tsx"), "utf8");
const routes = Array.from(app.matchAll(/path="([^"]+)"/g)).map((m) => m[1]).filter((r) => r !== "*" && r !== "/*");
const LEGACY = ["/controls", "/catalog", "/systems", "/systems/new", "/systems/:id", "/systems/:id/controls", "/systems/:id/controls/:controlId", "/rmf/prepare", "/rmf/categorize",
  "/rmf/select", "/rmf/implement", "/rmf/assess", "/rmf/authorize", "/rmf/monitor", "/rmf-workflow", "/inheritance", "/inventory", "/ccis", "/policy-auditor", "/evidence-sources",
  "/evidence-ledger", "/reviews", "/test-results", "/mapping-review", "/poams", "/emass", "/traceability", "/import-center", "/portfolio", "/help", "/audit-log", "/admin", "/whitepaper"];
const match = (p: string) => routes.some((r) => new RegExp(`^${r.replace(/:[^/]+/g, "[^/]+")}$`).test(p));

test("every legacy route still resolves", () => {
  for (const r of LEGACY) expect([r, match(r.replace(/:[^/]+/g, "x"))]).toEqual([r, true]);
});

test("every nav item points at a defined route and new routes exist", () => {
  for (const n of NAV_ITEMS) expect([n.id, match(n.path)]).toEqual([n.id, true]);
  for (const r of ["/my-work", "/dashboard", "/assess/workspace", "/assess/workspace/ac-2", "/ux-proposal"]) expect([r, match(r)]).toEqual([r, true]);
});

test("deep links keep a sidebar owner", () => {
  for (const p of ["/systems/abc/controls/ac-2", "/findings/1", "/poams/1", "/systems/abc/emass-import/1", "/systems/abc/authorization", "/docs-center/x", "/reviews/1"])
    expect([p, Boolean(activeNavId(p))]).toEqual([p, true]);
});
