import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api } from "@/lib/api";
import type { ControlSummary } from "@/lib/types";
import { allKeys, buildTree, filterTree, matcher, normalizeQuery, passes, pathTo, searchTree, NO_FILTERS, loadState } from "@/lib/catalogTree";
import { CatalogTree } from "./CatalogTree";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn() }, errorMessage: (e: { message: string }) => e.message }));
jest.mock("@/context/SystemContext", () => ({ useSystems: () => ({ systems: [{ id: "s1", name: "Raven" }], loaded: true }) }));
jest.mock("./ControlDetailDrawer", () => ({ ControlDetailDrawer: ({ controlId }: { controlId: string | null }) => (controlId ? <div data-testid="drawer">{controlId}</div> : null) }));
const m = api as unknown as { get: jest.Mock };

const C = (id: string, title: string, o: Partial<ControlSummary> = {}): ControlSummary => ({
  control_id: id, label: null, title, family_id: id.split("-")[0], family_title: id.startsWith("ac") ? "Access Control" : "Audit and Accountability",
  is_enhancement: id.includes("."), is_withdrawn: false, parent_control_id: id.includes(".") ? id.split(".")[0] : null, sort_id: id, baselines: ["moderate"], ...o });
const ITEMS = [C("ac-1", "Policy and Procedures"), C("ac-2", "Account Management"), C("ac-2.1", "Automated System Account Management"),
  C("ac-2.10", "Shared and Group Account Credential Change", { is_withdrawn: true, baselines: [] }), C("ac-17", "Remote Access"), C("au-2", "Event Logging", { baselines: ["low"] })];

test("tree is derived from catalog fields: family → base control → enhancement; withdrawn only when shown", () => {
  const t = buildTree(ITEMS, false);
  expect(t.map((f) => [f.id, f.base, f.enhancements])).toEqual([["ac", 3, 1], ["au", 1, 0]]);
  expect(t[0].controls.find((n) => n.c.control_id === "ac-2")!.enh.map((e) => e.control_id)).toEqual(["ac-2.1"]);
  expect(buildTree(ITEMS, true)[0].controls.find((n) => n.c.control_id === "ac-2")!.enh.map((e) => e.control_id)).toEqual(["ac-2.1", "ac-2.10"]);
  expect(pathTo(t, "ac-2.1")).toEqual(["f:ac", "c:ac-2"]);
  expect(allKeys(t)).toEqual(["f:ac", "c:ac-2", "f:au"]);
});

test("search normalisation accepts AC-2(1), ac-2.1, AC-02(01) and CCI forms", () => {
  for (const q of ["AC-2(1)", "ac-2.1", "AC-02(01)", " ac-02.01 "]) expect(normalizeQuery(q).id).toBe("ac-2.1");
  expect(normalizeQuery("AC-17").id).toBe("ac-17");
  expect(normalizeQuery("cci-15").cci).toBe("CCI-000015");
  expect(normalizeQuery("CCI-000015").cci).toBe("CCI-000015");
  expect(normalizeQuery("remote access").id).toBeNull();
  const t = buildTree(ITEMS, false);
  const r = searchTree(t, matcher("AC-02(01)", null)!);
  expect([...r.matches]).toEqual(["ac-2.1"]);
  expect([...r.expand].sort()).toEqual(["c:ac-2", "f:ac"]);
  expect([...searchTree(t, matcher("CCI-000015", { "CCI-000015": ["ac-2"] })!).matches]).toEqual(["ac-2"]);
  expect([...searchTree(t, matcher("remote", null)!).matches]).toEqual(["ac-17"]);
});

test("filters: catalog baseline always; system filters use the system rows; parents kept for matching enhancements", () => {
  const t = buildTree(ITEMS, false);
  expect(filterTree(t, (c) => passes(c, { ...NO_FILTERS, baseline: "low" }, null)).map((f) => f.id)).toEqual(["au"]);
  const sys = new Map([["ac-2.1", { control_id: "ac-2.1", implementation_status: "implemented", assessment_status: "satisfied", responsibility: "system", origin: "baseline" }],
    ["ac-2", { control_id: "ac-2", implementation_status: "planned", assessment_status: "not_assessed", responsibility: "inherited", origin: "overlay" }]]);
  const impl = filterTree(t, (c) => passes(c, { ...NO_FILTERS, implementation_status: "implemented" }, sys));
  expect(impl[0].controls.map((n) => [n.c.control_id, n.enh.map((e) => e.control_id)])).toEqual([["ac-2", ["ac-2.1"]]]);
  expect(filterTree(t, (c) => passes(c, { ...NO_FILTERS, applicability: "inherited" }, sys))[0].controls.map((n) => n.c.control_id)).toEqual(["ac-2"]);
  expect(filterTree(t, (c) => passes(c, { ...NO_FILTERS, applicability: "not_selected" }, sys)).flatMap((f) => f.controls.map((n) => n.c.control_id))).toEqual(["ac-1", "ac-17", "au-2"]);
  expect(filterTree(t, (c) => passes(c, { ...NO_FILTERS, baseline: "overlay" }, sys))[0].controls.map((n) => n.c.control_id)).toEqual(["ac-2"]);
});

