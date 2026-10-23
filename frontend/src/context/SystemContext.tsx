import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SystemRecord } from "@/lib/types";

const KEY = "aegis.selected_system";

interface SystemState {
  systems: SystemRecord[];
  loaded: boolean;
  selectedId: string;
  select: (id: string) => void;
  refresh: () => Promise<void>;
}

const SystemContext = createContext<SystemState | undefined>(undefined);

export function SystemProvider({ children }: { children: ReactNode }) {
  const [systems, setSystems] = useState<SystemRecord[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState(localStorage.getItem(KEY) || "");

  const refresh = () => api.get<SystemRecord[]>("/systems")
    .then((r) => { setSystems(r.data); if (!localStorage.getItem(KEY) && r.data[0]) select((r.data.find((s) => s.acronym === "LTP") ?? r.data[0]).id); })
    .catch(() => setSystems([]))
    .finally(() => setLoaded(true));
  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const select = (id: string) => {
    setSelectedId(id);
    localStorage.setItem(KEY, id);
  };

  return <SystemContext.Provider value={{ systems, loaded, selectedId, select, refresh }}>{children}</SystemContext.Provider>;
}

export function useSystems(): SystemState {
  const ctx = useContext(SystemContext);
  if (!ctx) throw new Error("useSystems must be used within SystemProvider");
  return ctx;
}
