import { useState, useMemo } from 'react';
import { DISCHARGE_PORTS, LOADING_PORTS, getPortStatus } from '../data/ports';
import { VESSEL_SPECS, VESSEL_CLASSES, type VesselClass } from '../data/vessels';
import { Search, CheckCircle, AlertCircle, XCircle, ChevronRight, Info } from 'lucide-react';
import './Matcher.css';

const COMMODITIES = ['Coal', 'Coking Coal', 'Iron Ore', 'Bauxite', 'Fertilizer', 'Grain', 'Limestone'];

// ─── Verdict types ────────────────────────────────────────────────────────────
type Verdict = 'available' | 'constrained' | 'blocked';

interface VesselVerdict {
  cls: VesselClass;
  verdict: Verdict;
  reason: string;
  subReasons: string[];
  draftMargin: number;
  loaMargin: number;
  estimatedCost: number; // USD / MT mock
}

// ─── Compute verdicts ─────────────────────────────────────────────────────────
function computeVerdicts(
  dischargeId: string,
  tonnage: number,
): VesselVerdict[] {
  const port = DISCHARGE_PORTS.find(p => p.id === dischargeId);
  if (!port) return [];

  return VESSEL_CLASSES.map(cls => {
    const spec = VESSEL_SPECS[cls];

    // Check tonnage fits vessel DWT range
    const tonFit = tonnage >= spec.dwt.min * 0.6 && tonnage <= spec.dwt.max;

    const draftOk = spec.ladenDraftM <= port.currentDraftM;
    const loaOk   = spec.loaM       <= port.maxLoaM;
    const draftMargin = port.currentDraftM - spec.ladenDraftM;
    const loaMargin   = port.maxLoaM       - spec.loaM;

    const status = getPortStatus(port, spec.ladenDraftM, spec.loaM);

    const subReasons: string[] = [];

    if (!draftOk) {
      subReasons.push(`Draft ${spec.ladenDraftM}m laden vs ${port.name} ${port.currentDraftM}m limit — ${Math.abs(draftMargin).toFixed(1)}m over`);
    } else if (draftMargin < 1.0) {
      subReasons.push(`Only ${draftMargin.toFixed(1)}m draft margin — tidal window critical`);
    }

    if (!loaOk) {
      subReasons.push(`LOA ${spec.loaM}m exceeds ${port.name} max ${port.maxLoaM}m`);
    }

    if (port.lighterageRequired) {
      subReasons.push('Lighterage required at Sagar/Sandheads before proceeding');
    }

    if (port.congestionLevel === 'high') {
      subReasons.push(`High congestion — estimated ${port.berthsAvailable === 0 ? '5+' : '3–5'} day wait`);
    } else if (port.berthsAvailable === 0) {
      subReasons.push('No berths currently available');
    }

    if (!tonFit) {
      subReasons.push(`${tonnage.toLocaleString()} T cargo ${tonnage < spec.dwt.min * 0.6 ? 'too small' : 'exceeds'} ${cls} range`);
    }

    let verdict: Verdict;
    let reason: string;

    if (!draftOk || !loaOk) {
      verdict = 'blocked';
      reason = subReasons[0];
    } else if (status === 'constrained' || !tonFit || draftMargin < 1.0) {
      verdict = 'constrained';
      reason = subReasons[0] ?? 'Port conditions constrained for this vessel';
    } else {
      verdict = 'available';
      reason = `${cls} fits ${port.name} — ${draftMargin.toFixed(1)}m draft margin, ${loaMargin}m LOA clearance`;
    }

    // Mock cost: base varies by class, adjusted for port congestion
    const baseCost: Record<VesselClass, number> = {
      Handysize: 14.2,
      Supramax:  16.8,
      Panamax:   18.4,
      Capesize:  22.1,
    };
    const congestionPenalty = port.congestionLevel === 'high' ? 1.4 : port.congestionLevel === 'medium' ? 0.6 : 0;
    const estimatedCost = +(baseCost[cls] + congestionPenalty + (Math.random() * 0.5 - 0.25)).toFixed(1);

    return { cls, verdict, reason, subReasons, draftMargin, loaMargin, estimatedCost };
  });
}

// ─── Verdict config ───────────────────────────────────────────────────────────
const VERDICT_CONFIG = {
  available:   { icon: CheckCircle,  label: 'Available',   cls: 'verdict--green',  iconCls: 'verdict-icon--green'  },
  constrained: { icon: AlertCircle,  label: 'Constrained', cls: 'verdict--amber',  iconCls: 'verdict-icon--amber'  },
  blocked:     { icon: XCircle,      label: 'Blocked',     cls: 'verdict--red',    iconCls: 'verdict-icon--red'    },
};

