import { AlertTriangle, Database, WifiOff } from 'lucide-react';
import type { DataOrigin } from '../../hooks/useApiResource';
import './DataOriginNotice.css';

interface Props {
  origin: DataOrigin;
  error?: string | null;
  /** Sources the backend reported as serving cached values. */
  stale?: string[];
  /** What this screen falls back to when the backend is unreachable. */
  bundledLabel?: string;
}

/**
 * One line saying where the numbers came from.
 *
 * Deliberately not an error state. Bundled data is a working mode, not a
 * failure, and the screen behind this notice is fully usable. What is not
 * acceptable is showing bundled or stale numbers as though they were live.
 */
export default function DataOriginNotice({ origin, error, stale = [], bundledLabel }: Props) {
  if (origin === 'loading') return null;

  if (origin === 'bundled') {
    return (
      <div className="origin origin--bundled">
        <WifiOff size={13} />
        <span>
          {bundledLabel ?? 'Backend unreachable. Showing the data bundled with the app.'}
          {error && <em className="origin__detail"> {error}</em>}
        </span>
      </div>
    );
  }

  if (stale.length) {
    return (
      <div className="origin origin--stale">
        <AlertTriangle size={13} />
        <span>
          Live, but {stale.length} source{stale.length === 1 ? '' : 's'} serving cached values:{' '}
          <b>{stale.join(', ')}</b>
        </span>
      </div>
    );
  }

  return (
    <div className="origin origin--live">
      <Database size={13} />
      <span>Live from the ingestion cache.</span>
    </div>
  );
}
