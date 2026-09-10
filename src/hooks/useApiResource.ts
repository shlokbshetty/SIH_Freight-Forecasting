import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../lib/api';

export type DataOrigin = 'live' | 'bundled' | 'loading';

export interface ApiResource<T> {
  data: T;
  /** Where `data` came from. "bundled" means the backend could not be reached. */
  origin: DataOrigin;
  error: string | null;
  refresh: () => void;
}

/**
 * Fetch from the backend, fall back to bundled data.
 *
 * `fallback` is what the app shipped with. It is returned immediately, so a
 * screen paints before the network settles and keeps painting if the network
 * never does. `origin` tells the UI which of the two it is looking at.
 */
export function useApiResource<T>(
  fetcher: () => Promise<T>,
  fallback: T,
  deps: unknown[],
): ApiResource<T> {
  const [data, setData] = useState<T>(fallback);
  const [origin, setOrigin] = useState<DataOrigin>('loading');
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // Keep the newest fetcher without making it a dependency, so callers can pass
  // an inline closure without re-running the effect on every render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    let cancelled = false;
    setOrigin('loading');

    fetcherRef.current()
      .then(result => {
        if (cancelled) return;
        setData(result);
        setOrigin('live');
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setData(fallback);
        setOrigin('bundled');
        setError(err instanceof ApiError ? err.message : String(err));
      });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const refresh = useCallback(() => setTick(t => t + 1), []);
  return { data, origin, error, refresh };
}
