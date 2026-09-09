import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Map, TrendingUp, Anchor,
  FileText, AlertTriangle, ChevronLeft, ChevronRight,
  Waves,
} from 'lucide-react';
import './Sidebar.css';

const NAV_ITEMS = [
  { path: '/',           label: 'Command Center',    icon: LayoutDashboard },
  { path: '/map',        label: 'Route Map',          icon: Map             },
  { path: '/forecast',   label: 'Forecast',           icon: TrendingUp      },
  { path: '/matcher',    label: 'Vessel Matcher',     icon: Anchor          },
  { path: '/contracts',  label: 'Contract Simulator', icon: FileText        },
  { path: '/risk',       label: 'Risk & Alerts',      icon: AlertTriangle   },
] as const;

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  // Auto-collapse on narrow viewports
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1024px)');
    if (mq.matches) setCollapsed(true);
    const handler = (e: MediaQueryListEvent) => setCollapsed(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}>
      {/* Logo */}
      <div className="sidebar__logo">
        <div className="sidebar__logo-icon">
          <Waves size={20} />
        </div>
        {!collapsed && (
          <div className="sidebar__logo-text">
            <span className="sidebar__logo-name">FreightIQ</span>
            <span className="sidebar__logo-sub">Freight Intelligence</span>
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
