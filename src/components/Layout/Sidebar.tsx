import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  AlertTriangle, Anchor, CalendarClock, ChevronLeft, ChevronRight, FileText, LayoutDashboard, Map, Route, TrendingUp,
} from 'lucide-react';
import './Sidebar.css';

const NAV_ITEMS = [
  { path: '/',           label: 'Command Center',    icon: LayoutDashboard },
  { path: '/map',        label: 'Route Map',          icon: Map             },
  { path: '/forecast',   label: 'Forecast',           icon: TrendingUp      },
  { path: '/matcher',    label: 'Vessel Matcher',     icon: Anchor          },
  { path: '/contracts',  label: 'Contract Simulator', icon: FileText        },
  { path: '/timing',     label: 'Market Timing',      icon: CalendarClock   },
  { path: '/idle',       label: 'Idle & Ballast',     icon: Route           },
  { path: '/risk',       label: 'Risk & Data Health',      icon: AlertTriangle   },
] as const;

export default function Sidebar() {
  // Initialise from the viewport rather than setting state inside an effect:
  // starting at false and immediately correcting causes a second render and a
  // visible flash of the expanded sidebar on a narrow screen.
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 1024px)').matches,
  );
  const location = useLocation();

  // Keep following the viewport as it changes.
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1024px)');
    const handler = (e: MediaQueryListEvent) => setCollapsed(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}>
      {/* Wordmark */}
      <div className="sidebar__logo">
        <div className="sidebar__logo-mark">
          <Anchor size={20} color="var(--copper)" strokeWidth={1.5} />
        </div>
        {!collapsed && (
          <div className="sidebar__logo-text">
            <span className="sidebar__logo-name">FreightIQ</span>
            <span className="sidebar__logo-sub">Vessel Intelligence</span>
          </div>
        )}
      </div>

      <div className="sidebar__divider" />

      {/* Navigation */}
      <nav className="sidebar__nav">
        {!collapsed && <span className="sidebar__nav-label">Navigation</span>}
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
          const isActive = path === '/'
            ? location.pathname === '/'
            : location.pathname.startsWith(path);
          return (
            <NavLink
              key={path}
              to={path}
              className={`sidebar__item ${isActive ? 'sidebar__item--active' : ''}`}
              title={collapsed ? label : undefined}
            >
              <span className="sidebar__item-icon">
                <Icon size={18} />
              </span>
              {!collapsed && <span className="sidebar__item-label">{label}</span>}
              {isActive && <span className="sidebar__item-indicator" />}
            </NavLink>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        className="sidebar__collapse-btn"
        onClick={() => setCollapsed(c => !c)}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
    </aside>
  );
}
