import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { StatusSection } from "./StatusSection";
import { WorkbenchFilters } from "@/pages/WorkbenchPage";
import { PolicyMappingsPanel } from "@/components/controls/PolicyMappings";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), put: jest.fn(), post: jest.fn() }, errorMessage: (e: { message: string }) => e.message, deniedInfo: () => null }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ can: () => true }) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn() } }));
const m = api as unknown as { get: jest.Mock; put: jest.Mock; post: jest.Mock };

const d = { assignment: { id: "a1", implementation_status: "planned", assessment_status: "not_assessed" }, status_last_changed: null };

test("status has its own Save: sends the new status, toasts, reloads", async () => {
  m.put.mockResolvedValue({ data: {} });
  const reload = jest.fn();
  render(<MemoryRouter><StatusSection systemId="s1" controlId="ra-5" d={d} reload={reload} /></MemoryRouter>);
  const save = screen.getByTestId("wb-status-save") as HTMLButtonElement;
  expect(save.disabled).toBe(true);                                  // nothing changed yet
  fireEvent.change(screen.getByTestId("wb-impl-status"), { target: { value: "partially_implemented" } });
  fireEvent.click(save);
  await waitFor(() => expect(reload).toHaveBeenCalled());
  expect(m.put).toHaveBeenCalledWith("/systems/s1/workbench/controls/ra-5/status", { implementation_status: "partially_implemented" });
  expect(toast.success).toHaveBeenCalled();
  expect(screen.getByTestId("wb-status-last-changed").textContent).toContain("Not changed");
});

test("status save failure shows an inline error", async () => {
  m.put.mockRejectedValue(new Error("Forbidden: implementation.write"));
  render(<MemoryRouter><StatusSection systemId="s1" controlId="ra-5" d={d} reload={jest.fn()} /></MemoryRouter>);
  fireEvent.change(screen.getByTestId("wb-impl-status"), { target: { value: "implemented" } });
  fireEvent.click(screen.getByTestId("wb-status-save"));
  expect((await screen.findByTestId("wb-status-error")).textContent).toContain("Forbidden");
});

function FiltersHarness() {
  const [p, setP] = useSearchParams();
  const loc = useLocation();
  return <><WorkbenchFilters params={p} set={(k, v) => setP((prev) => { const n = new URLSearchParams(prev); if (v) n.set(k, v); else n.delete(k); return n; })} /><div data-testid="qs">{loc.search}</div></>;
}

test("every workbench filter writes its URL param (deep-linkable, e.g. ?has_evidence=yes)", async () => {
  m.get.mockResolvedValue({ data: [{ family_id: "ac", family_title: "Access Control" }] });
  render(<MemoryRouter initialEntries={["/systems/s1/controls?has_evidence=yes"]}><FiltersHarness /></MemoryRouter>);
  expect((screen.getByTestId("filter-has_evidence") as HTMLSelectElement).value).toBe("yes");
  for (const [k, v] of [["implementation_status", "partially_implemented"], ["assessment_status", "satisfied"], ["responsibility", "inherited"],
    ["origin", "overlay"], ["monitoring_status", "failing"], ["evidence", "current"]]) {
    fireEvent.change(screen.getByTestId(`filter-${k}`), { target: { value: v } });
    expect(screen.getByTestId("qs").textContent).toContain(`${k}=${v}`);
  }
  await waitFor(() => expect((screen.getByTestId("filter-family") as HTMLSelectElement).options.length).toBe(2));
  fireEvent.change(screen.getByTestId("filter-family"), { target: { value: "ac" } });
  expect(screen.getByTestId("qs").textContent).toContain("family=ac");
  expect(screen.getByTestId("qs").textContent).toContain("has_evidence=yes");   // earlier filters are kept
});

test("Reject mapping requires a justification before calling the API", async () => {
  const data = { control_mappings: [{ id: "m1", control_id: "ra-3", status: "proposed", confidence: "Low", basis: "title", snippets: [], parts: [] }], mapping_history: [] };
  m.post.mockResolvedValue({ data: {} });
  render(<MemoryRouter><PolicyMappingsPanel policyId="p1" data={data} canMap reload={jest.fn()} setMsg={jest.fn()} /></MemoryRouter>);
  fireEvent.click(screen.getByTestId("mapping-reject-ra-3"));
  fireEvent.click(screen.getByTestId("reject-mapping-confirm"));
  expect(screen.getByTestId("reject-mapping-error").textContent).toContain("at least 10");
  expect(m.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByTestId("reject-mapping-justification"), { target: { value: "Not a risk assessment procedure" } });
  fireEvent.click(screen.getByTestId("reject-mapping-confirm"));
  await waitFor(() => expect(m.post).toHaveBeenCalledWith("/policies/p1/control-mappings/reject", { control_id: "ra-3", justification: "Not a risk assessment procedure" }));
});
