import { useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Bell, Clock, Moon, Sun } from 'lucide-react';
import { useTheme } from '../../store/themeStore';
import ConnectionBadge from './ConnectionBadge';
import './Header.css';

const ROUTE_META: Record<string, { title: string; sub: string }> = {
  '/':          { title: 'Command Center',    sub: 'Operational overview & live market alerts' },
  '/map':       { title: 'Route Map',          sub: 'Interactive GIS port & vessel tracking' },
  '/forecast':  { title: 'Freight Forecast',   sub: 'Rate prediction with confidence bands' },
  '/matcher':   { title: 'Vessel Matcher',     sub: 'Cargo & port compatibility engine' },
  '/contracts': { title: 'Contract Simulator', sub: 'Spot vs CVC cost comparison' },
  '/timing':    { title: 'Market Entry Timing', sub: 'When to fix, and what waiting costs' },
  '/idle':      { title: 'Idle & Repositioning', sub: 'Ballast legs, turnaround and redeployment' },
  '/risk':      { title: 'Risk & Data Health',  sub: 'Disruptions, port delays and source freshness' },
};

export default function Header() {
  const { pathname } = useLocation();
  const meta = ROUTE_META[pathname] ?? ROUTE_META['/'];
  const [time, setTime] = useState(new Date());
  const { theme, toggle } = useTheme();

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const timeStr = time.toLocaleTimeString('en-IN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  const dateStr = time.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  });

  return (
    <header className="app-header">
      <div className="app-header__left">
        <h1 className="app-header__title">{meta.title}</h1>
        <p className="app-header__sub">{meta.sub}</p>
      </div>

      <div className="app-header__right">
        {/* Live clock */}
        <div className="app-header__clock">
          <Clock size={13} className="app-header__clock-icon" />
          <span className="app-header__clock-time mono">{timeStr}</span>
          <span className="app-header__clock-date">{dateStr} IST</span>
        </div>

        {/* Theme toggle */}
        <button
          className="app-header__theme-toggle"
          id="header-theme-toggle"
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          onClick={toggle}
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        {/* Alerts bell */}
        <button className="app-header__bell" id="header-alerts-btn" title="View alerts">
          <Bell size={16} />
          <span className="app-header__bell-dot" />
        </button>

        {/* Where the numbers are coming from */}
        <ConnectionBadge />
      </div>
    </header>
  );
}
