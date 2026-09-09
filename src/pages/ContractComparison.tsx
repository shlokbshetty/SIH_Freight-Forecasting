import { useState, useMemo } from 'react';
import { MOCK_CONTRACT_SCENARIO, MOCK_SPOT_SEGMENTS } from '../data/mockContracts';
import './ContractComparison.css';

// ─── Live computation engine ──────────────────────────────────────────────────

interface ComputedResults {
  spotTotal:  number;   // INR Crores
  cvcTotal:   number;
  delta:      number;   // positive = CVC cheaper
  lineItems: { label: string; spot: number; cvc: number }[];
  breakEven:  number;   // USD/MT
  spotWinPct: number;   // %
  segmentHeights: number[]; // px heights for stacked spot bars
  verdict: string;
  verdictType: 'savings' | 'loss';
}

function compute(bunkerPrice: number, cvcDiscountPct: number): ComputedResults {
  const s = MOCK_CONTRACT_SCENARIO;
  const bunkerMultiplier = bunkerPrice / s.bunkerPrice;
  const cvcRate = s.spotRate * (1 - cvcDiscountPct / 100);

  // Line items — recompute from sliders
  const baseFreightSpot = +(s.lineItems[0].spot).toFixed(2);
  const baseFreightCvc  = +(s.lineItems[0].spot * (cvcRate / s.spotRate)).toFixed(2);
  const bunkerSpot      = +(s.lineItems[1].spot * bunkerMultiplier).toFixed(2);
  const bunkerCvc       = +(s.lineItems[1].cvc  * bunkerMultiplier * 0.92).toFixed(2);
  const portSpot        = s.lineItems[2].spot;
  const portCvc         = s.lineItems[2].cvc;
  const demurrageSpot   = +(s.lineItems[3].spot).toFixed(2);
  const demurrageCvc    = +(s.lineItems[3].cvc  * 0.85).toFixed(2);
  const lighterageSpot  = 0;
  const lighterageCvc   = 0;

  const lineItems = [
    { label: 'Base Freight',       spot: baseFreightSpot, cvc: baseFreightCvc },
    { label: 'Bunker Adjustment',  spot: bunkerSpot,      cvc: bunkerCvc      },
    { label: 'Port Charges',       spot: portSpot,        cvc: portCvc        },
    { label: 'Expected Demurrage', spot: demurrageSpot,   cvc: demurrageCvc   },
    { label: 'Lighterage',         spot: lighterageSpot,  cvc: lighterageCvc  },
  ];

  const spotTotal = +(lineItems.reduce((sum, l) => sum + l.spot, 0)).toFixed(2);
  const cvcTotal  = +(lineItems.reduce((sum, l) => sum + l.cvc,  0)).toFixed(2);
  const delta     = +(spotTotal - cvcTotal).toFixed(2);

  // Break-even: spot rate at which spot == CVC total
  const breakEven = +(s.spotRate * (cvcTotal / spotTotal)).toFixed(1);
  // Probability spot wins: rough heuristic based on delta size
  const spotWinPct = Math.max(5, Math.min(70, Math.round(30 - delta * 3)));

  // Stacked segment heights (pixels) for visual — vary with bunker
  const segmentHeights = MOCK_SPOT_SEGMENTS.map(seg => {
    const h = 60 + seg.rateDelta * 8 * bunkerMultiplier;
    return Math.max(30, Math.round(h));
  });

  const cvcSaves = delta >= 0;
  const absD = Math.abs(delta).toFixed(1);
  const verdict = cvcSaves
    ? `CVC saves ₹${absD} Cr · break-even $${breakEven}/T · ${spotWinPct}% chance spot wins`
    : `Spot cheaper by ₹${absD} Cr at current bunker — delay CVC until rates stabilise`;

  return { spotTotal, cvcTotal, delta, lineItems, breakEven, spotWinPct, segmentHeights, verdict, verdictType: cvcSaves ? 'savings' : 'loss' };
}

// ─── Custom stacked bar visual ────────────────────────────────────────────────

