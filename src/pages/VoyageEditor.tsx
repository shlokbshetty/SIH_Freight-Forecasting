import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, CheckCircle, Lock, Ship, TrendingUp,
  AlertTriangle, Info,
} from 'lucide-react';
import { DISCHARGE_PORTS, LOADING_PORTS } from '../data/ports';
import { VESSEL_SPECS } from '../data/vessels';
import { DEFAULT_PROGRAMME } from '../data/mockContracts';
import { USD_INR } from '../data/costAssumptions';
import { evaluate, type CvcInputs } from '../lib/cvcEngine';
import { useCharter, type LockedCharter } from '../store/charterStore';
import './VoyageEditor.css';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function cr(n: number): string {
  const d = Math.abs(n) >= 10 ? 1 : 2;
  return `₹${n.toFixed(d)} Cr`;
}
function pct(n: number): string { return `${Math.round(n * 100)}%`; }

function DualCost({ usdVal, crVal }: { usdVal: number; crVal: number }) {
  const d = Math.abs(crVal) >= 10 ? 1 : 2;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.35em' }}>
      <span>${(usdVal / 1e6).toFixed(2)}M</span>
      <span style={{ fontSize: '0.72em', opacity: 0.55, fontWeight: 400 }}>₹{crVal.toFixed(d)} Cr</span>
    </span>
  );
}

