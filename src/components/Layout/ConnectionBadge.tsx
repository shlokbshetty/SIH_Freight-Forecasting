import { Link } from 'react-router-dom';
import { useDataStatus } from '../../context/dataStatus';
import './ConnectionBadge.css';

/**
 * Says where the numbers on screen are coming from.
 *
 * Three states, and the difference between them matters commercially:
 *   live      backend answered, every source fresh
 *   stale     backend answered, but some sources are serving cached values
 *   bundled   backend unreachable, screens are on the data shipped with the app
 */
export default function ConnectionBadge() {
  const { online, staleSources, proxySources, status } = useDataStatus();

  if (!online) {
    return (
      <Link to="/risk" className="conn conn--offline" title="Backend unreachable. Screens are showing the data bundled with the app.">
        <span className="dot dot-amber" />
        <span>Bundled data</span>
      </Link>
    );
  }

  const stale = staleSources.length;
  const title = [
    status?.snapshot_provenance ? `Snapshot: ${status.snapshot_provenance}` : null,
    stale ? `Stale: ${staleSources.join(', ')}` : 'All sources fresh',
    proxySources.length ? `Proxy sources: ${proxySources.join(', ')}` : null,
  ].filter(Boolean).join(' · ');

  return (
    <Link to="/risk" className={`conn ${stale ? 'conn--stale' : 'conn--live'}`} title={title}>
      <span className={`dot ${stale ? 'dot-amber' : 'dot-green'}`} />
      <span>{stale ? `${stale} stale` : 'Live'}</span>
    </Link>
  );
}
