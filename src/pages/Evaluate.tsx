/**
 * Evaluate Page — Full Spot vs. CVC financial evaluation UI.
 *
 * Wires user inputs (cargo tonnage, ports, vessel, time horizon, CVC discount)
 * to POST /api/evaluate and renders:
 *   - Hero Banner with dynamic headline
 *   - Summary Panel (savings, break-even, locked rate, confidence range)
 *   - Confidence Band Chart (p10/p50/p90 quantile rates per voyage)
 *   - Voyage Breakdown Table
 *
 * Tasks: 2.4, 2.5, 2.6
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { evaluate, fetchPorts, horizonToVoyages } from '../lib/evaluateApi';
import type { EvaluationResult, PortResponse } from '../lib/evaluateApi';
import './Evaluate.css';

// ─── Constants ────────────────────────────────────────────────────────────────

const VESSEL_CODES = ['HANDYSIZE', 'SUPRAMAX', 'PANAMAX', 'CAPESIZE'] as const;
type VesselCode = typeof VESSEL_CODES[number];

const HORIZONS: { label: string; months: 1 | 3 | 6 }[] = [
  { label: '1 Month',  months: 1 },
  { label: '3 Months', months: 3 },
  { label: '6 Months', months: 6 },
];

// ─── Custom chart tooltip ────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="eval-tooltip">
      <p className="eval-tooltip__label">Voyage {label}</p>
      <p className="eval-tooltip__row">
        <span style={{ color: '#ef4444' }}>p90</span>
        <b>${d?.p90?.toFixed(2)}/T</b>
      </p>
      <p className="eval-tooltip__row">
        <span style={{ color: '#3b82f6' }}>p50</span>
        <b>${d?.p50?.toFixed(2)}/T</b>
      </p>
      <p className="eval-tooltip__row">
        <span style={{ color: '#22c55e' }}>p10</span>
        <b>${d?.p10?.toFixed(2)}/T</b>
      </p>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function Evaluate() {
  // ── Port data ──────────────────────────────────────────────────────────────
  const [ports, setPorts] = useState<PortResponse[]>([]);
  const [portsLoading, setPortsLoading] = useState(true);

  useEffect(() => {
    fetchPorts()
      .then(setPorts)
      .catch(() => setPorts([]))
      .finally(() => setPortsLoading(false));
  }, []);

  // ── Form state ─────────────────────────────────────────────────────────────
  const [cargoTonnage, setCargoTonnage] = useState<number>(75000);
  const [originCode, setOriginCode] = useState<string>('NEWCASTLE');
  const [destCode, setDestCode] = useState<string>('HALDIA');
  const [vesselCode, setVesselCode] = useState<VesselCode>('PANAMAX');
  const [horizonMonths, setHorizonMonths] = useState<1 | 3 | 6>(3);
  const [cvcDiscount, setCvcDiscount] = useState<number>(5.0);

  const originOptions = ports.filter(p => !p.is_anchorage);
  const destOptions = ports.filter(p => !p.is_anchorage && p.code !== originCode);

  // ── Result state ───────────────────────────────────────────────────────────
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Debounce timer ref ─────────────────────────────────────────────────────
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Trigger evaluation (debounced to max 1 req / 500ms) ──────────────────
  const triggerEval = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      if (!originCode || !destCode || !vesselCode || cargoTonnage < 1000) return;
      setLoading(true);
      setError(null);
      try {
        const res = await evaluate({
          cargo_tonnage: cargoTonnage,
          origin_code: originCode,
          destination_code: destCode,
          vessel_code: vesselCode,
          num_voyages: horizonToVoyages(horizonMonths),
          cvc_discount_pct: cvcDiscount,
        });
        setResult(res);
      } catch (e: any) {
        setError(e.message ?? 'Evaluation failed');
      } finally {
        setLoading(false);
      }
    }, 500);
  }, [cargoTonnage, originCode, destCode, vesselCode, horizonMonths, cvcDiscount]);

  // Auto-trigger when any input changes
  useEffect(() => {
    triggerEval();
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [triggerEval]);

  // ── Chart data from result ─────────────────────────────────────────────────
  const chartData = result
    ? result.p10_rates.map((p10, i) => ({
        voyage: i + 1,
        p10,
        p50: result.p50_rates[i],
        p90: result.p90_rates[i],
        bandLow: p10,
        bandHigh: result.p90_rates[i],
      }))
    : [];

  // ── Validation helpers ─────────────────────────────────────────────────────
  const cargoError = cargoTonnage < 1000 || cargoTonnage > 500000
    ? 'Cargo must be between 1,000 and 500,000 MT'
    : null;

  return (
    <div className="eval-page">

      {/* ── Hero Banner ──────────────────────────────────────────────────── */}
      {result && (
        <div className={`eval-banner ${result.is_cvc_favorable ? 'eval-banner--green' : 'eval-banner--amber'}`}>
          {loading && <span className="eval-banner__spinner" />}
          <p className="eval-banner__text">{result.headline_summary}</p>
        </div>
      )}
      {!result && !loading && (
        <div className="eval-banner eval-banner--idle">
          <p className="eval-banner__text">Fill in the form below to run a Spot vs. CVC financial evaluation.</p>
        </div>
      )}
      {loading && !result && (
        <div className="eval-banner eval-banner--idle">
          <span className="eval-banner__spinner" /> <p className="eval-banner__text">Evaluating…</p>
        </div>
      )}
      {error && (
        <div className="eval-banner eval-banner--error">
          <p className="eval-banner__text">⚠ {error}</p>
        </div>
      )}

      <div className="eval-body">

        {/* ── Left: Input Form ────────────────────────────────────────────── */}
        <div className="eval-form card">
          <p className="card-title">Cargo Details</p>

          {/* Cargo Tonnage */}
          <div className="eval-field">
            <label className="eval-label" htmlFor="cargo-input">Cargo Tonnage (MT)</label>
            <input
              id="cargo-input"
              type="number"
              className={`eval-input ${cargoError ? 'eval-input--error' : ''}`}
              min={1000}
              max={500000}
              step={1000}
              value={cargoTonnage}
              onChange={e => setCargoTonnage(Number(e.target.value))}
            />
            {cargoError && <span className="eval-error">{cargoError}</span>}
          </div>

          {/* Origin Port */}
          <div className="eval-field">
            <label className="eval-label" htmlFor="origin-select">Origin Port (Loading)</label>
            <select
              id="origin-select"
              className="eval-select"
              value={originCode}
              onChange={e => setOriginCode(e.target.value)}
              disabled={portsLoading}
            >
              {portsLoading
                ? <option>Loading ports…</option>
                : originOptions.map(p => (
                    <option key={p.code} value={p.code}>{p.name} ({p.country})</option>
                  ))
              }
            </select>
          </div>

          {/* Destination Port */}
          <div className="eval-field">
            <label className="eval-label" htmlFor="dest-select">Destination Port (Discharge)</label>
            <select
              id="dest-select"
              className="eval-select"
              value={destCode}
              onChange={e => setDestCode(e.target.value)}
              disabled={portsLoading}
            >
              {portsLoading
                ? <option>Loading ports…</option>
                : destOptions.map(p => (
                    <option key={p.code} value={p.code}>{p.name} ({p.country})</option>
                  ))
              }
            </select>
          </div>

          {/* Vessel Class */}
          <div className="eval-field">
            <label className="eval-label">Vessel Class</label>
            <div className="eval-vessel-btns">
              {VESSEL_CODES.map(code => (
                <button
                  key={code}
                  className={`eval-vessel-btn ${vesselCode === code ? 'eval-vessel-btn--active' : ''}`}
                  onClick={() => setVesselCode(code)}
                >
                  {code[0] + code.slice(1).toLowerCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Time Horizon */}
          <div className="eval-field">
            <label className="eval-label">Time Horizon</label>
            <div className="eval-horizon-btns">
              {HORIZONS.map(h => (
                <button
                  key={h.months}
                  className={`eval-horizon-btn ${horizonMonths === h.months ? 'eval-horizon-btn--active' : ''}`}
                  onClick={() => setHorizonMonths(h.months)}
                >
                  {h.label}
                  <span className="eval-horizon-sub">
                    {horizonToVoyages(h.months)} voyage{horizonToVoyages(h.months) > 1 ? 's' : ''}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* CVC Discount Slider */}
          <div className="eval-field">
            <div className="eval-slider-header">
              <label className="eval-label" htmlFor="cvc-slider">CVC Negotiated Discount</label>
              <span className="eval-slider-val mono">{cvcDiscount.toFixed(1)}%</span>
            </div>
            <input
              id="cvc-slider"
              type="range"
              className="eval-slider"
              min={0}
              max={15}
              step={0.1}
              value={cvcDiscount}
              onChange={e => setCvcDiscount(Number(e.target.value))}
            />
            <div className="eval-slider-range">
              <span>0%</span>
              <span>{cvcDiscount < 5 ? 'Weak' : cvcDiscount > 10 ? 'Strong discount' : 'Typical'}</span>
              <span>15%</span>
            </div>
          </div>
        </div>

        {/* ── Right: Summary Panel + Chart ────────────────────────────────── */}
        <div className="eval-right">

          {/* Summary Panel */}
          <div className="eval-summary card">
            <p className="card-title">Financial Summary</p>
            {result ? (
              <div className="eval-summary-grid">
                <div className="eval-kv">
                  <span>CVC/Spot Savings</span>
                  <b style={{ color: result.is_cvc_favorable ? 'var(--sig-green)' : 'var(--sig-amber)' }}>
                    {result.is_cvc_favorable ? '+' : '-'}₹{result.base_case_delta_cr.toFixed(1)} Cr
                  </b>
                </div>
                <div className="eval-kv">
                  <span>Break-Even Rate</span>
                  <b className="mono">${result.breakeven_spot_rate.toFixed(2)}/T</b>
                </div>
                <div className="eval-kv eval-kv--sub">
                  <span>Spot wins below this rate (Probability)</span>
                  <b className="mono">{result.breakeven_probability_pct.toFixed(1)}%</b>
                </div>
                <div className="eval-divider" />
                <div className="eval-kv">
                  <span>Locked CVC Rate</span>
                  <b className="mono">${result.locked_cvc_rate.toFixed(2)}/T</b>
                </div>
                <div className="eval-kv">
                  <span>Avg Spot Rate (p50)</span>
                  <b className="mono">${result.average_spot_rate.toFixed(2)}/T</b>
                </div>
                <div className="eval-divider" />
                <div className="eval-kv">
                  <span>Spot Total (80% confidence)</span>
                  <b className="mono">
                    ${(result.p10_spot_total_usd / 1_000_000).toFixed(2)}M –
                    ${(result.p90_spot_total_usd / 1_000_000).toFixed(2)}M
                  </b>
                </div>
                <div className="eval-kv">
                  <span>Spot Total</span>
                  <b className="mono">${(result.spot_total_usd / 1_000_000).toFixed(2)}M</b>
                </div>
                <div className="eval-kv">
                  <span>CVC Total</span>
                  <b className="mono">${(result.cvc_total_usd / 1_000_000).toFixed(2)}M</b>
                </div>
                {result.lighterage_plan.is_required && (
                  <>
                    <div className="eval-divider" />
                    <div className="eval-lighterage-warn">
                      ⚠ {result.lighterage_plan.warning_message || '[LIGHTERAGE_REQUIRED]'}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <p className="eval-placeholder">Run an evaluation to see financial summary.</p>
            )}
          </div>

          {/* Confidence Band Chart */}
          <div className="eval-chart card">
            <p className="card-title">
              Freight Rate Forecast — p10 / p50 / p90 Confidence Band
            </p>
            {chartData.length > 0 ? (
              <div className="eval-chart-wrap">
                <ResponsiveContainer width="100%" height={260}>
                  <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                    <defs>
                      <linearGradient id="bandGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.18} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.03} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.04)" vertical={false} />
                    <XAxis
                      dataKey="voyage"
                      tickFormatter={v => `V${v}`}
                      tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }}
                      tickLine={false}
                      axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                    />
                    <YAxis
                      tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={v => `$${v}`}
                      domain={['auto', 'auto']}
                      width={52}
                    />
                    <Tooltip content={<ChartTooltip />} />

                    {/* Confidence band fill */}
                    <Area
                      type="monotone"
                      dataKey="bandHigh"
                      isAnimationActive={false}
                      stroke="none"
                      fill="url(#bandGrad)"
                      fillOpacity={1}
                      legendType="none"
                      dot={false}
                      activeDot={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="bandLow"
                      isAnimationActive={false}
                      stroke="none"
                      // Masks the band below p10. Must follow the surface, or it
                      // paints a near-black block across the chart in light mode.
                      fill="var(--hull)"
                      fillOpacity={1}
                      legendType="none"
                      dot={false}
                      activeDot={false}
                    />

                    {/* p90 — light red */}
                    <Line
                      type="monotone"
                      dataKey="p90"
                      isAnimationActive={false}
                      stroke="#f87171"
                      strokeWidth={1.5}
                      strokeDasharray="4 3"
                      dot={{ r: 3, fill: '#f87171', strokeWidth: 0 }}
                      name="p90 Bullish"
                    />
                    {/* p50 — bold blue (median) */}
                    <Line
                      type="monotone"
                      dataKey="p50"
                      isAnimationActive={false}
                      stroke="#3b82f6"
                      strokeWidth={2.5}
                      dot={{ r: 4, fill: '#3b82f6', strokeWidth: 0 }}
                      name="p50 Median"
                    />
                    {/* p10 — light green */}
                    <Line
                      type="monotone"
                      dataKey="p10"
                      isAnimationActive={false}
                      stroke="#4ade80"
                      strokeWidth={1.5}
                      strokeDasharray="4 3"
                      dot={{ r: 3, fill: '#4ade80', strokeWidth: 0 }}
                      name="p10 Bearish"
                    />

                    <Legend
                      wrapperStyle={{ fontSize: 11, color: 'var(--chalk-dim)', paddingTop: 6 }}
                      formatter={v => <span style={{ color: 'var(--chalk-dim)' }}>{v}</span>}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="eval-placeholder">Chart appears after evaluation.</p>
            )}
          </div>

        </div>
      </div>

      {/* ── Voyage Breakdown Table ────────────────────────────────────────── */}
      {result && result.voyages.length > 0 && (
        <div className="card eval-table-card">
          <p className="card-title">Voyage-by-Voyage Cost Breakdown</p>
          <div className="eval-table-wrap">
            <table className="eval-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Spot Rate</th>
                  <th>CVC Rate</th>
                  <th>Spot Total</th>
                  <th>CVC Total</th>
                  <th>Savings</th>
                  <th>p10</th>
                  <th>p90</th>
                </tr>
              </thead>
              <tbody>
                {result.voyages.map(v => (
                  <tr key={v.voyage_number}>
                    <td>{v.voyage_number}</td>
                    <td className="mono">${v.spot_freight_rate.toFixed(2)}/T</td>
                    <td className="mono">${v.cvc_freight_rate.toFixed(2)}/T</td>
                    <td className="mono">${(v.spot_voyage_total / 1000).toFixed(0)}K</td>
                    <td className="mono">${(v.cvc_voyage_total / 1000).toFixed(0)}K</td>
                    <td
                      className="mono"
                      style={{ color: v.voyage_savings >= 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}
                    >
                      {v.voyage_savings >= 0 ? '+' : ''}${(v.voyage_savings / 1000).toFixed(0)}K
                    </td>
                    <td className="mono" style={{ color: '#4ade80' }}>${v.p10_spot_rate.toFixed(2)}</td>
                    <td className="mono" style={{ color: '#f87171' }}>${v.p90_spot_rate.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
