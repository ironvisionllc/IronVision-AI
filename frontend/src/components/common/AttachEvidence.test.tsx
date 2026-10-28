import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api } from "@/lib/api";
import { AttachEvidence } from "./AttachEvidence";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), put: jest.fn(), post: jest.fn() }, errorMessage: (e: { message: string }) => e.message, deniedInfo: () => null }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ can: () => true }) }));
const m = api as unknown as { get: jest.Mock; post: jest.Mock };

test("Attach evidence opens an in-app dialog with the target control, uploads, links and shows Completed – next", async () => {
  m.post.mockResolvedValueOnce({ data: { evidence_id: "ev1", status: "received" } }).mockResolvedValueOnce({ data: { linked: true } });
  render(<MemoryRouter><AttachEvidence systemId="s1" controlIds={["ac-2"]} testId="ae" /></MemoryRouter>);
  fireEvent.click(screen.getByTestId("ae-btn"));
  expect(screen.getByTestId("ae-dialog")).toBeTruthy();
  expect(screen.getByTestId("ae-target").textContent).toContain("AC-2");
  expect(screen.getByTestId("ae-dropzone")).toBeTruthy();
  fireEvent.change(screen.getByTestId("ae-input"), { target: { files: [new File(["x"], "scan.json")] } });
  await waitFor(() => expect(screen.getByTestId("ae-done")).toBeTruthy());
  expect(m.post).toHaveBeenNthCalledWith(1, "/systems/s1/uploads", expect.any(FormData), expect.anything());
  expect(m.post).toHaveBeenNthCalledWith(2, "/systems/s1/controls/ac-2/evidence-links", { evidence_id: "ev1" });
  expect(screen.queryByTestId("ae-dialog")).toBeNull();
});
