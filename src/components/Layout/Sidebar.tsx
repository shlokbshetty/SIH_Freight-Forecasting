import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  AlertTriangle, Anchor, CalendarClock, Calculator, ChevronLeft, ChevronRight,
  FileText, LayoutDashboard, Map, Route, TrendingUp,
} from 'lucide-react';
import './Sidebar.css';

interface NavItem {
  path: string;
  label: string;
  icon: any;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/',           label: 'Command Center',    icon: LayoutDashboard, badge: 'Live' },
  { path: '/map',        label: 'Route Map',          icon: Map             },
  { path: '/evaluate',   label: 'Evaluate (CVC)',     icon: Calculator      },
  { path: '/forecast',   label: 'Forecast',           icon: TrendingUp      },
  { path: '/matcher',    label: 'Vessel Matcher',     icon: Anchor          },
  { path: '/contracts',  label: 'Contract Simulator', icon: FileText        },
  { path: '/timing',     label: 'Market Timing',      icon: CalendarClock   },
  { path: '/idle',       label: 'Idle & Ballast',     icon: Route           },
  { path: '/risk',       label: 'Risk & Data Health', icon: AlertTriangle,   badge: 'Alert' },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 1024px)').matches,
  );
  const location = useLocation();

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1024px)');
    const handler = (e: MediaQueryListEvent) => setCollapsed(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`} aria-label="Main sidebar navigation">
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
        {!collapsed && <span className="sidebar__nav-label">PLATFORM MODULES</span>}
        {NAV_ITEMS.map(({ path, label, icon: Icon, badge }) => {
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
              {!collapsed && badge && (
                <span className={`sidebar__item-tag ${badge === 'Alert' ? 'sidebar__item-tag--alert' : ''}`}>
                  {badge}
                </span>
              )}
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
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
    </aside>
  );
}
