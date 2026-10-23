import { render, screen } from "@testing-library/react";
import { SourceBadge } from "./SourceBadge";

test("a mock-adapter source renders the MOCKED source badge", () => {
  render(<SourceBadge label="MOCKED source" />);
  const b = screen.getByTestId("mocked-badge");
  expect(b.textContent).toBe("MOCKED source");
  expect(b.className).toContain("bg-rose-600");
});

test("a real file import is not labelled as mocked", () => {
  render(<SourceBadge label="Scan/checklist file import" />);
  expect(screen.queryByTestId("mocked-badge")).toBeNull();
  expect(screen.getByTestId("source-badge").textContent).toBe("Scan/checklist file import");
});
