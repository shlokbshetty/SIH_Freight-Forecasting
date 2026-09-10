import { createContext, useContext } from 'react';
import type { DataStatusResponse, SourceStatus } from '../lib/apiTypes';

export interface DataStatusValue {
  /** Null until the first poll settles, or while the backend is unreachable. */
  status: DataStatusResponse | null;
  /** True when the backend answered. False means every screen is on bundled data. */
  online: boolean;
  sources: SourceStatus[];
  staleSources: string[];
  proxySources: string[];
  error: string | null;
  refresh: () => void;
}

export const DataStatusContext = createContext<DataStatusValue>({
  status: null,
  online: false,
  sources: [],
  staleSources: [],
  proxySources: [],
  error: null,
  refresh: () => {},
});

export function useDataStatus(): DataStatusValue {
  return useContext(DataStatusContext);
}
