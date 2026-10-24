import { render, screen } from "@testing-library/react";
import { ConfidenceBadge } from "./SideBySideReview";

test("confidence badge shows evidence-based confidence and direct vs inferred", () => {
  render(<ConfidenceBadge m={{ control_id: "ac-2", evidence_confidence: "High", evidence_kind: "direct", confidence_explanation: "quotes the ID" }} />);
  expect(screen.getByTestId("evidence-confidence-ac-2").textContent).toBe("High · direct evidence");
});

test("mapping without supporting text is labelled for manual review", () => {
  render(<ConfidenceBadge m={{ control_id: "sc-8", evidence_confidence: "Requires manual review", evidence_kind: "none" }} />);
  expect(screen.getByTestId("evidence-confidence-sc-8").textContent).toBe("Requires manual review");
});
