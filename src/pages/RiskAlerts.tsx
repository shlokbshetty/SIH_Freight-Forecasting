import { AlertTriangle, Wind, Anchor, TrendingUp } from 'lucide-react';

const RISK_ITEMS = [
  { id: 'risk-1', severity: 'high',   icon: AlertTriangle, title: 'Port Congestion — Haldia', detail: 'Average wait time 5.2 days. Tidal window constraints worsening. Consider Sagar Sandheads anchorage.' },
  { id: 'risk-2', severity: 'high',   icon: TrendingUp,    title: 'Capesize Rate Spike +8%',  detail: 'Newcastle–India route surging. CVC lock-in window closes within 72h based on forward curve.' },
  { id: 'risk-3', severity: 'medium', icon: Wind,          title: 'Monsoon Advisory',          detail: 'Bay of Bengal advisory issued. Expected disruption to Paradip approach routes Sept 12–16.' },
  { id: 'risk-4', severity: 'low',    icon: Anchor,        title: 'Gangavaram Berth 3 Closed', detail: 'Scheduled maintenance Sept 10–14. 2 berths operational. Minor queue expected.' },
];

const SEV_BADGE: Record<string, string> = {
  high: 'badge-red', medium: 'badge-amber', low: 'badge-green',
};

export default function RiskAlerts() {
  return (
    <div className="page-content">
      <div className="page-header" style={{ padding: 0, marginBottom: '1.5rem' }}>
        <h1>Risk & Alerts</h1>
        <p>Real-time disruption monitoring — port delays, freight spikes, weather events.</p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {RISK_ITEMS.map(({ id, severity, icon: Icon, title, detail }) => (
          <div key={id} id={id} className="card" style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
            <div style={{
              width: 40, height: 40, borderRadius: 'var(--radius)', flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: severity === 'high' ? 'rgba(239,68,68,0.12)' : severity === 'medium' ? 'rgba(245,158,11,0.12)' : 'rgba(34,197,94,0.12)',
              color: severity === 'high' ? 'var(--accent-red)' : severity === 'medium' ? 'var(--accent-amber)' : 'var(--accent-green)',
            }}>
              <Icon size={18} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{title}</span>
                <span className={`badge ${SEV_BADGE[severity]}`}>{severity.toUpperCase()}</span>
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
