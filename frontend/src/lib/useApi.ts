"use client";

import { useCallback, useEffect, useState } from "react";
import { api, cachedResponse } from "./client";

/** GET a JSON endpoint with loading / error state and a reload function.
 *  A page seen before shows its last data at once and refreshes it in the background. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(() => (path ? (cachedResponse<T>(path) ?? null) : null));
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(!!path);
  const load = useCallback(async () => {
    if (!path) return;
    const last = cachedResponse<T>(path);
    if (last !== undefined) setData(last);
    setLoading(true);
    setError("");
    try {
      setData(await api<T>(path, { timeoutMs: 60000 }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    load();
  }, [load]);
  return { data, error, loading, reload: load, setData };
}
