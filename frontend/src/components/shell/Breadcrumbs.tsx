import { Link, useLocation } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { activeNavId, NAV_GROUPS, NAV_ITEMS } from "@/lib/nav";
import { useSystems } from "@/context/SystemContext";
import { useEffect } from "react";
import { fmtControl } from "@/lib/format";

const GROUP_HOME: Record<string, string> = { start: "/rmf-workflow", prepare: "/rmf/prepare", categorize: "/rmf/categorize", select: "/rmf/select",
  implement: "/rmf/implement", assess: "/rmf/assess", authorize: "/rmf/authorize", monitor: "/rmf/monitor", tools: "/traceability" };

/** System › Step › Page – same on every page. */
export function Breadcrumbs() {
  const path = useLocation().pathname;
  const { systems, selectedId } = useSystems();
  const item = NAV_ITEMS.find((n) => n.id === activeNavId(path));
  const group = NAV_GROUPS.find((g) => g.key === item?.group);
  const sys = systems.find((s) => s.id === selectedId);
  const ctl = path.match(/\/(?:controls|workspace)\/([a-z]{2}-[\d.()a-z-]+)/i)?.[1];
  useEffect(() => { document.title = [ctl ? fmtControl(ctl) : item?.label, sys?.acronym || sys?.name, "IronVision AI"].filter(Boolean).join(" · "); }, [ctl, item?.label, sys?.acronym, sys?.name]);
  return (
    <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-1 text-[12px] text-slate-500" data-testid="breadcrumbs">
      {sys ? <Link to={`/systems/${sys.id}`} className="hover:underline" data-testid="crumb-system">{sys.acronym || sys.name}</Link> : <span>No system selected</span>}
      {group && <><ChevronRight className="h-3 w-3" /><Link to={GROUP_HOME[group.key]} className="hover:underline" title={group.help} data-testid="crumb-step">{group.label}</Link></>}
      {item && <><ChevronRight className="h-3 w-3" /><span className="text-slate-700" data-testid="crumb-page">{item.label}</span></>}
    </nav>);
}
