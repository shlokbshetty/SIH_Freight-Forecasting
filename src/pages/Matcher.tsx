import { useMemo, useState } from 'react';
import {
  AlertCircle, Anchor, CheckCircle, ChevronRight, Ship, XCircle,
} from 'lucide-react';
import { apiGet, apiPost } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { fallbackMatch, fallbackPorts } from '../lib/fallbacks';
import type { BerthOutcome, MatchResponse, PortsResponse, VesselVerdict } from '../lib/apiTypes';
import DataOriginNotice from '../components/common/DataOriginNotice';
import { VESSEL_SPECS } from '../data/vessels';
import './Matcher.css';

const COMMODITIES = [
  { key: 'thermal_coal', label: 'Thermal Coal' },
  { key: 'coking_coal', label: 'Coking Coal' },
  { key: 'iron_ore', label: 'Iron Ore' },
  { key: 'bauxite', label: 'Bauxite' },
  { key: 'limestone', label: 'Limestone' },
  { key: 'fertiliser', label: 'Fertiliser' },
  { key: 'general', label: 'General Cargo' },
];

const OUTCOME_UI: Record<BerthOutcome, { icon: typeof CheckCircle; label: string; cls: string }> = {
  ACCEPT_ALL_TIDE: { icon: CheckCircle, label: 'Berths all tide', cls: 'green' },
  ACCEPT_HIGH_TIDE_ONLY: { icon: AlertCircle, label: 'High tide only', cls: 'amber' },
  REJECT: { icon: XCircle, label: 'Cannot berth', cls: 'red' },
};

