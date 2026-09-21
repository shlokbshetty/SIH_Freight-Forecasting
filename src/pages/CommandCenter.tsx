import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, CalendarClock, Ship, Sparkles, Anchor
} from 'lucide-react';
import { apiGet } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { useDataStatus } from '../context/dataStatus';
import { fallbackMarketSeries, fallbackPorts } from '../lib/fallbacks';
import type { PortsResponse } from '../lib/apiTypes';
import type { BundledSeries } from '../lib/fallbacks';
import DataOriginNotice from '../components/common/DataOriginNotice';
import OnboardingBanner from '../components/common/OnboardingBanner';
import StatCard from '../components/common/StatCard';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
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

function capTone(level: string): 'red' | 'amber' | 'green' {
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
    {
      id: 'stat-bdi',
      label: `Baltic Dry Index${s['baltic.bdi']?.is_proxy ? ' (proxy)' : ''}`,
      value: fmt(bdi.now, 0),
      move: bdi.move,
      icon: <Sparkles size={14} />,
    },
    {
      id: 'stat-bunker',
      label: 'VLSFO Singapore Bunker',
      value: fmt(bunker.now, 0, '$'),
      move: bunker.move,
      invert: true,
      icon: <Anchor size={14} />,
    },
    {
      id: 'stat-coal',
      label: 'Thermal Coal API2',
      value: fmt(coal.now, 1, '$'),
      move: coal.move,
      icon: <Ship size={14} />,
    },
    {
      id: 'stat-fx',
      label: 'USD / INR Exchange',
      value: fmt(fx.now, 2, '₹'),
      move: fx.move,
      invert: true,
      icon: <CalendarClock size={14} />,
    },
  ];

  const watchlist = useMemo(() => {
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
      'Start backend for live market feeds',
    ];
  };

  const ticker = buildTicker();

  return (
    <div className="cc animate-fade-in">
      {/* Live Market Ticker */}
      <div className="cc__ticker">
        <span className={`cc__ticker-label ${online ? '' : 'cc__ticker-label--off'}`}>
          {online ? 'LIVE FEED' : 'CACHED'}
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
        <OnboardingBanner />

        <div className="cc__notice">
          <DataOriginNotice
            origin={market.origin}
            error={market.error}
            stale={staleSources}
            bundledLabel="Backend unreachable. Market figures are unavailable; port reference data is bundled."
          />
        </div>

        {/* High-Level KPI Stat Cards */}
        <div className="grid-4 cc__stats">
          {stats.map(st => {
            const up = (st.move ?? 0) >= 0;
            const good = st.invert ? !up : up;
            const badgeVariant = st.move === null ? 'muted' : good ? 'green' : 'red';
            const badgeText = st.move === null
              ? 'No move'
              : `${up ? '▲' : '▼'} ${Math.abs(st.move).toFixed(1)}% / wk`;

            return (
              <StatCard
                key={st.id}
                title={st.label}
                value={st.value}
                badgeText={badgeText}
                badgeVariant={badgeVariant}
                icon={st.icon}
                subtext="Updated live via FreightIQ feed"
              />
            );
          })}
        </div>

        <div className="cc__grid">
          {/* Vessel Class Rates */}
          <Card title="Route Rates by Vessel Class" subtitle="Per-tonne freight benchmark overview">
            <div className="cc__rate-rows">
              {rates.map(r => (
                <div className="cc__rate-row" key={r.cls}>
                  <span className="cc__rate-dot" style={{ background: r.color }} />
                  <span className="cc__rate-cls">{r.cls}</span>
                  <span className="cc__rate-val mono">
                    {r.now === null ? '—' : `$${r.now.toFixed(2)}/T`}
                  </span>
                  <span className="cc__rate-badge">
                    <Badge variant={(r.move ?? 0) >= 0 ? 'red' : 'green'} dot>
                      {r.move === null ? '0.0%' : `${r.move >= 0 ? '+' : '−'}${Math.abs(r.move).toFixed(1)}%`}
                    </Badge>
                  </span>
                </div>
              ))}
            </div>
            <p className="cc__market-note">
              Per-tonne freight rates scale inversely with vessel deadweight tonnage. Capesize spreads voyage cost over 5× the cargo of a Handysize.
            </p>
          </Card>

          {/* Port Queue Watchlist */}
          <Card title="Ports Worth Watching" subtitle="Congestion & waiting time watchlist">
            {watchlist.length === 0 ? (
              <p className="cc__no-move">No congestion data. Start backend services to populate live port status.</p>
            ) : (
              <div className="cc__watch-rows">
                {watchlist.map(p => {
                  const wait = p.live.wait_days;
                  const tone = wait === null ? capTone(p.congestion_level) : wait >= 5 ? 'red' : wait >= 3 ? 'amber' : 'green';
                  return (
                    <button key={p.id} className="cc__watch-row" onClick={() => navigate('/matcher')}>
                      <span className="cc__watch-name-wrap">
                        <Badge variant={tone} dot>
                          {wait === null ? p.congestion_level.toUpperCase() : `${wait.toFixed(1)} d wait`}
                        </Badge>
                        <span className="cc__watch-name">{p.name}</span>
                      </span>
                      <span className="cc__watch-berths mono">
                        {p.berths.length > 0 ? `${p.berths.length} berths` : '—'}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
            <p className="cc__market-note">
              Queuing days directly impact demurrage risk. Fast discharge rates are offset by long anchorage queues.
            </p>
          </Card>

          {/* Navigation Action Shortcuts */}
          <Card title="Where to Go Next" subtitle="Key analytics & simulation tools">
            <div className="cc__quick-grid">
              {[
                { label: 'Contract Simulator (Spot vs CVC)', to: '/contracts', icon: Ship, desc: 'Model charter structures' },
                { label: 'Market Entry Timing', to: '/timing', icon: CalendarClock, desc: 'Calculate delay exposure' },
                { label: 'Vessel & Cargo Matcher', to: '/matcher', icon: Anchor, desc: 'Check berth compatibility' },
                { label: 'Risk & Data Health', to: '/risk', icon: AlertTriangle, desc: 'Source freshness status' },
              ].map(a => (
                <button key={a.to} className="cc__quick-btn" onClick={() => navigate(a.to)}>
                  <span className="cc__quick-icon"><a.icon size={15} /></span>
                  <div className="cc__quick-text">
                    <span className="cc__quick-title">{a.label}</span>
                    <span className="cc__quick-desc">{a.desc}</span>
                  </div>
                  <ArrowRight size={14} className="cc__quick-arrow" />
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
