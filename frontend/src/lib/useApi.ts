import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";

export function useApi<T>(url: string | null, params?: Record<string, unknown>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const key = JSON.stringify(params ?? {});
  const reload = useCallback(() => {
    if (!url) return;
    api.get<T>(url, { params: JSON.parse(key) }).then((r) => { setData(r.data); setError(""); }).catch((e) => setError(errorMessage(e)));
  }, [url, key]);
  useEffect(reload, [reload]);
  return { data, error, reload };
}

export type Row = Record<string, any>;
