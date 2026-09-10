import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, CalendarClock, Ship, TrendingDown, TrendingUp,
} from 'lucide-react';
import { apiGet } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { useDataStatus } from '../context/dataStatus';
import { fallbackMarketSeries, fallbackPorts } from '../lib/fallbacks';
import type { PortsResponse } from '../lib/apiTypes';
import type { BundledSeries } from '../lib/fallbacks';
import DataOriginNotice from '../components/common/DataOriginNotice';
import { VESSEL_CLASSES, VESSEL_SPECS } from '../data/vessels';
import './CommandCenter.css';

/** Metrics the home screen leads with. */
const HEADLINE_METRICS = [
  'baltic.bdi',
  'bunker.vlsfo.singapore',
  'macro.usdinr',
  'commodity.coal.api2',
  'freight.rate.handysize',
  'freight.rate.supramax',
  'freight.rate.panamax',
  'freight.rate.capesize',
].join(',');

function lastAndPrior(points: { value: number }[] | undefined, back = 5) {
  if (!points || points.length === 0) return { now: null as number | null, move: null as number | null };
  const now = points[points.length - 1].value;
  const prior = points[Math.max(0, points.length - 1 - back)]?.value;
  const move = prior && prior !== 0 ? ((now - prior) / prior) * 100 : null;
  return { now, move };
}

/** Standing congestion level to a signal tone, used when no live wait is known. */
function capTone(level: string): string {
  return level === 'high' ? 'red' : level === 'medium' ? 'amber' : 'green';
}

