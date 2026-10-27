import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ImportButton, importCenterHref } from "./ImportButton";

test("old entry points open the Import Center pre-set to system and type", () => {
  expect(importCenterHref("s1", "hwsw")).toBe("/systems/s1/import-center?type=hwsw");
  expect(importCenterHref(null, "poam")).toBe("/import-center?type=poam");
  expect(importCenterHref()).toBe("/import-center");
  render(<MemoryRouter><ImportButton systemId="abc" type="control_information" testId="x-btn" /></MemoryRouter>);
  expect(screen.getByTestId("x-btn").getAttribute("href")).toBe("/systems/abc/import-center?type=control_information");
});
