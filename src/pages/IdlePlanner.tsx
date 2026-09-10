import { useMemo, useState } from 'react';
import { Clock, Fuel, Navigation, Ship } from 'lucide-react';
import { apiGet, apiPost } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { fallbackPorts } from '../lib/fallbacks';
import type { BerthOutcome, MatchResponse, PortsResponse } from '../lib/apiTypes';
import DataOriginNotice from '../components/common/DataOriginNotice';
import { sailedNm } from '../lib/geo';
import { VESSEL_CLASSES, VESSEL_SPECS, type VesselClass } from '../data/vessels';
import './IdlePlanner.css';

const COMMODITIES = [
  { key: 'thermal_coal', label: 'Thermal Coal' },
  { key: 'coking_coal', label: 'Coking Coal' },
  { key: 'iron_ore', label: 'Iron Ore' },
  { key: 'fertiliser', label: 'Fertiliser' },
];

/** Daily burn on the ballast leg, tonnes. Matches the backend's assumptions. */
const BALLAST_TPD: Record<VesselClass, number> = {
  Handysize: 21 * 0.82,
  Supramax: 27 * 0.82,
  Panamax: 32 * 0.82,
  Capesize: 45 * 0.82,
};

/** Indicative daily hire, the opportunity cost of a ballast day. */
const HIRE_USD_PER_DAY: Record<VesselClass, number> = {
  Handysize: 11_000, Supramax: 14_200, Panamax: 17_400, Capesize: 26_500,
};

const OUTCOME_CLS: Record<BerthOutcome, string> = {
  ACCEPT_ALL_TIDE: 'green', ACCEPT_HIGH_TIDE_ONLY: 'amber', REJECT: 'red',
};

interface SeriesPayload {
  series: Record<string, { points: { date: string; value: number }[] }>;
}