export default function CommandCenter() {
  const navigate = useNavigate();
  const { sources, online } = useDataStatus();

  const market = useApiResource<BundledSeries>(
    () => apiGet<BundledSeries>(`/api/series?metrics=${HEADLINE_METRICS}&days=30`),
    fallbackMarketSeries(),
    [],
  );

  const ports = useApiResource<PortsResponse>(
    () => apiGet<PortsResponse>('/api/ports'),
    fallbackPorts(),
    [],
  );

  const s = market.data.series;

  const bdi = lastAndPrior(s['baltic.bdi']?.points);
  const bunker = lastAndPrior(s['bunker.vlsfo.singapore']?.points);
  const fx = lastAndPrior(s['macro.usdinr']?.points);
  const coal = lastAndPrior(s['commodity.coal.api2']?.points);

  const rates = useMemo(
    () => VESSEL_CLASSES.map(cls => ({
      cls,
      color: VESSEL_SPECS[cls].color,
      ...lastAndPrior(s[`freight.rate.${cls.toLowerCase()}`]?.points),
    })),
    [s],
  );

  const fmt = (n: number | null, digits = 2, prefix = '') =>
    n === null ? '—' : `${prefix}${n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

  const stats = [
    { id: 'stat-bdi', label: `Baltic Dry${s['baltic.bdi']?.is_proxy ? ' (proxy)' : ''}`, value: fmt(bdi.now, 0), move: bdi.move },
    { id: 'stat-bunker', label: 'VLSFO Singapore', value: fmt(bunker.now, 0, '$'), move: bunker.move, invert: true },
    { id: 'stat-coal', label: 'Thermal coal API2', value: fmt(coal.now, 1, '$'), move: coal.move },
    { id: 'stat-fx', label: 'USD/INR', value: fmt(fx.now, 2, '₹'), move: fx.move, invert: true },
  ];

  // Ports worth looking at now: longest queues first.
  const watchlist = useMemo(() => {
    // Rank on observed waiting when the congestion feed is up, and on the
    // port's standing congestion level when it is not, so the panel still
    // ranks something rather than emptying out.
    const level: Record<string, number> = { high: 3, medium: 2, low: 1 };
    return [...ports.data.discharge_ports]
      .sort((a, b) => {
        const byWait = (b.live.wait_days ?? -1) - (a.live.wait_days ?? -1);
        if (byWait !== 0) return byWait;
        return (level[b.congestion_level] ?? 0) - (level[a.congestion_level] ?? 0);
      })
      .slice(0, 5);
  }, [ports.data]);

  const staleSources = sources.filter(x => x.is_stale).map(x => x.source);

  const buildTicker = () => {
    const items: string[] = [];
    if (bdi.now !== null) items.push(`BDI ${bdi.now.toFixed(0)}${bdi.move !== null ? ` ${bdi.move >= 0 ? '▲' : '▼'}${Math.abs(bdi.move).toFixed(1)}%` : ''}`);
    for (const r of rates) if (r.now !== null) items.push(`${r.cls} $${r.now.toFixed(2)}/T`);
    if (bunker.now !== null) items.push(`VLSFO $${bunker.now.toFixed(0)}/T`);
    if (fx.now !== null) items.push(`USD/INR ${fx.now.toFixed(2)}`);
    for (const p of ports.data.discharge_ports) {
      if (p.live.wait_days !== null) items.push(`${p.name} — ${p.live.wait_days.toFixed(1)}d wait`);
    }
    if (items.length) return items;
    return [
      'Bundled reference data',
      'Backend offline',
      'Berth detail unavailable',
      'Forecasts unfitted',
      'Start the backend for live rates',
    ];
  };

  const ticker = buildTicker();

  return (
    <div className="cc">
      {/* Ticker */}
      <div className="cc__ticker">
        <span className={`cc__ticker-label ${online ? '' : 'cc__ticker-label--off'}`}>
          {online ? 'LIVE' : 'CACHE'}
        </span>
        <div className="ticker-wrap">
          <div className="ticker-inner">
            {[...ticker, ...ticker].map((item, i) => (
              <span key={i} className="cc__ticker-item">{item}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="page-content">
        <div className="cc__notice">
          <DataOriginNotice
            origin={market.origin}
            error={market.error}
            stale={staleSources}
            bundledLabel="Backend unreachable. Market figures are unavailable; port reference data is bundled."
          />
        </div>

        {/* Stat cards */}
        <div className="grid-4 cc__stats">
          {stats.map(st => {
            const up = (st.move ?? 0) >= 0;
            // For a cost line, up is bad news, so the colour follows meaning
            // rather than direction.
            const good = st.invert ? !up : up;
            return (
              <div className="card" key={st.id} id={st.id}>
                <p className="card-title">{st.label}</p>
                <p className="stat-value">{st.value}</p>
                <p className={`stat-delta ${good ? 'up' : 'down'}`}>
                  {st.move === null ? (
                    <span className="cc__no-move">no recent move</span>
                  ) : (
                    <>
                      {up ? <TrendingUp size={12} style={{ display: 'inline', marginRight: 4 }} />
                          : <TrendingDown size={12} style={{ display: 'inline', marginRight: 4 }} />}
                      {Math.abs(st.move).toFixed(1)}% on the week
                    </>
                  )}
                </p>
              </div>
            );
          })}
        </div>

        <div className="cc__grid">
          {/* Market summary */}
          <div className="card cc__market">
            <p className="card-title">Route rates by vessel class</p>
            <div className="cc__rate-rows">
              {rates.map(r => (
                <div className="cc__rate-row" key={r.cls}>
                  <span className="cc__rate-dot" style={{ background: r.color }} />
                  <span className="cc__rate-cls">{r.cls}</span>
                  <span className="cc__rate-val mono">
                    {r.now === null ? '—' : `$${r.now.toFixed(2)}/T`}
                  </span>
                  <span className={`cc__rate-move mono ${(r.move ?? 0) >= 0 ? 'down' : 'up'}`}>
                    {r.move === null ? '' : `${r.move >= 0 ? '+' : '−'}${Math.abs(r.move).toFixed(1)}%`}
                  </span>
                </div>
              ))}
            </div>
            <p className="cc__market-note">
              Per-tonne freight falls as the ship gets bigger: a Capesize spreads one voyage over
              five times the cargo a Handysize carries. A move against you is a rate rise, so the
              arrows follow cost, not price.
            </p>
          </div>

          {/* Port watchlist */}
          <div className="card cc__watch">
            <p className="card-title">Ports worth watching</p>
            {watchlist.length === 0 ? (
              <p className="cc__no-move">No congestion data. Start the backend to populate it.</p>
            ) : (
              <div className="cc__watch-rows">
                {watchlist.map(p => {
                  const wait = p.live.wait_days;
                  const tone = wait === null ? 'muted' : wait >= 5 ? 'red' : wait >= 3 ? 'amber' : 'green';
                  return (
                    <button key={p.id} className="cc__watch-row" onClick={() => navigate('/matcher')}>
                      <span className={`dot dot-${tone === 'muted' ? 'amber' : tone}`} />
                      <span className="cc__watch-name">{p.name}</span>
                      <span className="cc__watch-berths mono">
                        {p.berths.length > 0 ? `${p.berths.length} berths` : '—'}
                      </span>
                      <span className={`cc__watch-wait mono cc__watch-wait--${wait === null ? capTone(p.congestion_level) : tone}`}>
                        {wait === null ? p.congestion_level : `${wait.toFixed(1)} d`}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
            <p className="cc__market-note">
              Waiting days come from the congestion feed. A port that discharges fast but queues for
              a week is not a fast port.
            </p>
          </div>

          {/* Quick actions */}
          <div className="card cc__quick-actions">
            <p className="card-title">Where to go next</p>
            {[
              { label: 'Price a multi-voyage programme', to: '/contracts', icon: Ship },
              { label: 'Check when to fix', to: '/timing', icon: CalendarClock },
              { label: 'Match a cargo to a berth', to: '/matcher', icon: ArrowRight },
              { label: 'Review risks and data health', to: '/risk', icon: AlertTriangle },
            ].map(a => (
              <button key={a.to} className="cc__quick-btn" onClick={() => navigate(a.to)}>
                <span className="cc__quick-icon"><a.icon size={14} /></span>
                {a.label}
                <ArrowRight size={13} className="cc__quick-arrow" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