function CostVisual({ results }: { results: ComputedResults }) {
  const { segmentHeights, spotTotal, cvcTotal, delta } = results;
  const maxH = 240;
  const spotTotalH = segmentHeights.reduce((a, b) => a + b, 0);
  const scale = maxH / Math.max(spotTotalH, 1);
  const scaledHeights = segmentHeights.map(h => Math.round(h * scale));
  const cvcH = Math.round((cvcTotal / spotTotal) * spotTotalH * scale);

  const spotColors = ['#c2822a', '#b87333', '#d4962e', '#a0692a'];

  return (
    <div className="cost-visual">
      {/* Spot column */}
      <div className="cost-visual__col">
        <div className="cost-visual__bars">
          {scaledHeights.map((h, i) => (
            <div
              key={i}
              className="cost-visual__seg"
              style={{ height: h, background: spotColors[i % spotColors.length] }}
              title={`Voyage ${i + 1}`}
            >
              {h > 20 && <span className="cost-visual__seg-label">V{i + 1}</span>}
            </div>
          ))}
        </div>
        <div className="cost-visual__col-label">
          <span>{MOCK_CONTRACT_SCENARIO.numVoyages} spot</span>
          <b>₹{spotTotal} Cr</b>
        </div>
      </div>

      {/* Delta annotation */}
      <div className="cost-visual__delta">
        <div className="cost-visual__delta-arrow">
          <div className="cost-visual__delta-line" style={{ height: Math.abs(cvcH - scaledHeights.reduce((a,b)=>a+b,0)) + 20 }} />
          <span
            className="cost-visual__delta-val"
            style={{ color: delta >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}
          >
            delta<br />₹{Math.abs(delta).toFixed(1)} Cr
          </span>
        </div>
      </div>

      {/* CVC column */}
      <div className="cost-visual__col">
        <div className="cost-visual__bars">
          <div
            className="cost-visual__seg cost-visual__seg--cvc"
            style={{ height: cvcH }}
          >
            <span className="cost-visual__seg-label">CVC</span>
          </div>
        </div>
        <div className="cost-visual__col-label">
          <span>1 CVC</span>
          <b>₹{cvcTotal} Cr</b>
        </div>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function ContractComparison() {
  const s = MOCK_CONTRACT_SCENARIO;

  const [bunkerPrice,   setBunkerPrice]   = useState(s.bunkerPrice);
  const [cvcDiscount,   setCvcDiscount]   = useState(s.cvcDiscount);

  const results = useMemo(() => compute(bunkerPrice, cvcDiscount), [bunkerPrice, cvcDiscount]);
  const { lineItems, spotTotal, cvcTotal, delta, breakEven, spotWinPct, verdict, verdictType } = results;

  return (
    <div className="cc-page">

      {/* ① Verdict banner — always first, always visible ─────────────────── */}
      <div className={`cc-verdict ${verdictType === 'savings' ? 'cc-verdict--green' : 'cc-verdict--red'}`}>
        <div className="cc-verdict__dot" />
        <p className="cc-verdict__text">{verdict}</p>
        <span className="cc-verdict__tag">{verdictType === 'savings' ? 'LOCK CVC' : 'HOLD SPOT'}</span>
      </div>

      <div className="cc-body">

        {/* ② Cost visual + Sensitivity ─────────────────────────────────── */}
        <div className="cc-top-row">

          {/* Cost comparison */}
          <div className="card cc-cost-card">
            <p className="card-title">Cost Comparison — {s.route}</p>
            <CostVisual results={results} />
          </div>

          {/* Sensitivity */}
          <div className="card cc-sensitivity">
            <p className="card-title">Sensitivity</p>
            <div className="sens-rows">
              <div className="sens-row">
                <span>Break-even rate</span>
                <b className="mono">${breakEven}/MT</b>
              </div>
              <div className="sens-row">
                <span>Downside if rates fall 20%</span>
                <b className="mono sens-green">
                  ₹{(delta + cvcTotal * 0.15).toFixed(1)} Cr saved
                </b>
              </div>
              <div className="sens-row">
                <span>Upside if rates rise 20%</span>
                <b className="mono sens-amber">
                  ₹{(delta * 1.4).toFixed(1)} Cr additional saving
                </b>
              </div>
              <div className="sens-row">
                <span>Forecast confidence</span>
                <b className="mono sens-blue">72%</b>
              </div>
              <div className="sens-row">
                <span>Chance spot wins</span>
                <b className="mono" style={{ color: spotWinPct > 40 ? 'var(--accent-amber)' : 'var(--accent-green)' }}>
                  {spotWinPct}%
                </b>
              </div>
            </div>

            {/* Mini stats */}
            <div className="sens-divider" />
            <div className="sens-mini-stats">
              <div className="sens-mini-stat">
                <span>Vessel</span>
                <b>{s.vesselClass}</b>
              </div>
              <div className="sens-mini-stat">
                <span>Route</span>
                <b>{s.route}</b>
              </div>
              <div className="sens-mini-stat">
                <span>Cargo</span>
                <b>{s.cargoTonnes.toLocaleString()} MT</b>
              </div>
              <div className="sens-mini-stat">
                <span>Voyages</span>
                <b>{s.numVoyages} spot vs 1 CVC</b>
              </div>
            </div>
          </div>
        </div>

        {/* ③ Line-item breakdown ───────────────────────────────────────── */}
        <div className="card cc-table-card">
          <p className="card-title">Line-item Breakdown — INR Crores</p>
          <table className="cc-table">
            <thead>
              <tr>
                <th>Cost Component</th>
                <th className="cc-table__col-spot">Spot (×{s.numVoyages})</th>
                <th className="cc-table__col-cvc">CVC</th>
                <th className="cc-table__col-delta">Delta</th>
              </tr>
            </thead>
            <tbody>
              {lineItems.map(item => {
                const d = +(item.spot - item.cvc).toFixed(2);
                const isSaving = d > 0;
                const isLighterage = item.label === 'Lighterage';
                return (
                  <tr key={item.label} className={isLighterage ? 'cc-table__row--lighterage' : ''}>
                    <td className="cc-table__label">
                      {item.label}
                      {isLighterage && <span className="cc-table__flag">constraint engine</span>}
                    </td>
                    <td className="cc-table__spot mono">
                      {item.spot === 0 ? '—' : `₹${item.spot.toFixed(2)}`}
                    </td>
                    <td className="cc-table__cvc mono">
                      {item.cvc === 0 ? '—' : `₹${item.cvc.toFixed(2)}`}
                    </td>
                    <td
                      className="cc-table__delta mono"
                      style={{ color: d === 0 ? 'var(--text-muted)' : isSaving ? 'var(--accent-green)' : 'var(--accent-red)' }}
                    >
                      {d === 0 ? '—' : `${isSaving ? '-' : '+'}₹${Math.abs(d).toFixed(2)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="cc-table__total">
                <td>Total</td>
                <td className="mono">₹{spotTotal.toFixed(2)}</td>
                <td className="mono">₹{cvcTotal.toFixed(2)}</td>
                <td
                  className="mono"
                  style={{ color: delta >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}
                >
                  {delta >= 0 ? '-' : '+'}₹{Math.abs(delta).toFixed(2)} Cr
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* ④ Sliders — at the bottom, everything above recomputes live ─── */}
        <div className="card cc-controls">
          <p className="card-title">Controls — drag sliders to recompute live</p>
          <div className="cc-sliders">

            {/* Bunker price slider */}
            <div className="cc-slider-group">
              <div className="cc-slider-header">
                <label className="label" htmlFor="slider-bunker">Bunker Price (VLSFO)</label>
                <span className="cc-slider-val mono">${bunkerPrice}/MT</span>
              </div>
              <input
                id="slider-bunker"
                type="range"
                className="cc-slider"
                min={400}
                max={900}
                step={10}
                value={bunkerPrice}
                onChange={e => setBunkerPrice(Number(e.target.value))}
              />
              <div className="cc-slider-range">
                <span>$400</span>
                <span className="cc-slider-hint">
                  {bunkerPrice < 500 ? 'Low — favours spot' : bunkerPrice > 750 ? 'High — CVC hedges risk' : 'Moderate'}
                </span>
                <span>$900</span>
              </div>
            </div>

            {/* CVC discount slider */}
            <div className="cc-slider-group">
              <div className="cc-slider-header">
                <label className="label" htmlFor="slider-cvc">CVC Negotiated Discount</label>
                <span className="cc-slider-val mono">{cvcDiscount.toFixed(1)}%</span>
              </div>
              <input
                id="slider-cvc"
                type="range"
                className="cc-slider"
                min={2}
                max={25}
                step={0.5}
                value={cvcDiscount}
                onChange={e => setCvcDiscount(Number(e.target.value))}
              />
              <div className="cc-slider-range">
                <span>2%</span>
                <span className="cc-slider-hint">
                  {cvcDiscount < 8 ? 'Weak negotiation' : cvcDiscount > 18 ? 'Strong discount secured' : 'Typical market discount'}
                </span>
                <span>25%</span>
              </div>
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}
