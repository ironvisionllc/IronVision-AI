import { useCallback, useEffect, useState } from "react";
import { api, deniedInfo, Denied, errorMessage } from "@/lib/api";

export function useApi<T>(url: string | null, params?: Record<string, unknown>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState<Denied | null>(null);
  const [loading, setLoading] = useState(true);
  const key = JSON.stringify(params ?? {});
  const reload = useCallback(() => {
    if (!url) return;
    setLoading(true);
    api.get<T>(url, { params: JSON.parse(key) })
      .then((r) => { setData(r.data); setError(""); setDenied(null); })
      .catch((e) => { setError(errorMessage(e)); setDenied(deniedInfo(e)); })
      .finally(() => setLoading(false));
  }, [url, key]);
  useEffect(reload, [reload]);
  useEffect(() => {
    window.addEventListener("iv:identity", reload);
    return () => window.removeEventListener("iv:identity", reload);
  }, [reload]);
  return { data, error, denied, reload, loading };
}

export type Row = Record<string, any>;
