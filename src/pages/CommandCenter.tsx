import { TrendingUp, TrendingDown, Ship, AlertTriangle, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import './CommandCenter.css';

const STATS = [
  { label: 'BDI (Today)',    value: '1,842',  delta: '+2.4%', up: true,  id: 'stat-bdi'       },
  { label: 'Avg Spot Rate',  value: '$16.8/T', delta: '-0.3%', up: false, id: 'stat-spot'      },
  { label: 'Active Voyages', value: '7',       delta: '+1',    up: true,  id: 'stat-voyages'   },
  { label: 'CVC Savings',    value: '₹4.2 Cr', delta: 'This month', up: true, id: 'stat-savings' },
];

const ALERTS = [
  { id: 'alert-1', type: 'red',   msg: 'Haldia tidal window closes in 4h — Panamax congestion.' },
  { id: 'alert-2', type: 'amber', msg: 'Capesize rates up 8% on Newcastle route — review CVC.' },
  { id: 'alert-3', type: 'green', msg: 'Paradip Berth 6 available — 2 day wait window.' },
];

const TICKER_ITEMS = [
  'BDI 1842 ▲2.4%',
  'Handysize $12.3/T',
  'Supramax $16.8/T',
  'Panamax $19.4/T',
  'Capesize $28.7/T',
  'Bunker VLSFO $624/T',
  'USD/INR 83.42',
  'Paradip — Berths 3/8 Available',
  'Vizag — Berths 5/12 Available',
  'Gangavaram — Clear',
  'Haldia — High Congestion',
];

export default function CommandCenter() {
  const navigate = useNavigate();

  return (
    <div className="cc">
      {/* Ticker */}
      <div className="cc__ticker">
        <span className="cc__ticker-label">LIVE</span>
        <div className="ticker-wrap">
          <div className="ticker-inner">
            {[...TICKER_ITEMS, ...TICKER_ITEMS].map((item, i) => (
              <span key={i} className="cc__ticker-item">{item}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="page-content">
        {/* Stat cards */}
        <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
          {STATS.map(s => (
            <div className="card" key={s.id} id={s.id}>
              <p className="card-title">{s.label}</p>
              <p className="stat-value">{s.value}</p>
              <p className={`stat-delta ${s.up ? 'up' : 'down'}`}>
                {s.up ? <TrendingUp size={12} style={{ display: 'inline', marginRight: 4 }} />
                      : <TrendingDown size={12} style={{ display: 'inline', marginRight: 4 }} />}
                {s.delta}
              </p>
            </div>
          ))}
        </div>

        <div className="cc__grid">
          {/* Alerts */}
          <div className="card">
            <p className="card-title">Active Alerts</p>
            <div className="cc__alerts">
              {ALERTS.map(a => (
                <div key={a.id} id={a.id} className={`cc__alert cc__alert--${a.type}`}>
                  <AlertTriangle size={14} className="cc__alert-icon" />
                  <span>{a.msg}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Quick nav */}
          <div className="card">
            <p className="card-title">Quick Actions</p>
            <div className="cc__quick-actions">
              {[
                { label: 'Open Port Map',        path: '/map',       icon: '🗺️' },
                { label: 'Freight Forecast',      path: '/forecast',  icon: '📈' },
                { label: 'Match Vessel',          path: '/matcher',   icon: '⚓' },
                { label: 'Compare Contracts',     path: '/contracts', icon: '📄' },
              ].map(({ label, path, icon }) => (
                <button
                  key={path}
                  id={`qa-${path.replace('/', '')}`}
                  className="cc__quick-btn"
                  onClick={() => navigate(path)}
                >
                  <span className="cc__quick-icon">{icon}</span>
                  <span>{label}</span>
                  <ArrowRight size={14} className="cc__quick-arrow" />
                </button>
              ))}
            </div>
          </div>

          {/* Market summary */}
          <div className="card cc__market">
            <p className="card-title">Market Summary — Vessel Class Rates</p>
            <div className="cc__rate-rows">
              {[
                { cls: 'Handysize', rate: '$12.3/T', delta: '+0.4', color: 'var(--accent-green)' },
                { cls: 'Supramax',  rate: '$16.8/T', delta: '-0.3', color: 'var(--accent-blue)'  },
                { cls: 'Panamax',   rate: '$19.4/T', delta: '+1.1', color: 'var(--accent-amber)' },
                { cls: 'Capesize',  rate: '$28.7/T', delta: '+2.3', color: 'var(--accent-red)'   },
              ].map(({ cls, rate, delta, color }) => (
                <div className="cc__rate-row" key={cls} id={`rate-${cls.toLowerCase()}`}>
                  <div className="cc__rate-dot" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
                  <span className="cc__rate-cls">{cls}</span>
                  <span className="cc__rate-val mono">{rate}</span>
                  <span className={`cc__rate-delta ${parseFloat(delta) >= 0 ? 'up' : 'down'}`}>
                    {parseFloat(delta) >= 0 ? '▲' : '▼'} {Math.abs(parseFloat(delta))}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Active charters */}
          <div className="card">
            <p className="card-title">Active Charters</p>
            <div className="cc__charters">
              {[
                { vessel: 'MV Coastal Star', cls: 'Supramax', route: 'Newcastle → Paradip', eta: '14 Sep', badge: 'En Route' },
                { vessel: 'MV Dhamra Eagle', cls: 'Panamax',  route: 'Gladstone → Vizag',   eta: '18 Sep', badge: 'Berthed'  },
                { vessel: 'MV Bay Pioneer',  cls: 'Handysize', route: 'Beira → Gopalpur',    eta: '22 Sep', badge: 'En Route' },
              ].map((c) => (
                <div className="cc__charter" key={c.vessel}>
                  <div className="cc__charter-icon"><Ship size={14} /></div>
                  <div className="cc__charter-info">
                    <span className="cc__charter-name">{c.vessel}</span>
                    <span className="cc__charter-route">{c.route}</span>
                  </div>
                  <div>
                    <span className={`badge ${c.badge === 'Berthed' ? 'badge-green' : 'badge-blue'}`}>
                      {c.badge}
                    </span>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4, textAlign: 'right' }}>ETA {c.eta}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
