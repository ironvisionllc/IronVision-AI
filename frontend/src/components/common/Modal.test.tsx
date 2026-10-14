import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { Modal } from "./Modal";

// Regression: callers pass a fresh onClose each render; the modal must not re-grab focus on every keystroke.
function Harness() {
  const [v, setV] = useState("");
  const [open, setOpen] = useState(true);
  return open ? (
    <Modal title="Test" onClose={() => setOpen(false)} testId="m">
      <input data-testid="field" value={v} onChange={(e) => setV(e.target.value)} />
    </Modal>
  ) : <div data-testid="closed" />;
}

test("typing a multi-character string into a modal input keeps focus and full text", () => {
  render(<Harness />);
  const input = screen.getByTestId("field") as HTMLInputElement;
  act(() => input.focus());
  let typed = "";
  for (const ch of "Weakness text") {
    typed += ch;
    fireEvent.change(input, { target: { value: typed } });
    expect(document.activeElement).toBe(input);
  }
  expect(input.value).toBe("Weakness text");
});

test("Escape still closes with the latest onClose", () => {
  render(<Harness />);
  fireEvent.change(screen.getByTestId("field"), { target: { value: "x" } });
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByTestId("closed")).toBeTruthy();
});