export default function Matcher() {
  const [dischargeId, setDischargeId] = useState('paradip');
  const [commodity, setCommodity] = useState('thermal_coal');
  const [tonnage, setTonnage] = useState(55_000);
  const [expanded, setExpanded] = useState<string | null>(null);

  const ports = useApiResource<PortsResponse>(
    () => apiGet<PortsResponse>('/api/ports'),
    fallbackPorts(),
    [],
  );

  const match = useApiResource<MatchResponse>(
    () => apiPost<MatchResponse>('/api/match', {
      discharge_port_id: dischargeId,
      commodity,
      cargo_tonnes: tonnage,
    }),
    fallbackMatch(dischargeId, tonnage, commodity),
    [dischargeId, commodity, tonnage],
  );

  const port = useMemo(
    () => ports.data.discharge_ports.find(p => p.id === dischargeId) ?? ports.data.discharge_ports[0],
    [ports.data, dischargeId],
  );

  const res = match.data;
  const workable = res.recommendations.filter(r => r.outcome !== 'REJECT').length;

  return (
    <div className="matcher-page">
      {/* ── Left panel ─────────────────────────── */}
      <aside className="matcher-panel">
        <div className="matcher-panel__header">
          <h3>Cargo Details</h3>
          <p>Every class is run through the berth resolver</p>
        </div>

        <div className="matcher-form">
          <div className="matcher-field">
            <label className="label" htmlFor="input-tonnage">Cargo Tonnage (MT)</label>
            <input
              id="input-tonnage" type="number" className="input"
              value={tonnage} min={10000} max={250000} step={5000}
              onChange={e => setTonnage(Math.max(1000, Number(e.target.value) || 0))}
            />
            <span className="matcher-field__hint">
              {tonnage.toLocaleString('en-US')} MT — typical{' '}
              {tonnage < 45000 ? 'Handysize' : tonnage < 65000 ? 'Supramax' : tonnage < 85000 ? 'Panamax' : 'Capesize'} parcel
            </span>
          </div>

          <div className="matcher-field">
            <label className="label" htmlFor="input-commodity">Commodity</label>
            <select id="input-commodity" className="select" value={commodity}
              onChange={e => setCommodity(e.target.value)}>
              {COMMODITIES.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
            <span className="matcher-field__hint">
              Berths are equipped for specific cargoes; this decides which are eligible at all.
            </span>
          </div>

          <div className="matcher-field">
            <label className="label" htmlFor="input-discharge">Discharge Port</label>
            <select id="input-discharge" className="select" value={dischargeId}
              onChange={e => setDischargeId(e.target.value)}>
              {ports.data.discharge_ports.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Port summary, now berth aware */}
        {port && (
          <div className="matcher-port-info">
            <div className="matcher-port-info__name">{port.name}</div>
            <div className="matcher-port-info__stats">
              <div className="matcher-port-info__row">
                <span>Berths on file</span>
                <b className="mono">{port.berths.length || '—'}</b>
              </div>
              <div className="matcher-port-info__row">
                <span>Deepest all tide</span>
                <b className="mono">{port.deepest_berth_m ? `${port.deepest_berth_m.toFixed(1)} m` : '—'}</b>
              </div>
              <div className="matcher-port-info__row">
                <span>Deepest on tide</span>
                <b className="mono">{port.deepest_on_tide_m ? `${port.deepest_on_tide_m.toFixed(1)} m` : '—'}</b>
              </div>
              <div className="matcher-port-info__row">
                <span>Berth queue</span>
                <b className="mono" style={{
                  color: (port.live.wait_days ?? 0) >= 5 ? 'var(--sig-red)'
                    : (port.live.wait_days ?? 0) >= 3 ? 'var(--sig-amber)' : 'var(--sig-green)',
                }}>
                  {port.live.wait_days !== null ? `${port.live.wait_days.toFixed(1)} d` : '—'}
                </b>
              </div>
              {port.live.vessels_at_anchor !== null && (
                <div className="matcher-port-info__row">
                  <span>At anchor</span>
                  <b className="mono">{port.live.vessels_at_anchor}</b>
                </div>
              )}
            </div>
            {port.notes && <p className="matcher-port-info__note">{port.notes}</p>}
            {port.lighterage_nodes.length > 0 && (
              <p className="matcher-port-info__note">
                Lighterage available at {port.lighterage_nodes.map(n => n.node_name).join(', ')}.
              </p>
            )}
          </div>
        )}
      </aside>

      {/* ── Results ────────────────────────────── */}
      <section className="matcher-results">
        <div className="matcher-results__header">
          <h3>
            <Ship size={14} /> Berth resolution
            <span className="matcher-results__count">{workable} of {res.recommendations.length} workable</span>
          </h3>
        </div>

        <div className="matcher-notice">
          <DataOriginNotice
            origin={match.origin}
            error={match.error}
            stale={res.sources_stale}
            bundledLabel="Backend unreachable. Falling back to a single-draft check per port; no berth detail."
          />
        </div>

        <div className="matcher-cards">
          {res.recommendations.map((v, i) => (
            <VerdictCard
              key={v.vessel_class}
              verdict={v}
              rank={i + 1}
              expanded={expanded === v.vessel_class}
              onToggle={() => setExpanded(expanded === v.vessel_class ? null : v.vessel_class)}
            />
          ))}
        </div>

        {res.provenance.caveat && (
          <p className="matcher-provenance">
            {res.provenance.caveat}
            {res.provenance.source_dates.length > 0 && ` Compiled ${res.provenance.source_dates.join(', ')}.`}
          </p>
        )}
      </section>
    </div>
  );
}

// ─── One vessel class ─────────────────────────────────────────────────────────

function VerdictCard({ verdict, rank, expanded, onToggle }: {
  verdict: VesselVerdict; rank: number; expanded: boolean; onToggle: () => void;
}) {
  const ui = OUTCOME_UI[verdict.outcome];
  const Icon = ui.icon;
  const spec = VESSEL_SPECS[verdict.vessel_class];
  const isBlocked = verdict.outcome === 'REJECT';

  return (
    <div className={`card matcher-card matcher-card--${ui.cls}`}>
      <div className="matcher-card__top">
        <span className="matcher-card__rank">{rank}</span>
        <div className="matcher-card__cls-row">
          <span className="matcher-card__cls" style={{ color: isBlocked ? 'var(--chalk-faint)' : spec.color }}>
            {verdict.vessel_class}
          </span>
          <span className="matcher-card__dwt mono">
            {verdict.laden_draft_m.toFixed(1)} m laden · {spec.loaM} m LOA
          </span>
        </div>
        <span className={`matcher-verdict matcher-verdict--${ui.cls}`}>
          <Icon size={13} /> {ui.label}
        </span>
      </div>

      <p className="matcher-card__reason">{verdict.reason}</p>

      {verdict.berth && (
        <div className="matcher-berth">
          <div className="matcher-berth__head">
            <b>{verdict.berth.berth_name}</b>
            <span className="mono">{verdict.berth.berth_id}</span>
          </div>
          <div className="matcher-berth__grid">
            <div><span>Operator</span><b>{verdict.berth.operator}</b></div>
            <div><span>All-tide draft</span><b className="mono">{verdict.berth.draft_max_m.toFixed(1)} m</b></div>
            <div><span>On tide</span><b className="mono">{verdict.berth.draft_max_on_tide_m.toFixed(1)} m</b></div>
            <div><span>Discharge</span><b className="mono">{verdict.berth.discharge_rate_tpd.toLocaleString('en-US')} t/d</b></div>
            <div><span>Turnaround</span><b className="mono">{verdict.turnaround_days?.toFixed(1) ?? '—'} d</b></div>
            <div><span>Night work</span><b>{verdict.berth.night_restricted ? 'restricted' : 'unrestricted'}</b></div>
          </div>
          {verdict.berth.provenance.source_url && (
            <a className="matcher-berth__src" href={verdict.berth.provenance.source_url}
              target="_blank" rel="noreferrer">
              source · {verdict.berth.provenance.source_date}
            </a>
          )}
        </div>
      )}

      {verdict.lighterage && (
        <div className="matcher-lighterage">
          <Anchor size={13} />
          <div>
            <p>{verdict.lighterage.narrative}</p>
            <div className="matcher-lighterage__nums mono">
              {verdict.lighterage.tonnes_to_lighten.toLocaleString('en-US')} T ·{' '}
              {verdict.lighterage.barge_trips} barge trips ·{' '}
              +{verdict.lighterage.added_days.toFixed(1)} d ·{' '}
              ${Math.round(verdict.lighterage.cost_usd).toLocaleString('en-US')}
            </div>
          </div>
        </div>
      )}

      {verdict.considered.length > 0 && (
        <>
          <button className="matcher-expand" onClick={onToggle}>
            <ChevronRight size={12} className={expanded ? 'matcher-expand__caret--open' : ''} />
            {expanded ? 'Hide' : 'Show'} all {verdict.considered.length} berths considered
          </button>
          {expanded && (
            <div className="matcher-considered">
              {verdict.considered.map(c => (
                <div key={c.berth_id} className={`matcher-considered__row matcher-considered__row--${OUTCOME_UI[c.outcome].cls}`}>
                  <span className="mono matcher-considered__id">{c.berth_id}</span>
                  <span className="matcher-considered__reason">{c.reason}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