const renderTree = (url = "/catalog") => render(<MemoryRouter initialEntries={[url]}><CatalogTree /></MemoryRouter>);

beforeEach(() => { sessionStorage.clear(); m.get.mockReset(); m.get.mockResolvedValue({ data: { items: ITEMS } }); });

test("families start collapsed; expand/collapse, expand all, keyboard and aria-expanded", async () => {
  renderTree();
  const fam = await screen.findByTestId("tree-family-ac");
  expect(fam.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByTestId("tree-control-ac-2")).toBeNull();
  fireEvent.click(screen.getByTestId("tree-family-toggle-ac"));
  expect(fam.getAttribute("aria-expanded")).toBe("true");
  expect(screen.queryByTestId("tree-enhancement-ac-2.1")).toBeNull();
  fireEvent.click(screen.getByTestId("tree-control-toggle-ac-2"));
  expect(screen.getByTestId("tree-enhancement-ac-2.1").textContent).toContain("AC-2(1)");
  expect(screen.getByTestId("tree-enhancement-ac-2.1").textContent).toContain("Enhancement");
  fireEvent.click(screen.getByTestId("catalog-tree-collapse-all"));
  expect(screen.queryByTestId("tree-control-ac-2")).toBeNull();
  fireEvent.click(screen.getByTestId("catalog-tree-expand-all"));
  expect(screen.getByTestId("tree-enhancement-ac-2.1")).toBeTruthy();
  fireEvent.click(screen.getByTestId("catalog-tree-collapse-all"));
  act(() => screen.getByTestId("tree-family-ac").focus());
  fireEvent.keyDown(screen.getByTestId("catalog-tree"), { key: "ArrowRight" });
  expect(screen.getByTestId("tree-family-ac").getAttribute("aria-expanded")).toBe("true");
  fireEvent.keyDown(screen.getByTestId("catalog-tree"), { key: "ArrowLeft" });
  expect(screen.getByTestId("tree-family-ac").getAttribute("aria-expanded")).toBe("false");
});

test("search auto-expands and counts matches; clearing restores the previous expansion; state persists", async () => {
  renderTree();
  await screen.findByTestId("tree-family-ac");
  fireEvent.click(screen.getByTestId("tree-family-toggle-au"));
  fireEvent.change(screen.getByTestId("catalog-tree-search"), { target: { value: "ac-02(01)" } });
  await waitFor(() => expect(screen.getByTestId("tree-enhancement-ac-2.1")).toBeTruthy());
  expect(screen.getByTestId("catalog-tree-count").textContent).toContain("1 match");
  expect(screen.queryByTestId("tree-family-au")).toBeNull();
  fireEvent.change(screen.getByTestId("catalog-tree-search"), { target: { value: "" } });
  await waitFor(() => expect(screen.getByTestId("tree-family-ac").getAttribute("aria-expanded")).toBe("false"));
  expect(screen.getByTestId("tree-family-au").getAttribute("aria-expanded")).toBe("true");
  expect(loadState("")!.expanded).toEqual(["f:au"]);
});

test("deep link auto-expands family and parent and opens details; system filters disabled without a system", async () => {
  renderTree("/catalog?control=ac-2.1");
  await waitFor(() => expect(screen.getByTestId("tree-enhancement-ac-2.1")).toBeTruthy());
  expect(screen.getByTestId("drawer").textContent).toContain("ac-2.1");
  expect((screen.getByTestId("catalog-tree-filter-implementation_status") as HTMLSelectElement).disabled).toBe(true);
  expect((screen.getByTestId("catalog-tree-filter-baseline") as HTMLSelectElement).disabled).toBe(false);
});
