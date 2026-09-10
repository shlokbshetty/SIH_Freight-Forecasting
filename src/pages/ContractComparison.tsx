import { useMemo, useState } from 'react';
import {
  Area, AreaChart, CartesianGrid, ComposedChart, LabelList, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertTriangle, Anchor, Ship } from 'lucide-react';
import { DISCHARGE_PORTS, LOADING_PORTS } from '../data/ports';
import { VESSEL_CLASSES, type VesselClass } from '../data/vessels';
import { DEFAULT_PROGRAMME, PROGRAMME_PRESETS } from '../data/mockContracts';
import { BUNKER_BASIS_USD, USD_INR } from '../data/costAssumptions';
import { breakEvenDensity, cumulativeSeries, evaluate, type CvcInputs, type CvcResult } from '../lib/cvcEngine';
import { useTheme } from '../store/themeStore';
import './ContractComparison.css';

// ─── Series colours ───────────────────────────────────────────────────────────
// Two series, one identity each. Validated for deuteranopia, protanopia and
// tritanopia separation against the --hull surface. Green and red stay reserved
// for the verdict, so they are never doing double duty as a series colour.
const SPOT_HUE = '#c87941';
const CVC_HUE = '#5a93e8';

// ─── Formatting ───────────────────────────────────────────────────────────────

function cr(n: number, digits?: number): string {
  const d = digits ?? (Math.abs(n) >= 10 ? 1 : 2);
  return `₹${n.toFixed(d)} Cr`;
}

/** USD primary + INR crores secondary (small). usdVal = raw USD, crVal = INR crores. */
function DualCost({ usdVal, crVal, digits }: { usdVal: number; crVal: number; digits?: number }) {
  const d = digits ?? (Math.abs(crVal) >= 10 ? 1 : 2);
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.35em' }}>
      <span>${(usdVal / 1e6).toFixed(2)}M</span>
      <span style={{ fontSize: '0.72em', opacity: 0.55, fontWeight: 400 }}>₹{crVal.toFixed(d)} Cr</span>
    </span>
  );
}

/** Rate in $/T primary, ₹/T small. */
function DualRate({ usdPerMt }: { usdPerMt: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.3em' }}>
      <span>${usdPerMt.toFixed(2)}/T</span>
      <span style={{ fontSize: '0.72em', opacity: 0.55, fontWeight: 400 }}>₹{(usdPerMt * USD_INR).toFixed(0)}/T</span>
    </span>
  );
}

/** CVC measured against spot: a negative figure means the lock costs less. */
function vsSpot(cvcMinusSpot: number): string {
  const d = Math.abs(cvcMinusSpot) >= 10 ? 1 : 2;
  return `${cvcMinusSpot >= 0 ? '+' : '−'}₹${Math.abs(cvcMinusSpot).toFixed(d)} Cr`;
}

/** Plain words for one edge of the forecast band. */
function spotVersusLock(spotMinusCvc: number): string {
  const d = Math.abs(spotMinusCvc) >= 10 ? 1 : 2;
  return `₹${Math.abs(spotMinusCvc).toFixed(d)} Cr ${spotMinusCvc >= 0 ? 'dearer' : 'cheaper'}`;
}