export default function IdlePlanner() {
  const [vesselClass, setVesselClass] = useState<VesselClass>('Supramax');
  const [tonnage, setTonnage] = useState(55_000);
  const [commodity, setCommodity] = useState('thermal_coal');
  const [originId, setOriginId] = useState('paradip');

  const spec = VESSEL_SPECS[vesselClass];

  const ports = useApiResource<PortsResponse>(
    () => apiGet<PortsResponse>('/api/ports'), fallbackPorts(), [],
  );

  const bunker = useApiResource<SeriesPayload>(
    () => apiGet<SeriesPayload>('/api/series?metrics=bunker.vlsfo.singapore&days=30&latest_only=true'),
    { series: {} }, [],
  );

  // Turnaround is the resolver's answer, not a re-implementation of it: one
  // call per discharge port, in parallel.
  const turnarounds = useApiResource<MatchResponse[]>(
    () => Promise.all(
      ports.data.discharge_ports.map(p =>
        apiPost<MatchResponse>('/api/match', {
          discharge_port_id: p.id, commodity, cargo_tonnes: tonnage,
        }),
      ),
    ),
    [],
    [ports.data.discharge_ports.length, commodity, tonnage],
  );

  const bunkerPrice =
    bunker.data.series['bunker.vlsfo.singapore']?.points.at(-1)?.value ?? 620;

  // ── Turnaround per port for the chosen class ──────────────────────────────
  const tatRows = useMemo(() => {
    return turnarounds.data
      .map(m => {
        const v = m.recommendations.find(r => r.vessel_class === vesselClass);
        const port = ports.data.discharge_ports.find(p => p.id === m.discharge_port_id);
        if (!v) return null;
        return {
          portId: m.discharge_port_id,
          portName: m.discharge_port_name,
          outcome: v.outcome,
          reason: v.reason,
          berth: v.berth?.berth_id ?? null,
          dischargeRate: v.berth?.discharge_rate_tpd ?? null,
          waitDays: port?.live.wait_days ?? null,
          turnaround: v.turnaround_days,
          lighterageDays: v.lighterage?.added_days ?? 0,
        };
      })
      .filter((r): r is NonNullable<typeof r> => r !== null)
      .sort((a, b) => {
        const rank = { ACCEPT_ALL_TIDE: 0, ACCEPT_HIGH_TIDE_ONLY: 1, REJECT: 2 };
        const d = rank[a.outcome] - rank[b.outcome];
        return d !== 0 ? d : (a.turnaround ?? 999) - (b.turnaround ?? 999);
      });
  }, [turnarounds.data, vesselClass, ports.data.discharge_ports]);

  // ── Ballast options from the origin discharge port ────────────────────────
  const ballastRows = useMemo(() => {
    const origin = ports.data.discharge_ports.find(p => p.id === originId);
    if (!origin) return [];

    const burn = BALLAST_TPD[vesselClass];
    const hire = HIRE_USD_PER_DAY[vesselClass];

    return ports.data.loading_ports
      .map(lp => {
        const nm = sailedNm(origin.lat, origin.lng, lp.lat, lp.lng);
        const days = nm / (spec.speedKts * 24);
        const fuelUsd = days * burn * bunkerPrice;
        const hireUsd = days * hire;
        return {
          id: lp.id,
          name: lp.name,
          country: lp.country,
          commodities: lp.commodities,
          nm,
          days,
          fuelUsd,
          hireUsd,
          totalUsd: fuelUsd + hireUsd,
        };
      })
      .sort((a, b) => a.totalUsd - b.totalUsd);
  }, [ports.data, originId, vesselClass, spec.speedKts, bunkerPrice]);

  const cheapest = ballastRows[0];
  const dearest = ballastRows.at(-1);

  return (
    <div className="page-content idle-page">
      <div className="idle-head">
        <div>
          <h1>Idle &amp; Repositioning</h1>
          <p>What the ship costs when she is not earning, and where to send her next.</p>
        </div>
        <div className="idle-controls">
          {VESSEL_CLASSES.map(c => (
            <button key={c}
              className={`forecast-cls-btn ${vesselClass === c ? 'forecast-cls-btn--active' : ''}`}
              style={vesselClass === c ? {
                borderColor: VESSEL_SPECS[c].color, color: VESSEL_SPECS[c].color,
                background: `${VESSEL_SPECS[c].color}18`,
              } : {}}
              onClick={() => setVesselClass(c)}>
              {c}
            </button>
          ))}
        </div>
      </div>

      <DataOriginNotice
        origin={turnarounds.origin === 'live' ? ports.origin : turnarounds.origin}
        error={turnarounds.error ?? ports.error}
        stale={ports.data.sources_stale}
        bundledLabel="Backend unreachable. Ballast distances still work; turnaround needs the berth resolver."
      />

      {/* ── Turnaround predictor ──────────────────────────────────────── */}
      <section className="card idle-tat">
        <div className="idle-section__head">
          <p className="card-title"><Clock size={12} /> Turnaround by discharge port</p>
          <div className="idle-inline-controls">
            <label className="label" htmlFor="idle-commodity">Commodity</label>
            <select id="idle-commodity" className="select" value={commodity}
              onChange={e => setCommodity(e.target.value)}>
              {COMMODITIES.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
            <label className="label" htmlFor="idle-tonnes">Parcel</label>
            <input id="idle-tonnes" className="input mono" type="number" min={10000} step={5000}
              value={tonnage} onChange={e => setTonnage(Math.max(1000, Number(e.target.value) || 0))} />
          </div>
        </div>

        {tatRows.length === 0 ? (
          <p className="idle-empty">
            Turnaround comes from the berth resolver. Start the backend to populate it.
          </p>
        ) : (
          <div className="idle-table-scroll">
            <table className="idle-table">
              <thead>
                <tr>
                  <th>Port</th>
                  <th>Berth</th>
                  <th className="idle-num">Queue</th>
                  <th className="idle-num">Discharge</th>
                  <th className="idle-num">Lighterage</th>
                  <th className="idle-num">Turnaround</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {tatRows.map(r => (
                  <tr key={r.portId} className={r.outcome === 'REJECT' ? 'idle-row--blocked' : ''}>
                    <td className="idle-table__port">{r.portName}</td>
                    <td className="mono idle-muted">{r.berth ?? '—'}</td>
                    <td className="idle-num mono">{r.waitDays !== null ? `${r.waitDays.toFixed(1)} d` : '—'}</td>
                    <td className="idle-num mono">
                      {r.dischargeRate ? `${(r.dischargeRate / 1000).toFixed(0)}k t/d` : '—'}
                    </td>
                    <td className="idle-num mono">
                      {r.lighterageDays > 0 ? `+${r.lighterageDays.toFixed(1)} d` : '—'}
                    </td>
                    <td className="idle-num mono idle-strong">
                      {r.turnaround !== null ? `${r.turnaround.toFixed(1)} d` : '—'}
                    </td>
                    <td>
                      <span className={`idle-badge idle-badge--${OUTCOME_CLS[r.outcome]}`} title={r.reason}>
                        {r.outcome === 'ACCEPT_ALL_TIDE' ? 'all tide'
                          : r.outcome === 'ACCEPT_HIGH_TIDE_ONLY' ? 'on tide' : 'blocked'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="idle-note">
          Turnaround is berth queue plus cargo time plus any lighterage, for a {vesselClass} carrying{' '}
          {tonnage.toLocaleString('en-US')} T. A port that discharges fast but queues for a week is
          not a fast port.
        </p>
      </section>

      {/* ── Ballast minimiser ─────────────────────────────────────────── */}
      <section className="card idle-ballast">
        <div className="idle-section__head">
          <p className="card-title"><Navigation size={12} /> Ballast leg from the last discharge</p>
          <div className="idle-inline-controls">
            <label className="label" htmlFor="idle-origin">Finishing at</label>
            <select id="idle-origin" className="select" value={originId}
              onChange={e => setOriginId(e.target.value)}>
              {ports.data.discharge_ports.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        </div>

        {cheapest && dearest && (
          <p className="idle-verdict">
            Nearest employment is <b>{cheapest.name}</b> at {Math.round(cheapest.nm).toLocaleString('en-US')} nm,{' '}
            {cheapest.days.toFixed(1)} ballast days costing about{' '}
            <b>${Math.round(cheapest.totalUsd).toLocaleString('en-US')}</b> in fuel and hire.
            The furthest, {dearest.name}, costs{' '}
            <b>${Math.round(dearest.totalUsd - cheapest.totalUsd).toLocaleString('en-US')}</b> more to reach.
          </p>
        )}

        <div className="idle-ballast-list">
          {ballastRows.map((r, i) => {
            const share = dearest ? r.totalUsd / dearest.totalUsd : 0;
            return (
              <div key={r.id} className={`idle-ballast-row ${i === 0 ? 'idle-ballast-row--best' : ''}`}>
                <span className="idle-ballast__rank">{i + 1}</span>
                <span className="idle-ballast__name">
                  {r.name}
                  <em>{r.country} · {r.commodities.join(', ')}</em>
                </span>
                <span className="idle-ballast__track">
                  <span className="idle-ballast__bar" style={{ width: `${Math.max(3, share * 100)}%` }} />
                </span>
                <span className="idle-ballast__nm mono">{Math.round(r.nm).toLocaleString('en-US')} nm</span>
                <span className="idle-ballast__days mono">{r.days.toFixed(1)} d</span>
                <span className="idle-ballast__cost mono">${Math.round(r.totalUsd).toLocaleString('en-US')}</span>
              </div>
            );
          })}
        </div>

        <div className="idle-assumptions">
          <span><Fuel size={11} /> VLSFO ${bunkerPrice.toFixed(0)}/T</span>
          <span><Ship size={11} /> {BALLAST_TPD[vesselClass].toFixed(1)} T/day ballast burn</span>
          <span><Clock size={11} /> ${(HIRE_USD_PER_DAY[vesselClass] / 1000).toFixed(1)}k/day hire opportunity</span>
          <span><Navigation size={11} /> {spec.speedKts} kts at sea</span>
        </div>

        <p className="idle-note">
          Cost is fuel plus the hire the ship is not earning while she steams empty. The cheapest
          ballast is not always the right one: a short leg into a soft market can be worth less than
          a long leg into a firm one, and a period charter out beats both when nothing pays.
        </p>
      </section>
    </div>
  );
}
