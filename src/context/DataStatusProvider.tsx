import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { apiGet } from '../lib/api';
import type { DataStatusResponse } from '../lib/apiTypes';
import { DataStatusContext, type DataStatusValue } from './dataStatus';

/** How often to re-poll the backend's source health. */
const POLL_MS = 60_000;

/**
 * Polls /api/data/status and hands the result to the whole app.
 *
 * Nothing here throws or blocks. If the backend is unreachable the provider
 * reports `online: false` and every screen carries on with the data it shipped
 * with. The point is that the UI can say which of the two it is showing.
 */
export default function DataStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<DataStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    let cancelled = false;

    const poll = () => {
      apiGet<DataStatusResponse>('/api/data/status')
        .then(res => {
          if (cancelled) return;
          setStatus(res);
          setError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setStatus(null);
          setError(err instanceof Error ? err.message : String(err));
        });
    };

    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [tick]);

  const value = useMemo<DataStatusValue>(() => {
    const sources = status?.sources ?? [];
    return {
      status,
      online: status !== null,
      sources,
      staleSources: sources.filter(s => s.is_stale).map(s => s.source),
      proxySources: sources.filter(s => s.is_proxy).map(s => s.source),
      error,
      refresh,
    };
  }, [status, error, refresh]);

  return <DataStatusContext.Provider value={value}>{children}</DataStatusContext.Provider>;
}
