import { useMemo } from 'react';
import {
  AlertTriangle, Anchor, CheckCircle, CloudRain, Database, RefreshCw, TrendingUp,
} from 'lucide-react';
import { apiGet } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { useDataStatus } from '../context/dataStatus';
import DataOriginNotice from '../components/common/DataOriginNotice';
import './RiskAlerts.css';

type Severity = 'high' | 'medium' | 'low';

interface Alert {
  id: string;
  severity: Severity;
  icon: typeof AlertTriangle;
  title: string;
  detail: string;
  source: string;
}

interface SeriesPayload {
  as_of: string;
  series: Record<string, {
    adapter: string;
    source: string;
    is_proxy: boolean;
    points: { date: string; value: number }[];
  }>;
}

const EMPTY_SERIES: SeriesPayload = { as_of: '', series: {} };

const SEV_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };
const SEV_BADGE: Record<Severity, string> = { high: 'badge-red', medium: 'badge-amber', low: 'badge-green' };

/** Waiting beyond this many days is worth waking someone up about. */
const CONGESTION_HIGH_D = 5;
const CONGESTION_MEDIUM_D = 3;

/** Baltic move over this share, week on week, is a market event. */
const BDI_MOVE_HIGH = 0.08;

const last = (points: { value: number }[] | undefined) =>
  points && points.length ? points[points.length - 1].value : null;

function buildAlerts(payload: SeriesPayload): Alert[] {
  const alerts: Alert[] = [];
  const series = payload.series ?? {};

  // ── Berth queues ───────────────────────────────────────────────────────────
  for (const [metric, entry] of Object.entries(series)) {
    if (!metric.startsWith('congestion.') || !metric.endsWith('.wait_days')) continue;
    const port = metric.split('.')[1];
    const wait = last(entry.points);
    if (wait === null || wait < CONGESTION_MEDIUM_D) continue;

    const anchored = last(series[`congestion.${port}.vessels_at_anchor`]?.points);
    alerts.push({
      id: `congestion-${port}`,
      severity: wait >= CONGESTION_HIGH_D ? 'high' : 'medium',
      icon: Anchor,
      title: `Berth queue at ${port}`,
      detail:
        `Average wait ${wait.toFixed(1)} days` +
        (anchored !== null ? `, ${Math.round(anchored)} vessels at anchor.` : '.') +
        ' Price the waiting into any fixture discharging here.',
      source: entry.source,
    });
  }

  // ── Weather stopping cargo work ────────────────────────────────────────────
  for (const [metric, entry] of Object.entries(series)) {
    if (!metric.startsWith('weather.') || !metric.endsWith('.work_stopped')) continue;
    const port = metric.split('.')[1];
    // Count forward-looking days flagged, not the whole window.
    const ahead = entry.points.slice(-14);
    const stopped = ahead.filter(p => p.value >= 1).length;
    if (stopped < 2) continue;

    const wind = last(series[`weather.${port}.wind_kmh`]?.points);
    alerts.push({
      id: `weather-${port}`,
      severity: stopped >= 5 ? 'high' : 'medium',
      icon: CloudRain,
      title: `Weather disruption forecast at ${port}`,
      detail:
        `${stopped} of the next 14 days forecast above the rain threshold for open-berth cargo work` +
        (wind !== null ? `, winds to ${Math.round(wind)} km/h.` : '.'),
      source: entry.source,
    });
  }

  // ── Market move ────────────────────────────────────────────────────────────
  const bdi = series['baltic.bdi']?.points ?? [];
  if (bdi.length > 6) {
    const now = bdi[bdi.length - 1].value;
    const weekAgo = bdi[Math.max(0, bdi.length - 6)].value;
    const move = weekAgo > 0 ? (now - weekAgo) / weekAgo : 0;
    if (Math.abs(move) >= BDI_MOVE_HIGH) {
      alerts.push({
        id: 'bdi-move',
        severity: Math.abs(move) >= BDI_MOVE_HIGH * 1.5 ? 'high' : 'medium',
        icon: TrendingUp,
        title: `Baltic proxy ${move > 0 ? 'up' : 'down'} ${Math.abs(move * 100).toFixed(1)}% on the week`,
        detail:
          `Index proxy at ${now.toFixed(0)}, from ${weekAgo.toFixed(0)} five sessions ago. ` +
          (move > 0
            ? 'Locking a multi-voyage rate gets more expensive the longer this runs.'
            : 'A softening market argues for staying on spot.'),
        source: series['baltic.bdi'].source,
      });
    }
  }

  return alerts.sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);
}

