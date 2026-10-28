import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";

type Next = { label: string; link: string };
/** "Completed – next: …" for every import / analysis: where the data went and the one recommended next action. */
export function nextFor(kind: string, c: Record<string, number | undefined> = {}): Next {
  if (["control_information", "implementation_plan"].includes(kind))
    return (c.blocked ?? 0) > 0 ? { label: `${c.blocked} control(s) need SLCM fields – set them in the Continuous Monitoring Strategy`, link: "/rmf/select" }
      : { label: "Review the imported controls in the Control Workbench", link: "/controls" };
  const map: Record<string, Next> = {
    test_results: { label: "Assess the imported results in the SCA workspace", link: "/assess/workspace" },
    slcm: { label: "Ask the ISSM to approve the monitoring strategy draft", link: "/rmf/select" },
    categorization: { label: "The categorization proposal awaits AO approval in Categorize", link: "/rmf/categorize" },
    system_details: { label: "Check the system profile in Prepare", link: "/rmf/prepare" },
    ppsm: { label: "Review ports, protocols and services in Prepare", link: "/rmf/prepare" },
    hwsw: { label: "Review the HW/SW inventory", link: "/inventory" }, inventory: { label: "Review the HW/SW inventory", link: "/inventory" },
    policy: { label: "Review the mapping suggestions", link: "/mapping-review" },
    scan: { label: "Create POA&Ms for the new findings", link: "/poams" }, stig: { label: "Review the findings and create POA&Ms", link: "/mapping-review" },
    nessus: { label: "Create POA&Ms for the new findings", link: "/poams" },
  };
  return map[kind] ?? { label: "Open the system dashboard", link: "/dashboard" };
}

export function CompletedNext({ kind, counts, next, testId = "completed-next" }: { kind?: string; counts?: Record<string, number | undefined>; next?: Next; testId?: string }) {
  const n = next ?? nextFor(kind ?? "", counts);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] text-emerald-900" role="status" data-testid={testId}>
      <CheckCircle2 className="h-4 w-4" aria-hidden /><b>Completed</b> – next: <Link className="font-semibold underline" to={n.link} data-testid={`${testId}-link`}>{n.label} →</Link>
    </div>);
}