function DualRate({ usdPerMt }: { usdPerMt: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.3em' }}>
      <span>${usdPerMt.toFixed(2)}/T</span>
      <span style={{ fontSize: '0.72em', opacity: 0.55, fontWeight: 400 }}>₹{(usdPerMt * USD_INR).toFixed(0)}/T</span>
    </span>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function VoyageEditor() {
  const navigate = useNavigate();
  const { selectedVessel, lockCharter } = useCharter();

  // Every hook runs before the early return below.
  //
  // The guard used to sit above these, which meant the eight useState calls only
  // ran when a vessel was selected. React identifies hooks by call order, so the
  // first render that arrives with a selection after one without would line the
  // state up against the wrong slots and crash the component.
  const vessel = selectedVessel;
  const spec = VESSEL_SPECS[vessel?.cls ?? 'Supramax'];

  // ─── Voyage inputs (editable) ───────────────────────────────────────────────
  const [originId, setOriginId] = useState(vessel?.originId ?? DEFAULT_PROGRAMME.loadPortId);
  const [dischargeId, setDischargeId] = useState(vessel?.dischargeId ?? DEFAULT_PROGRAMME.dischargePortId);
  const [cargoTonnes, setCargoTonnes] = useState(vessel?.tonnage ?? DEFAULT_PROGRAMME.cargoTonnes);
  const [numVoyages, setNumVoyages] = useState(3);
  const [cvcDiscount, setCvcDiscount] = useState(DEFAULT_PROGRAMME.cvcDiscountPct);
  const [bunker, setBunker] = useState(DEFAULT_PROGRAMME.bunkerPriceUsd);
  const [demurrage, setDemurrage] = useState(DEFAULT_PROGRAMME.demurrageUsdPerDay);
  const [locked, setLocked] = useState(false);

  const origin = LOADING_PORTS.find(p => p.id === originId);
  const discharge = DISCHARGE_PORTS.find(p => p.id === dischargeId);

  // ─── CVC engine ─────────────────────────────────────────────────────────────
  const inputs: CvcInputs = useMemo(() => ({
    ...DEFAULT_PROGRAMME,
    loadPortId: originId,
    dischargePortId: dischargeId,
    vesselClass: vessel?.cls ?? 'Supramax',
    cargoTonnes,
    numVoyages,
    cvcDiscountPct: cvcDiscount,
    bunkerPriceUsd: bunker,
    demurrageUsdPerDay: demurrage,
  }), [originId, dischargeId, vessel?.cls, cargoTonnes, numVoyages, cvcDiscount, bunker, demurrage]);

  const result = useMemo(() => evaluate(inputs), [inputs]);

  // Now that every hook has run, it is safe to bail out.
  if (!vessel) {
    return (
      <div className="ve-empty">
        <Ship size={40} className="ve-empty__icon" />
        <p>No vessel selected. Go back to Vessel Matcher.</p>
        <button className="btn btn-primary" onClick={() => navigate('/matcher')}>
          <ArrowLeft size={14} /> Back to Matcher
        </button>
      </div>
    );
  }
  // Captured after the guard so closures below keep the narrowed type: TypeScript
  // does not narrow a captured binding inside a function declaration.
  const activeVessel = vessel;

  const { spot, cvc, deltaCr, cvcWins, probSpotWins, breakEvenUsdPerMt, lockedRateUsdPerMt } = result;

  // ─── Port constraints summary ─────────────────────────────────────────────
  const draftOk = discharge ? spec.ladenDraftM <= discharge.currentDraftM : true;
  const loaOk   = discharge ? spec.loaM <= discharge.maxLoaM : true;
  const draftMargin = discharge ? discharge.currentDraftM - spec.ladenDraftM : 0;

  // ─── Lock handler ─────────────────────────────────────────────────────────
  function handleLock() {
    if (locked) return;
    const eta = new Date();
    eta.setDate(eta.getDate() + 14 + Math.floor(Math.random() * 10));
    const charter: LockedCharter = {
      id: `charter-${Date.now()}`,
      vessel: `MV ${origin?.name ?? '?'} Trader`,
      cls: activeVessel.cls,
      route: `${origin?.name ?? '?'} → ${discharge?.name ?? '?'}`,
      eta: eta.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }),
      badge: 'Locked',
      cvcRate: lockedRateUsdPerMt,
      cargoTonnes,
      lockedAt: new Date().toISOString(),
    };
    lockCharter(charter);
    setLocked(true);
  }

  return (
    <div className="ve-page">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="ve-header">
        <button className="ve-back" onClick={() => navigate('/matcher')}>
          <ArrowLeft size={14} /> Matcher
        </button>
        <div className="ve-header__title">
          <span className="ve-vessel-badge" style={{ color: spec.color, borderColor: `${spec.color}44`, background: `${spec.color}0f` }}>
            <Ship size={13} /> {vessel.cls}
          </span>
          <h1>Voyage Editor</h1>
          <p>{vessel.commodity} · {vessel.targetMonth}</p>
        </div>
        {locked ? (
          <div className="ve-locked-badge">
            <Lock size={13} /> Contract Locked
          </div>
        ) : (
          <button
            id="btn-lock-contract"
            className="btn btn-primary ve-lock-btn"
            onClick={handleLock}
            disabled={!draftOk || !loaOk}
          >
            <Lock size={13} /> Lock Contract
          </button>
        )}
      </div>

      <div className="ve-body">

        {/* ── Left: form ──────────────────────────────────────────────────── */}
        <aside className="ve-panel">

          {/* Vessel summary */}
          <div className="ve-vessel-card" style={{ borderColor: `${spec.color}33` }}>
            <div className="ve-vessel-card__name" style={{ color: spec.color }}>{vessel.cls}</div>
            <div className="ve-vessel-card__specs">
              <span>DWT {spec.dwt.min.toLocaleString()}–{spec.dwt.max.toLocaleString()}</span>
              <span>LOA {spec.loaM}m</span>
              <span>Draft {spec.ladenDraftM}m laden</span>
              <span>Speed {spec.speedKts}kts</span>
            </div>
            <p className="ve-vessel-card__desc">{spec.description}</p>
          </div>

          <div className="ve-section-label">Route</div>

          <div className="ve-field">
            <label className="label" htmlFor="ve-origin">Origin Port</label>
            <select id="ve-origin" className="select" value={originId} onChange={e => setOriginId(e.target.value)}>
              {LOADING_PORTS.map(p => <option key={p.id} value={p.id}>{p.name}, {p.country}</option>)}
            </select>
          </div>

          <div className="ve-field">
            <label className="label" htmlFor="ve-discharge">Discharge Port</label>
            <select id="ve-discharge" className="select" value={dischargeId} onChange={e => setDischargeId(e.target.value)}>
              {DISCHARGE_PORTS.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          <div className="ve-field">
            <label className="label" htmlFor="ve-cargo">Cargo per Voyage (MT)</label>
            <input id="ve-cargo" type="number" className="input" min={10000} max={200000} step={5000}
              value={cargoTonnes} onChange={e => setCargoTonnes(Number(e.target.value))} />
          </div>

          <div className="ve-field">
            <label className="label" htmlFor="ve-voyages">Number of Voyages</label>
            <input id="ve-voyages" type="number" className="input" min={1} max={12} step={1}
              value={numVoyages} onChange={e => setNumVoyages(Number(e.target.value))} />
          </div>

          <div className="ve-section-label" style={{ marginTop: '1rem' }}>Assumptions</div>

          <div className="ve-field">
            <div className="ve-slider-header">
              <label className="label" htmlFor="ve-discount">CVC Discount</label>
              <span className="ve-slider-val">{cvcDiscount.toFixed(1)}%</span>
            </div>
            <input id="ve-discount" type="range" className="cc-slider" min={0} max={25} step={0.5}
              value={cvcDiscount} onChange={e => setCvcDiscount(Number(e.target.value))} />
          </div>

          <div className="ve-field">
            <div className="ve-slider-header">
              <label className="label" htmlFor="ve-bunker">Bunker VLSFO</label>
              <span className="ve-slider-val">${bunker}/T</span>
            </div>
            <input id="ve-bunker" type="range" className="cc-slider" min={350} max={950} step={10}
              value={bunker} onChange={e => setBunker(Number(e.target.value))} />
          </div>

          <div className="ve-field">
            <div className="ve-slider-header">
              <label className="label" htmlFor="ve-demurrage">Demurrage Rate</label>
              <span className="ve-slider-val">${(demurrage / 1000).toFixed(0)}k/day</span>
            </div>
            <input id="ve-demurrage" type="range" className="cc-slider" min={5000} max={60000} step={1000}
              value={demurrage} onChange={e => setDemurrage(Number(e.target.value))} />
          </div>

        </aside>

        {/* ── Right: results ──────────────────────────────────────────────── */}
        <div className="ve-results">

          {/* Port constraint card */}
          {discharge && (
            <div className={`ve-port-card ${!draftOk || !loaOk ? 've-port-card--blocked' : draftMargin < 1.5 ? 've-port-card--warn' : 've-port-card--ok'}`}>
              <div className="ve-port-card__header">
                <Info size={13} />
                <span>{discharge.name} — Port Constraints</span>
                <span className={`badge ${!draftOk || !loaOk ? 'badge-red' : draftMargin < 1.5 ? 'badge-amber' : 'badge-green'}`}>
                  {!draftOk || !loaOk ? 'BLOCKED' : draftMargin < 1.5 ? 'CONSTRAINED' : 'CLEAR'}
                </span>
              </div>
              <div className="ve-port-card__stats">
                <div className="ve-port-stat">
                  <span>Port Draft Limit</span>
                  <b>{discharge.currentDraftM}m</b>
                </div>
                <div className="ve-port-stat">
                  <span>{vessel.cls} Draft</span>
                  <b style={{ color: draftOk ? 'var(--sig-green)' : 'var(--sig-red)' }}>{spec.ladenDraftM}m</b>
                </div>
                <div className="ve-port-stat">
                  <span>Draft Margin</span>
                  <b style={{ color: draftMargin < 0 ? 'var(--sig-red)' : draftMargin < 1 ? 'var(--sig-amber)' : 'var(--sig-green)' }}>
                    {draftMargin >= 0 ? '+' : ''}{draftMargin.toFixed(1)}m
                  </b>
                </div>
                <div className="ve-port-stat">
                  <span>Berths Available</span>
                  <b>{discharge.berthsAvailable}/{discharge.berthCount}</b>
                </div>
                <div className="ve-port-stat">
                  <span>Cargo Rate</span>
                  <b>{discharge.cargoRateTpd.toLocaleString()} T/day</b>
                </div>
                <div className="ve-port-stat">
                  <span>Congestion</span>
                  <b style={{
                    color: discharge.congestionLevel === 'high' ? 'var(--sig-red)'
                      : discharge.congestionLevel === 'medium' ? 'var(--sig-amber)'
                      : 'var(--sig-green)',
                  }}>
                    {discharge.congestionLevel.charAt(0).toUpperCase() + discharge.congestionLevel.slice(1)}
                  </b>
                </div>
                {discharge.maxLoaM && (
                  <div className="ve-port-stat">
                    <span>Max LOA</span>
                    <b style={{ color: loaOk ? 'var(--sig-green)' : 'var(--sig-red)' }}>{discharge.maxLoaM}m</b>
                  </div>
                )}
                {discharge.lighterageRequired && (
                  <div className="ve-port-stat">
                    <span>Lighterage</span>
                    <b style={{ color: 'var(--sig-amber)' }}>Required</b>
                  </div>
                )}
              </div>
              {discharge.notes && (
                <div className="ve-port-card__note">
                  <AlertTriangle size={11} /> {discharge.notes}
                </div>
              )}
            </div>
          )}

          {/* Verdict banner */}
          <div className={`ve-verdict ${cvcWins ? 've-verdict--green' : 've-verdict--red'}`}>
            <div className="ve-verdict__dot" />
            <div className="ve-verdict__text">
              <strong>{cvcWins ? 'CVC is cheaper' : 'Spot is cheaper'}</strong>
              {' · '}saves {cr(Math.abs(deltaCr))} across {numVoyages} voyage{numVoyages > 1 ? 's' : ''}
            </div>
            <span className="ve-verdict__tag">{cvcWins ? 'LOCK CVC' : 'STAY SPOT'}</span>
          </div>

          {/* KPI grid */}
          <div className="ve-kpis">
            <div className="ve-kpi ve-kpi--hero">
              <span className="ve-kpi__label">Programme delta</span>
              <span className="ve-kpi__val" style={{ color: cvcWins ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                {cr(Math.abs(deltaCr))}
              </span>
              <span className="ve-kpi__sub">{cvcWins ? 'CVC saves vs spot' : 'spot saves vs CVC'}</span>
            </div>
            <div className="ve-kpi">
              <span className="ve-kpi__label">Spot total</span>
              <span className="ve-kpi__val"><DualCost usdVal={spot.totalUsd} crVal={spot.totalCr} /></span>
              <span className="ve-kpi__sub"><DualRate usdPerMt={spot.avgRateUsdPerMt} /> avg</span>
            </div>
            <div className="ve-kpi">
              <span className="ve-kpi__label">CVC locked total</span>
              <span className="ve-kpi__val" style={{ color: 'var(--sig-blue)' }}><DualCost usdVal={cvc.totalUsd} crVal={cvc.totalCr} /></span>
              <span className="ve-kpi__sub"><DualRate usdPerMt={lockedRateUsdPerMt} /> locked</span>
            </div>
            <div className="ve-kpi">
              <span className="ve-kpi__label">Break-even spot</span>
              <span className="ve-kpi__val"><DualRate usdPerMt={breakEvenUsdPerMt} /></span>
              <span className="ve-kpi__sub">chance spot wins: {pct(probSpotWins)}</span>
            </div>
          </div>

          {/* Voyage by voyage table */}
          <div className="card ve-table-card">
            <p className="card-title">Voyage breakdown — {origin?.name ?? '?'} → {discharge?.name ?? '?'}</p>
            <div className="ve-table-scroll">
              <table className="ve-table">
                <thead>
                  <tr>
                    <th>Voyage</th>
                    <th>Departs</th>
                    <th className="ve-num">Spot rate</th>
                    <th className="ve-num ve-col-spot">Spot cost</th>
                    <th className="ve-num ve-col-cvc">CVC cost</th>
                    <th className="ve-num">CVC vs spot</th>
                  </tr>
                </thead>
                <tbody>
                  {spot.voyages.map((v, i) => {
                    const c = cvc.voyages[i];
                    const d = (c.total - v.total) * USD_INR / 1e7;
                    return (
                      <tr key={v.index}>
                        <td className="ve-table__label">V{v.index}</td>
                        <td className="ve-muted">{v.label}</td>
                        <td className="ve-num mono"><DualRate usdPerMt={v.rateUsdPerMt} /></td>
                        <td className="ve-num mono ve-col-spot"><DualCost usdVal={v.total} crVal={v.total * USD_INR / 1e7} /></td>
                        <td className="ve-num mono ve-col-cvc"><DualCost usdVal={c.total} crVal={c.total * USD_INR / 1e7} /></td>
                        <td className="ve-num mono" style={{ color: d <= 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                          {d >= 0 ? '+' : '−'}₹{Math.abs(d).toFixed(2)} Cr
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="ve-table__total">
                    <td colSpan={2}>Programme</td>
                    <td className="ve-num"><DualRate usdPerMt={spot.avgRateUsdPerMt} /></td>
                    <td className="ve-num"><DualCost usdVal={spot.totalUsd} crVal={spot.totalCr} /></td>
                    <td className="ve-num"><DualCost usdVal={cvc.totalUsd} crVal={cvc.totalCr} /></td>
                    <td className="ve-num" style={{ color: cvcWins ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                      {cvcWins ? '−' : '+'}₹{Math.abs(deltaCr).toFixed(2)} Cr
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Lock confirmation */}
          {locked && (
            <div className="ve-lock-confirm">
              <CheckCircle size={18} className="ve-lock-confirm__icon" />
              <div>
                <strong>Contract locked!</strong>
                <p>This charter is now visible in the Command Centre under Active Charters.</p>
              </div>
              <button className="btn btn-ghost" onClick={() => navigate('/')}>
                View in Command Centre <TrendingUp size={13} />
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