export default function RiskAlerts() {
  const { sources, online, refresh, status } = useDataStatus();

  const feed = useApiResource<SeriesPayload>(
    () => apiGet<SeriesPayload>(
      '/api/series?prefix=congestion&days=7',
    ).then(async congestion => {
      // Three namespaces, three calls, merged. Each is allowed to fail on its
      // own so one missing adapter does not blank the whole screen.
      const merged: SeriesPayload = { as_of: congestion.as_of, series: { ...congestion.series } };
      for (const path of ['/api/series?prefix=weather&days=21', '/api/series?metrics=baltic.bdi&days=30']) {
        try {
          const extra = await apiGet<SeriesPayload>(path);
          Object.assign(merged.series, extra.series);
        } catch {
          /* a missing namespace is not fatal here */
        }
      }
      return merged;
    }),
    EMPTY_SERIES,
    [],
  );

  const alerts = useMemo(() => buildAlerts(feed.data), [feed.data]);
  const staleCount = sources.filter(s => s.is_stale).length;

  return (
    <div className="page-content risk-page">
      <div className="risk-head">
        <div>
          <h1>Risk &amp; Data Health</h1>
          <p>Disruptions derived from live data, and the state of every source behind it.</p>
        </div>
        <button className="btn btn-ghost" onClick={() => { refresh(); feed.refresh(); }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <DataOriginNotice
        origin={feed.origin}
        error={feed.error}
        stale={feed.data.series ? sources.filter(s => s.is_stale).map(s => s.source) : []}
        bundledLabel="Backend unreachable. Alerts are derived from live data only, so none are shown."
      />

      {/* ── Derived alerts ──────────────────────────────────────────────── */}
      <section className="risk-section">
        <p className="card-title">
          Active alerts {alerts.length > 0 && <span className="risk-count">{alerts.length}</span>}
        </p>

        {alerts.length === 0 ? (
          <div className="card risk-empty">
            <CheckCircle size={16} />
            <div>
              <b>{online ? 'Nothing flagged' : 'No live data'}</b>
              <p>
                {online
                  ? 'No berth queue, weather window or market move is over threshold right now.'
                  : 'Alerts come from the ingestion cache. Start the backend to populate them.'}
              </p>
            </div>
          </div>
        ) : (
          <div className="risk-list">
            {alerts.map(({ id, severity, icon: Icon, title, detail, source }) => (
              <div key={id} id={id} className={`card risk-item risk-item--${severity}`}>
                <div className={`risk-item__icon risk-item__icon--${severity}`}>
                  <Icon size={16} />
                </div>
                <div className="risk-item__body">
                  <div className="risk-item__head">
                    <span className="risk-item__title">{title}</span>
                    <span className={`badge ${SEV_BADGE[severity]}`}>{severity.toUpperCase()}</span>
                  </div>
                  <p className="risk-item__detail">{detail}</p>
                  <p className="risk-item__source mono">{source}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Source health ───────────────────────────────────────────────── */}
      <section className="risk-section">
        <div className="risk-section__head">
          <p className="card-title">
            <Database size={12} /> Source health
          </p>
          {status?.snapshot_provenance && (
            <span className="risk-provenance mono">snapshot: {status.snapshot_provenance}</span>
          )}
        </div>

        <div className="card risk-table-card">
          {!online ? (
            <p className="risk-offline">
              Backend unreachable, so source health cannot be read. Every screen is running on
              the data bundled with the app.
            </p>
          ) : (
            <div className="risk-table-scroll">
              <table className="risk-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>What it is</th>
                    <th className="risk-num">Rows</th>
                    <th className="risk-num">Age</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map(s => (
                    <tr key={s.source}>
                      <td className="risk-table__name">
                        {s.source}
                        {s.is_proxy && <span className="risk-proxy" title="Stands in for something it is not">proxy</span>}
                      </td>
                      <td className="risk-table__label">
                        {s.source_label ?? '—'}
                        {s.notes.length > 0 && (
                          <span className="risk-table__note">{s.notes.join(' · ')}</span>
                        )}
                      </td>
                      <td className="risk-num mono">{s.row_count.toLocaleString('en-US')}</td>
                      <td className="risk-num mono">
                        {s.age_minutes === null
                          ? '—'
                          : s.age_minutes < 90
                            ? `${Math.round(s.age_minutes)}m`
                            : `${(s.age_minutes / 60).toFixed(1)}h`}
                      </td>
                      <td>
                        <span className={`badge ${s.is_stale ? 'badge-amber' : 'badge-green'}`}>
                          {s.is_stale ? 'stale' : 'fresh'}
                        </span>
                        {s.error && <span className="risk-table__error" title={s.error}>{s.error}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {online && staleCount > 0 && (
          <p className="risk-footnote">
            A stale source is serving its last known values. That is the designed behaviour, not an
            outage: the number on screen is real, it is just older than it looks.
          </p>
        )}
      </section>
    </div>
  );
}