const RANK_ORDER: Record<Verdict, number> = { available: 0, constrained: 1, blocked: 2 };

// ─── Component ────────────────────────────────────────────────────────────────
export default function Matcher() {
  const [tonnage,    setTonnage]    = useState(55000);
  const [commodity,  setCommodity]  = useState('Coal');
  const [originId,   setOriginId]   = useState('newcastle');
  const [dischargeId, setDischargeId] = useState('paradip');
  const [targetMonth, setTargetMonth] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() + 1);
    return d.toISOString().slice(0, 7);
  });
  const [searched, setSearched] = useState(false);

  const origin = LOADING_PORTS.find(p => p.id === originId);
  const discharge = DISCHARGE_PORTS.find(p => p.id === dischargeId);

  const verdicts = useMemo(() => {
    if (!searched) return [];
    return computeVerdicts(dischargeId, tonnage)
      .sort((a, b) => RANK_ORDER[a.verdict] - RANK_ORDER[b.verdict]);
  }, [searched, dischargeId, tonnage]);

  const handleSearch = () => setSearched(true);
  const handleChange = () => setSearched(false);

  return (
    <div className="matcher-page">
      {/* ── Left panel ─────────────────────────── */}
      <aside className="matcher-panel">
        <div className="matcher-panel__header">
          <h3>Cargo Details</h3>
          <p>Enter cargo specs to find compatible vessels</p>
        </div>

        <div className="matcher-form">
          {/* Tonnage */}
          <div className="matcher-field">
            <label className="label" htmlFor="input-tonnage">Cargo Tonnage (MT)</label>
            <input
              id="input-tonnage"
              type="number"
              className="input"
              value={tonnage}
              min={10000}
              max={200000}
              step={5000}
              onChange={e => { setTonnage(Number(e.target.value)); handleChange(); }}
            />
            <span className="matcher-field__hint">
              {tonnage.toLocaleString()} MT — typical {tonnage < 45000 ? 'Handysize' : tonnage < 65000 ? 'Supramax' : tonnage < 85000 ? 'Panamax' : 'Capesize'} range
            </span>
          </div>

          {/* Commodity */}
          <div className="matcher-field">
            <label className="label" htmlFor="input-commodity">Commodity</label>
            <select
              id="input-commodity"
              className="select"
              value={commodity}
              onChange={e => { setCommodity(e.target.value); handleChange(); }}
            >
              {COMMODITIES.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>

          {/* Origin */}
          <div className="matcher-field">
            <label className="label" htmlFor="input-origin">Origin Port</label>
            <select
              id="input-origin"
              className="select"
              value={originId}
              onChange={e => { setOriginId(e.target.value); handleChange(); }}
            >
              {LOADING_PORTS.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({p.country})</option>
              ))}
            </select>
          </div>

          {/* Discharge */}
          <div className="matcher-field">
            <label className="label" htmlFor="input-discharge">Discharge Port</label>
            <select
              id="input-discharge"
              className="select"
              value={dischargeId}
              onChange={e => { setDischargeId(e.target.value); handleChange(); }}
            >
              {DISCHARGE_PORTS.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          {/* Target month */}
          <div className="matcher-field">
            <label className="label" htmlFor="input-month">Target Month</label>
            <input
              id="input-month"
              type="month"
              className="input"
              value={targetMonth}
              onChange={e => { setTargetMonth(e.target.value); handleChange(); }}
            />
          </div>

          {/* Port info card */}
          {discharge && (
            <div className="matcher-port-info">
              <div className="matcher-port-info__row">
                <Info size={13} />
                <span className="matcher-port-info__name">{discharge.name}</span>
              </div>
              <div className="matcher-port-info__stats">
                <span>Draft <b>{discharge.currentDraftM}m</b></span>
                <span>LOA <b>{discharge.maxLoaM}m</b></span>
                <span>Berths <b>{discharge.berthsAvailable}/{discharge.berthCount}</b></span>
                <span
                  style={{
                    color: discharge.congestionLevel === 'high' ? 'var(--accent-red)'
                         : discharge.congestionLevel === 'medium' ? 'var(--accent-amber)'
                         : 'var(--accent-green)',
                  }}
                >
                  {discharge.congestionLevel.charAt(0).toUpperCase() + discharge.congestionLevel.slice(1)} congestion
                </span>
              </div>
              {discharge.notes && <p className="matcher-port-info__note">{discharge.notes}</p>}
            </div>
          )}

          <button
            id="btn-match-vessels"
            className="btn btn-primary matcher-search-btn"
            onClick={handleSearch}
          >
            <Search size={15} />
            Match Vessels
          </button>
        </div>
      </aside>

      {/* ── Right panel ────────────────────────── */}
      <div className="matcher-results">
        {!searched ? (
          <div className="matcher-results__empty">
            <span className="matcher-results__empty-icon">⚓</span>
            <p>Fill in cargo details and click <b>Match Vessels</b> to see ranked recommendations.</p>
          </div>
        ) : (
          <>
            <div className="matcher-results__header">
              <div>
                <h3>Vessel Recommendations</h3>
                <p>
                  {origin?.name} → {discharge?.name} · {tonnage.toLocaleString()} MT {commodity} · {targetMonth}
                </p>
              </div>
              <span className="matcher-results__count">
                {verdicts.filter(v => v.verdict === 'available').length} of {verdicts.length} viable
              </span>
            </div>

            <div className="matcher-cards">
              {verdicts.map((v, i) => {
                const spec     = VESSEL_SPECS[v.cls];
                const cfg      = VERDICT_CONFIG[v.verdict];
                const VIcon    = cfg.icon;
                const isBlocked = v.verdict === 'blocked';
                const rank      = i + 1;

                return (
                  <div
                    key={v.cls}
                    id={`vessel-card-${v.cls.toLowerCase()}`}
                    className={`matcher-card ${isBlocked ? 'matcher-card--blocked' : ''}`}
                    style={!isBlocked ? { borderColor: `${spec.color}33` } : {}}
                  >
                    {/* Rank badge */}
                    {!isBlocked && (
                      <div
                        className="matcher-card__rank"
                        style={{ background: spec.color, boxShadow: `0 0 10px ${spec.color}55` }}
                      >
                        #{rank}
                      </div>
                    )}

                    <div className="matcher-card__top">
                      {/* Class name */}
                      <div className="matcher-card__cls-row">
                        <span
                          className="matcher-card__cls"
                          style={{ color: isBlocked ? 'var(--text-muted)' : spec.color }}
                        >
                          {v.cls}
                        </span>
                        <span className="matcher-card__dwt">
                          {spec.dwt.min.toLocaleString()}–{spec.dwt.max.toLocaleString()} DWT
                        </span>
                      </div>

                      {/* Verdict badge */}
                      <div className={`matcher-verdict ${cfg.cls}`}>
                        <VIcon size={13} className={cfg.iconCls} />
                        <span>{cfg.label}</span>
                      </div>
                    </div>

                    {/* Primary reason */}
                    <p className="matcher-card__reason">{v.reason}</p>

                    {/* Sub-reasons */}
                    {v.subReasons.length > 0 && (
                      <ul className="matcher-card__subreasons">
                        {v.subReasons.map((r, ri) => (
                          <li key={ri}>
                            <ChevronRight size={11} />
                            {r}
                          </li>
                        ))}
                      </ul>
                    )}

                    {/* Spec grid */}
                    <div className="matcher-card__specs">
                      <div className="matcher-card__spec">
                        <span>Laden Draft</span>
                        <b style={{ color: v.draftMargin < 0 ? 'var(--accent-red)' : v.draftMargin < 1 ? 'var(--accent-amber)' : 'var(--text-primary)' }}>
                          {spec.ladenDraftM}m
                        </b>
                      </div>
                      <div className="matcher-card__spec">
                        <span>Draft Margin</span>
                        <b style={{ color: v.draftMargin < 0 ? 'var(--accent-red)' : v.draftMargin < 1 ? 'var(--accent-amber)' : 'var(--accent-green)' }}>
                          {v.draftMargin > 0 ? '+' : ''}{v.draftMargin.toFixed(1)}m
                        </b>
                      </div>
                      <div className="matcher-card__spec">
                        <span>LOA</span>
                        <b>{spec.loaM}m</b>
                      </div>
                      <div className="matcher-card__spec">
                        <span>Est. Freight</span>
                        <b className="mono">${v.estimatedCost}/MT</b>
                      </div>
                    </div>

                    {!isBlocked && (
                      <div className="matcher-card__description">
                        {spec.description}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