function usd(n: number): string {
  return `$${n.toFixed(2)}`;
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

// ─── Cumulative cost chart ────────────────────────────────────────────────────

function CumulativeTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const cvcMinusSpot = d.cvc - d.spot;
  return (
    <div className="cc-tip">
      <p className="cc-tip__head">{d.voyage} · {d.monthLabel}</p>
      <p className="cc-tip__row">
        <span><i className="cc-tip__swatch" style={{ background: SPOT_HUE }} />Spot to date</span>
        <b>{cr(d.spot)}</b>
      </p>
      <p className="cc-tip__row">
        <span><i className="cc-tip__swatch" style={{ background: CVC_HUE }} />CVC to date</span>
        <b>{cr(d.cvc)}</b>
      </p>
      <p className="cc-tip__row cc-tip__row--sep">
        <span>CVC vs spot</span>
        <b style={{ color: cvcMinusSpot <= 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}>{vsSpot(cvcMinusSpot)}</b>
      </p>
      <p className="cc-tip__foot">Forecast band {cr(d.spotLow)} – {cr(d.spotHigh)}</p>
    </div>
  );
}

/** Direct label on the final point of a series, so the lines need no hunting. */
function endLabel(lastIndex: number, text: string, fill: string, dy: number) {
  return (props: any) => {
    if (props.index !== lastIndex) return null;
    return (
      <text
        x={props.x}
        y={props.y + dy}
        textAnchor="end"
        fill={fill}
        fontSize={11}
        fontWeight={600}
        fontFamily="IBM Plex Mono, monospace"
      >
        {text}
      </text>
    );
  };
}

function CumulativeChart({ result }: { result: CvcResult }) {
  const data = useMemo(() => cumulativeSeries(result), [result]);
  const { theme } = useTheme();
  const gridColor  = theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)';
  const axisColor  = theme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.10)';
  const cursorColor= theme === 'dark' ? 'rgba(255,255,255,0.16)' : 'rgba(0,0,0,0.16)';
  const tickColor  = theme === 'dark' ? 'var(--chalk-faint)' : '#6b7280';

  // Whichever programme finishes higher gets its label above the point, so the
  // two never converge when the lines cross.
  const spotOnTop = result.spot.totalCr >= result.cvc.totalCr;
  const ABOVE = -11;
  const BELOW = 18;

  return (
    <div className="cc-chart">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 22, right: 18, left: 4, bottom: 4 }}>
          <CartesianGrid stroke={gridColor} vertical={false} />
          <XAxis
            dataKey="voyage"
            tick={{ fill: tickColor, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: axisColor }}
          />
          <YAxis
            tick={{ fill: tickColor, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={52}
            tickFormatter={(v: number) => `₹${v.toFixed(0)}`}
          />
          <Tooltip content={<CumulativeTooltip />} cursor={{ stroke: cursorColor }} />

          {/* Where the forecast's 90% band puts the spot programme */}
          <Area
            dataKey="spotBand"
            stroke="none"
            fill={SPOT_HUE}
            fillOpacity={0.12}
            isAnimationActive={false}
            activeDot={false}
          />
          <Line
            dataKey="spot"
            name="Spot"
            stroke={SPOT_HUE}
            strokeWidth={2}
            dot={{ r: 3.5, fill: SPOT_HUE, strokeWidth: 0 }}
            activeDot={{ r: 5.5, fill: SPOT_HUE, stroke: 'var(--hull)', strokeWidth: 2 }}
            isAnimationActive={false}
          >
            <LabelList dataKey="spot" content={endLabel(data.length - 1, cr(result.spot.totalCr), SPOT_HUE, spotOnTop ? ABOVE : BELOW)} />
          </Line>
          <Line
            dataKey="cvc"
            name="CVC"
            stroke={CVC_HUE}
            strokeWidth={2}
            dot={{ r: 3.5, fill: CVC_HUE, strokeWidth: 0 }}
            activeDot={{ r: 5.5, fill: CVC_HUE, stroke: 'var(--hull)', strokeWidth: 2 }}
            isAnimationActive={false}
          >
            <LabelList dataKey="cvc" content={endLabel(data.length - 1, cr(result.cvc.totalCr), CVC_HUE, spotOnTop ? BELOW : ABOVE)} />
          </Line>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Break-even probability chart ─────────────────────────────────────────────

/** Whole-dollar ticks across the plotted range, so no two round to the same label. */
function rateTicks(from: number, to: number): { ticks: number[]; step: number } {
  const target = (to - from) / 5;
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(target, 1e-6)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * magnitude).find(c => c >= target) ?? magnitude * 10;
  const ticks: number[] = [];
  for (let t = Math.ceil(from / step) * step; t <= to + 1e-9; t += step) {
    ticks.push(+t.toFixed(6));
  }
  return { ticks, step };
}

function BreakEvenChart({ result }: { result: CvcResult }) {
  const data = useMemo(() => breakEvenDensity(result), [result]);
  const axis = useMemo(
    () => (data.length ? rateTicks(data[0].rate, data[data.length - 1].rate) : { ticks: [], step: 1 }),
    [data],
  );
  const { theme } = useTheme();
  const gridColor = theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)';
  const axisColor = theme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.10)';
  const tickColor = theme === 'dark' ? 'var(--chalk-faint)' : '#6b7280';

  if (!data.length) {
    return <div className="cc-chart cc-chart--empty">Forecast band too narrow to price this risk.</div>;
  }

  return (
    <div className="cc-chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 26, right: 14, left: 4, bottom: 4 }}>
          <CartesianGrid stroke={gridColor} vertical={false} />
          <XAxis
            dataKey="rate"
            type="number"
            domain={['dataMin', 'dataMax']}
            tick={{ fill: tickColor, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: axisColor }}
            ticks={axis.ticks}
            tickFormatter={(v: number) => `$${v.toFixed(axis.step < 1 ? 1 : 0)}`}
          />
          {/* Density height carries no unit the reader needs — area is the message. */}
          <YAxis hide />

          <Area
            dataKey="spotWins"
            stroke={SPOT_HUE}
            strokeWidth={1.5}
            fill={SPOT_HUE}
            fillOpacity={0.34}
            connectNulls={false}
            isAnimationActive={false}
            activeDot={false}
          />
          <Area
            dataKey="cvcWins"
            stroke={CVC_HUE}
            strokeWidth={1.5}
            fill={CVC_HUE}
            fillOpacity={0.24}
            connectNulls={false}
            isAnimationActive={false}
            activeDot={false}
          />

          <ReferenceLine
            x={+result.breakEvenUsdPerMt.toFixed(3)}
            stroke="var(--chalk)"
            strokeWidth={1.5}
            label={{
              value: `break-even ${usd(result.breakEvenUsdPerMt)}`,
              position: 'top',
              fill: 'var(--chalk)',
              fontSize: 10.5,
              fontFamily: 'IBM Plex Mono, monospace',
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Slider ───────────────────────────────────────────────────────────────────

function Slider(props: {
  id: string;
  label: string;
  value: number;
  display: string;
  min: number;
  max: number;
  step: number;
  minLabel: string;
  maxLabel: string;
  hint: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="cc-slider-group">
      <div className="cc-slider-header">
        <label className="label" htmlFor={props.id}>{props.label}</label>
        <span className="cc-slider-val mono">{props.display}</span>
      </div>
      <input
        id={props.id}
        type="range"
        className="cc-slider"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={e => props.onChange(Number(e.target.value))}
      />
      <div className="cc-slider-range">
        <span>{props.minLabel}</span>
        <span className="cc-slider-hint">{props.hint}</span>
        <span>{props.maxLabel}</span>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ContractComparison() {
  const [inputs, setInputs] = useState<CvcInputs>(DEFAULT_PROGRAMME);
  const set = <K extends keyof CvcInputs>(key: K, value: CvcInputs[K]) =>
    setInputs(prev => ({ ...prev, [key]: value }));

  const result = useMemo(() => evaluate(inputs), [inputs]);
  const {
    spot, cvc, deltaCr, deltaPct, breakEvenUsdPerMt, probSpotWins, band,
    lighterage, feasibility, headline, cvcWins, profile, lockedRateUsdPerMt,
    marketRateUsdPerMt, rateDistribution, lineItems,
  } = result;

  const activePreset = PROGRAMME_PRESETS.find(
    p => p.inputs.loadPortId === inputs.loadPortId
      && p.inputs.dischargePortId === inputs.dischargePortId
      && p.inputs.vesselClass === inputs.vesselClass,
  );

  return (
    <div className="cc-page">

      {/* ① The trade, in one sentence ───────────────────────────────────── */}
      <div className={`cc-verdict ${cvcWins ? 'cc-verdict--green' : 'cc-verdict--red'}`}>
        <div className="cc-verdict__dot" />
        <p className="cc-verdict__text">{headline}</p>
        <span className="cc-verdict__tag">{cvcWins ? 'LOCK CVC' : 'STAY SPOT'}</span>
      </div>

      <div className="cc-body">

        {/* ② The programme being priced ──────────────────────────────────── */}
        <div className="card cc-scenario">
          <div className="cc-scenario__presets">
            <span className="card-title cc-scenario__presets-label">Programme</span>
            {PROGRAMME_PRESETS.map(p => (
              <button
                key={p.id}
                className={`cc-preset ${activePreset?.id === p.id ? 'cc-preset--active' : ''}`}
                title={p.hint}
                onClick={() => setInputs(prev => ({
                  ...p.inputs,
                  bunkerPriceUsd: prev.bunkerPriceUsd,
                  demurrageUsdPerDay: prev.demurrageUsdPerDay,
                  cvcDiscountPct: prev.cvcDiscountPct,
                }))}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="cc-scenario__fields">
            <div className="cc-field">
              <label className="label" htmlFor="cc-load">Load port</label>
              <select
                id="cc-load"
                className="select"
                value={inputs.loadPortId}
                onChange={e => set('loadPortId', e.target.value)}
              >
                {LOADING_PORTS.map(p => (
                  <option key={p.id} value={p.id}>{p.name}, {p.country}</option>
                ))}
              </select>
            </div>

            <div className="cc-field">
              <label className="label" htmlFor="cc-discharge">Discharge port</label>
              <select
                id="cc-discharge"
                className="select"
                value={inputs.dischargePortId}
                onChange={e => set('dischargePortId', e.target.value)}
              >
                {DISCHARGE_PORTS.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div className="cc-field">
              <label className="label" htmlFor="cc-vessel">Vessel class</label>
              <select
                id="cc-vessel"
                className="select"
                value={inputs.vesselClass}
                onChange={e => set('vesselClass', e.target.value as VesselClass)}
              >
                {VESSEL_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            <div className="cc-field">
              <label className="label" htmlFor="cc-tonnes">Cargo per voyage</label>
              <input
                id="cc-tonnes"
                className="input mono"
                type="number"
                min={10_000}
                max={200_000}
                step={1_000}
                value={inputs.cargoTonnes}
                onChange={e => set('cargoTonnes', Math.max(1_000, Number(e.target.value) || 0))}
              />
            </div>

            <div className="cc-field">
              <label className="label" htmlFor="cc-voyages">Voyages</label>
              <input
                id="cc-voyages"
                className="input mono"
                type="number"
                min={1}
                max={12}
                step={1}
                value={inputs.numVoyages}
                onChange={e => set('numVoyages', Math.min(12, Math.max(1, Number(e.target.value) || 1)))}
              />
            </div>
          </div>
        </div>

        {/* ③ What the constraint engine has to say ───────────────────────── */}
        {(feasibility.blocked || lighterage.required) && (
          <div className="cc-flags">
            {feasibility.blocked && (
              <div className="cc-flag cc-flag--block">
                <AlertTriangle size={14} />
                <span>{feasibility.reason}</span>
              </div>
            )}
            {lighterage.required && (
              <div className="cc-flag cc-flag--info">
                <Anchor size={14} />
                <span>{lighterage.reason}</span>
              </div>
            )}
          </div>
        )}

        {/* ④ The four numbers that decide it ─────────────────────────────── */}
        <div className="cc-kpis">
          <div className="cc-kpi cc-kpi--hero">
            <span className="cc-kpi__label">Programme delta</span>
            <span
              className="cc-kpi__hero mono"
              style={{ color: cvcWins ? 'var(--sig-green)' : 'var(--sig-red)' }}
            >
              {cr(Math.abs(deltaCr))}
            </span>
            <span className="cc-kpi__sub">
              {cvcWins ? 'CVC cheaper' : 'spot cheaper'} across {inputs.numVoyages} voyages · {Math.abs(deltaPct).toFixed(1)}% of programme
            </span>
          </div>

          <div className="cc-kpi">
            <span className="cc-kpi__label">Break-even spot rate</span>
            <span className="cc-kpi__val mono"><DualRate usdPerMt={breakEvenUsdPerMt} /></span>
            <span className="cc-kpi__sub">
              the average spot level where both programmes cost the same
            </span>
          </div>

          <div className="cc-kpi">
            <span className="cc-kpi__label">Chance spot wins</span>
            <span
              className="cc-kpi__val mono"
              style={{ color: probSpotWins > 0.4 ? 'var(--sig-amber)' : 'var(--chalk)' }}
            >
              {pct(probSpotWins)}
            </span>
            <span className="cc-kpi__sub">
              forecast <DualRate usdPerMt={rateDistribution.mean} /> average, ±{usd(rateDistribution.sd * 1.645).replace('$', '')} at 90%
            </span>
          </div>

          <div className="cc-kpi">
            <span className="cc-kpi__label">Locked CVC rate</span>
            <span className="cc-kpi__val mono" style={{ color: CVC_HUE }}><DualRate usdPerMt={lockedRateUsdPerMt} /></span>
            <span className="cc-kpi__sub">
              {inputs.cvcDiscountPct.toFixed(1)}% off today's <DualRate usdPerMt={marketRateUsdPerMt} /> market
            </span>
          </div>

          <div className="cc-kpi">
            <span className="cc-kpi__label">Spot total</span>
            <span className="cc-kpi__val mono">
              <DualCost usdVal={spot.totalUsd} crVal={spot.totalCr} />
            </span>
            <span className="cc-kpi__sub">whole programme, spot pricing</span>
          </div>

          <div className="cc-kpi">
            <span className="cc-kpi__label">CVC total</span>
            <span className="cc-kpi__val mono" style={{ color: CVC_HUE }}>
              <DualCost usdVal={cvc.totalUsd} crVal={cvc.totalCr} />
            </span>
            <span className="cc-kpi__sub">whole programme, locked rate</span>
          </div>
        </div>

        {/* ⑤ The two pictures ────────────────────────────────────────────── */}
        <div className="cc-charts">
          <div className="card cc-chart-card">
            <div className="cc-chart-head">
              <p className="card-title">Cumulative programme cost</p>
              <div className="cc-legend">
                <span className="cc-legend__item">
                  <i style={{ background: SPOT_HUE }} />Spot at forecast
                </span>
                <span className="cc-legend__item">
                  <i style={{ background: CVC_HUE }} />CVC locked
                </span>
              </div>
            </div>
            <CumulativeChart result={result} />
            <p className="cc-chart-note">
              Shaded band prices the spot programme at the floor and ceiling of the
              forecast's 90% interval. Spot lands anywhere from {spotVersusLock(band.lowDeltaCr)} than
              the lock to {spotVersusLock(band.highDeltaCr)}.
            </p>
          </div>

          <div className="card cc-chart-card">
            <div className="cc-chart-head">
              <p className="card-title">Where the forecast puts the average rate</p>
              <div className="cc-legend">
                <span className="cc-legend__item">
                  <i style={{ background: SPOT_HUE }} />Spot wins {pct(probSpotWins)}
                </span>
                <span className="cc-legend__item">
                  <i style={{ background: CVC_HUE }} />CVC wins {pct(1 - probSpotWins)}
                </span>
              </div>
            </div>
            <BreakEvenChart result={result} />
            <p className="cc-chart-note">
              The curve peaks at the forecast's <DualRate usdPerMt={rateDistribution.mean} /> programme average, and
              the area either side of the break-even is the probability that side comes out cheaper.
              Forecast misses travel together across months, so averaging {inputs.numVoyages} voyages
              narrows the spread far less than independent draws would.
            </p>
          </div>
        </div>

        {/* ⑥ Voyage by voyage ────────────────────────────────────────────── */}
        <div className="card cc-table-card">
          <p className="card-title">Voyage by voyage — {result.loadPortName} → {result.dischargePortName}</p>
          <div className="cc-table-scroll">
            <table className="cc-table">
              <thead>
                <tr>
                  <th>Voyage</th>
                  <th>Departs</th>
                  <th className="cc-num">Forecast rate</th>
                  <th className="cc-num cc-col-spot">Spot cost</th>
                  <th className="cc-num cc-col-cvc">CVC cost</th>
                  <th className="cc-num">CVC vs spot</th>
                </tr>
              </thead>
              <tbody>
                {spot.voyages.map((v, i) => {
                  const c = cvc.voyages[i];
                  const d = (c.total - v.total) * USD_INR / 1e7;
                  return (
                    <tr key={v.index}>
                      <td className="cc-table__label">V{v.index}</td>
                      <td className="cc-muted">{v.label}</td>
                      <td className="cc-num mono"><DualRate usdPerMt={v.rateUsdPerMt} /></td>
                      <td className="cc-num mono cc-col-spot"><DualCost usdVal={v.total} crVal={v.total * USD_INR / 1e7} /></td>
                      <td className="cc-num mono cc-col-cvc"><DualCost usdVal={c.total} crVal={c.total * USD_INR / 1e7} /></td>
                      <td className="cc-num mono" style={{ color: d <= 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                        {vsSpot(d)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="cc-table__total">
                  <td colSpan={2}>Programme</td>
                  <td className="cc-num"><DualRate usdPerMt={spot.avgRateUsdPerMt} /></td>
                  <td className="cc-num"><DualCost usdVal={spot.totalUsd} crVal={spot.totalCr} /></td>
                  <td className="cc-num"><DualCost usdVal={cvc.totalUsd} crVal={cvc.totalCr} /></td>
                  <td className="cc-num" style={{ color: cvcWins ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                    {vsSpot(-deltaCr)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {/* ⑦ Where the money actually goes ───────────────────────────────── */}
        <div className="card cc-table-card">
          <p className="card-title">Line-item breakdown — whole programme, INR crores</p>
          <div className="cc-table-scroll">
            <table className="cc-table">
              <thead>
                <tr>
                  <th>Cost component</th>
                  <th className="cc-num cc-col-spot">Spot</th>
                  <th className="cc-num cc-col-cvc">CVC</th>
                  <th className="cc-num">CVC vs spot</th>
                </tr>
              </thead>
              <tbody>
                {lineItems.map(item => {
                  const d = item.cvcCr - item.spotCr;
                  const inert = Math.abs(d) < 0.005;
                  const spotUsd = item.spotCr * 1e7 / USD_INR;
                  const cvcUsd = item.cvcCr * 1e7 / USD_INR;
                  return (
                    <tr key={item.label}>
                      <td className="cc-table__label">
                        <span>{item.label}</span>
                        {item.note && <span className="cc-note">{item.note}</span>}
                      </td>
                      <td className="cc-num mono cc-col-spot"><DualCost usdVal={spotUsd} crVal={item.spotCr} /></td>
                      <td className="cc-num mono cc-col-cvc"><DualCost usdVal={cvcUsd} crVal={item.cvcCr} /></td>
                      <td
                        className="cc-num mono"
                        style={{ color: inert ? 'var(--chalk-faint)' : d < 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}
                      >
                        {inert ? 'cancels' : vsSpot(d)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="cc-table__total">
                  <td>Total</td>
                  <td className="cc-num"><DualCost usdVal={spot.totalUsd} crVal={spot.totalCr} /></td>
                  <td className="cc-num"><DualCost usdVal={cvc.totalUsd} crVal={cvc.totalCr} /></td>
                  <td className="cc-num" style={{ color: cvcWins ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                    {vsSpot(-deltaCr)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {/* ⑧ Move the assumptions, watch everything above move ───────────── */}
        <div className="card cc-controls">
          <p className="card-title">Assumptions — everything above recomputes live</p>
          <div className="cc-sliders">
            <Slider
              id="cc-slider-discount"
              label="CVC negotiated discount"
              value={inputs.cvcDiscountPct}
              display={`${inputs.cvcDiscountPct.toFixed(1)}%`}
              min={0}
              max={25}
              step={0.5}
              minLabel="0%"
              maxLabel="25%"
              hint={
                inputs.cvcDiscountPct < 3 ? 'thin — the lock is buying certainty, not price'
                  : inputs.cvcDiscountPct > 15 ? 'unusually deep — check the owner can perform'
                    : 'typical range for a multi-voyage commitment'
              }
              onChange={v => set('cvcDiscountPct', v)}
            />

            <Slider
              id="cc-slider-bunker"
              label="Bunker price (VLSFO)"
              value={inputs.bunkerPriceUsd}
              display={`$${inputs.bunkerPriceUsd}/T`}
              min={350}
              max={950}
              step={10}
              minLabel="$350"
              maxLabel="$950"
              hint={
                inputs.bunkerPriceUsd === BUNKER_BASIS_USD ? `at the $${BUNKER_BASIS_USD} contract basis — no adjustment either way`
                  : inputs.bunkerPriceUsd > BUNKER_BASIS_USD ? 'above basis — the CVC clause absorbs most of it'
                    : 'below basis — spot keeps the whole credit'
              }
              onChange={v => set('bunkerPriceUsd', v)}
            />

            <Slider
              id="cc-slider-demurrage"
              label="Demurrage rate"
              value={inputs.demurrageUsdPerDay}
              display={`$${(inputs.demurrageUsdPerDay / 1000).toFixed(0)}k/day`}
              min={5_000}
              max={60_000}
              step={1_000}
              minLabel="$5k"
              maxLabel="$60k"
              hint={`${profile.waitDaysSpot.toFixed(1)} d expected wait on spot, ${profile.waitDaysCvc.toFixed(1)} d on a nominated window`}
              onChange={v => set('demurrageUsdPerDay', v)}
            />
          </div>
        </div>

        {/* ⑨ What the costing assumed ────────────────────────────────────── */}
        <div className="card cc-profile">
          <p className="card-title"><Ship size={12} /> Voyage profile behind these numbers</p>
          <div className="cc-profile__grid">
            <div><span>Sailed distance</span><b className="mono">{Math.round(profile.distanceNm).toLocaleString('en-IN')} nm</b></div>
            <div><span>Sea days, round trip</span><b className="mono">{profile.seaDays.toFixed(1)} d</b></div>
            <div><span>Cargo operations</span><b className="mono">{profile.cargoDays.toFixed(1)} d</b></div>
            <div><span>Expected wait, spot</span><b className="mono">{profile.waitDaysSpot.toFixed(1)} d</b></div>
            <div><span>Round trip</span><b className="mono">{profile.roundTripDays.toFixed(1)} d</b></div>
            <div><span>Bunkers burnt</span><b className="mono">{Math.round(profile.bunkerTonnes).toLocaleString('en-IN')} T</b></div>
            <div><span>Programme span</span><b className="mono">{Math.round(profile.roundTripDays * inputs.numVoyages)} d</b></div>
            <div><span>Conversion</span><b className="mono">₹{USD_INR}/$</b></div>
          </div>
        </div>

      </div>
    </div>
  );
}
