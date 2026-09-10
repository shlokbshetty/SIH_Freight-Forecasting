import { useMemo, useState } from 'react';
import {
  Area, AreaChart, CartesianGrid, ComposedChart, LabelList, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertTriangle, Anchor, Ship, Split } from 'lucide-react';
import { apiGet, apiPost } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { fallbackContract, fallbackPorts } from '../lib/fallbacks';
import type { ContractResponse, MultiPortResponse, PortsResponse } from '../lib/apiTypes';
import DataOriginNotice from '../components/common/DataOriginNotice';
import { DEFAULT_PROGRAMME, PROGRAMME_PRESETS } from '../data/mockContracts';
import { BUNKER_BASIS_USD } from '../data/costAssumptions';
import { normalPdf, type CvcInputs } from '../lib/cvcEngine';
import { VESSEL_CLASSES, type VesselClass } from '../data/vessels';
import './ContractComparison.css';

// ─── Series colours ───────────────────────────────────────────────────────────
// Three structures, three identities. Validated for deuteranopia, protanopia and
// tritanopia separation against the --hull surface. Green and red stay reserved
// for the verdict, so they never double as a series colour.
const SPOT_HUE = '#c87941';
const CVC_HUE = '#5a93e8';
const PTC_HUE = '#9b7fd4';

const COMMODITIES = [
  { key: 'thermal_coal', label: 'Thermal Coal' },
  { key: 'coking_coal', label: 'Coking Coal' },
  { key: 'iron_ore', label: 'Iron Ore' },
  { key: 'bauxite', label: 'Bauxite' },
  { key: 'limestone', label: 'Limestone' },
  { key: 'fertiliser', label: 'Fertiliser' },
];

// ─── Formatting ───────────────────────────────────────────────────────────────

const cr = (n: number, digits?: number) =>
  `₹${n.toFixed(digits ?? (Math.abs(n) >= 10 ? 1 : 2))} Cr`;

/** CVC measured against spot: a negative figure means the lock costs less. */
const vsSpot = (d: number) =>
  `${d >= 0 ? '+' : '−'}₹${Math.abs(d).toFixed(Math.abs(d) >= 10 ? 1 : 2)} Cr`;

const spotVersusLock = (d: number) =>
  `₹${Math.abs(d).toFixed(Math.abs(d) >= 10 ? 1 : 2)} Cr ${d >= 0 ? 'dearer' : 'cheaper'}`;

const usd = (n: number) => `$${n.toFixed(2)}`;
const pct = (n: number) => `${Math.round(n * 100)}%`;

// ─── Cumulative cost chart ────────────────────────────────────────────────────

function CumulativeTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const gap = d.cvc - d.spot;
  return (
    <div className="cc-tip">
      <p className="cc-tip__head">Voyage {d.voyage}</p>
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
        <b style={{ color: gap <= 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}>{vsSpot(gap)}</b>
      </p>
      <p className="cc-tip__foot">Forecast rate {usd(d.rate)}/T</p>
    </div>
  );
}

function endLabel(lastIndex: number, text: string, fill: string, dy: number) {
  return (props: any) => {
    if (props.index !== lastIndex) return null;
    return (
      <text x={props.x} y={props.y + dy} textAnchor="end" fill={fill}
        fontSize={11} fontWeight={600} fontFamily="IBM Plex Mono, monospace">
        {text}
      </text>
    );
  };
}

function CumulativeChart({ res }: { res: ContractResponse }) {
  const data = useMemo(() => {
    const out: { voyage: string; spot: number; cvc: number; rate: number }[] = [];
    for (const v of res.voyages) {
      const prior = out[out.length - 1];
      out.push({
        voyage: `V${v.index}`,
        spot: +((prior?.spot ?? 0) + v.spot_cr).toFixed(3),
        cvc: +((prior?.cvc ?? 0) + v.cvc_cr).toFixed(3),
        rate: v.rate_usd_per_t,
      });
    }
    return out;
  }, [res]);

  if (!data.length) return <div className="cc-chart cc-chart--empty">No voyage detail available.</div>;

  const spotOnTop = res.spot_total_cr >= res.cvc_total_cr;
  const ABOVE = -11;
  const BELOW = 18;

  return (
    <div className="cc-chart">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 22, right: 18, left: 4, bottom: 4 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis dataKey="voyage" tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }}
            tickLine={false} axisLine={{ stroke: 'rgba(255,255,255,0.08)' }} />
          <YAxis tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }} tickLine={false}
            axisLine={false} width={52} tickFormatter={(v: number) => `₹${v.toFixed(0)}`} />
          <Tooltip content={<CumulativeTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.16)' }} />
          <Line dataKey="spot" stroke={SPOT_HUE} strokeWidth={2} isAnimationActive={false}
            dot={{ r: 3.5, fill: SPOT_HUE, strokeWidth: 0 }}
            activeDot={{ r: 5.5, fill: SPOT_HUE, stroke: 'var(--hull)', strokeWidth: 2 }}>
            <LabelList dataKey="spot" content={endLabel(data.length - 1, cr(res.spot_total_cr), SPOT_HUE, spotOnTop ? ABOVE : BELOW)} />
          </Line>
          <Line dataKey="cvc" stroke={CVC_HUE} strokeWidth={2} isAnimationActive={false}
            dot={{ r: 3.5, fill: CVC_HUE, strokeWidth: 0 }}
            activeDot={{ r: 5.5, fill: CVC_HUE, stroke: 'var(--hull)', strokeWidth: 2 }}>
            <LabelList dataKey="cvc" content={endLabel(data.length - 1, cr(res.cvc_total_cr), CVC_HUE, spotOnTop ? BELOW : ABOVE)} />
          </Line>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Break-even probability ───────────────────────────────────────────────────

function rateTicks(from: number, to: number): { ticks: number[]; step: number } {
  const target = (to - from) / 5;
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(target, 1e-6)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * magnitude).find(c => c >= target) ?? magnitude * 10;
  const ticks: number[] = [];
  for (let t = Math.ceil(from / step) * step; t <= to + 1e-9; t += step) ticks.push(+t.toFixed(6));
  return { ticks, step };
}

function BreakEvenChart({ res }: { res: ContractResponse }) {
  const dist = res.rate_distribution;

  const data = useMemo(() => {
    if (!dist || dist.sd <= 0) return [];
    const be = res.break_even_usd_per_t;
    const from = Math.min(dist.mean - 3.4 * dist.sd, be - 0.6 * dist.sd);
    const to = Math.max(dist.mean + 3.4 * dist.sd, be + 0.6 * dist.sd);
    const steps = 96;
    const out: { rate: number; spotWins: number | null; cvcWins: number | null }[] = [];
    for (let i = 0; i <= steps; i++) {
      const rate = from + ((to - from) / steps) * i;
      const d = normalPdf((rate - dist.mean) / dist.sd) / dist.sd;
      out.push({
        rate: +rate.toFixed(3),
        spotWins: rate <= be ? +d.toFixed(6) : null,
        cvcWins: rate >= be ? +d.toFixed(6) : null,
      });
    }
    const dBe = normalPdf((be - dist.mean) / dist.sd) / dist.sd;
    out.push({ rate: +be.toFixed(3), spotWins: +dBe.toFixed(6), cvcWins: +dBe.toFixed(6) });
    out.sort((a, b) => a.rate - b.rate);
    return out;
  }, [dist, res.break_even_usd_per_t]);

  const axis = useMemo(
    () => (data.length ? rateTicks(data[0].rate, data[data.length - 1].rate) : { ticks: [], step: 1 }),
    [data],
  );

  if (!data.length) {
    return <div className="cc-chart cc-chart--empty">Forecast band too narrow to price this risk.</div>;
  }

  return (
    <div className="cc-chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 26, right: 14, left: 4, bottom: 4 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis dataKey="rate" type="number" domain={['dataMin', 'dataMax']}
            tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }} tickLine={false}
            axisLine={{ stroke: 'rgba(255,255,255,0.08)' }} ticks={axis.ticks}
            tickFormatter={(v: number) => `$${v.toFixed(axis.step < 1 ? 1 : 0)}`} />
          {/* Density height carries no unit the reader needs — area is the message. */}
          <YAxis hide />
          <Area dataKey="spotWins" stroke={SPOT_HUE} strokeWidth={1.5} fill={SPOT_HUE}
            fillOpacity={0.34} connectNulls={false} isAnimationActive={false} activeDot={false} />
          <Area dataKey="cvcWins" stroke={CVC_HUE} strokeWidth={1.5} fill={CVC_HUE}
            fillOpacity={0.24} connectNulls={false} isAnimationActive={false} activeDot={false} />
          <ReferenceLine x={+res.break_even_usd_per_t.toFixed(3)} stroke="var(--chalk)" strokeWidth={1.5}
            label={{
              value: `break-even ${usd(res.break_even_usd_per_t)}`, position: 'top',
              fill: 'var(--chalk)', fontSize: 10.5, fontFamily: 'IBM Plex Mono, monospace',
            }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Slider ───────────────────────────────────────────────────────────────────

function Slider(props: {
  id: string; label: string; value: number; display: string;
  min: number; max: number; step: number; minLabel: string; maxLabel: string;
  hint: string; onChange: (v: number) => void;
}) {
  return (
    <div className="cc-slider-group">
      <div className="cc-slider-header">
        <label className="label" htmlFor={props.id}>{props.label}</label>
        <span className="cc-slider-val mono">{props.display}</span>
      </div>
      <input id={props.id} type="range" className="cc-slider"
        min={props.min} max={props.max} step={props.step} value={props.value}
        onChange={e => props.onChange(Number(e.target.value))} />
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
  const [commodity, setCommodity] = useState('thermal_coal');
  const [secondPortId, setSecondPortId] = useState('haldia');

  const set = <K extends keyof CvcInputs>(key: K, value: CvcInputs[K]) =>
    setInputs(prev => ({ ...prev, [key]: value }));

  const ports = useApiResource<PortsResponse>(
    () => apiGet<PortsResponse>('/api/ports'), fallbackPorts(), [],
  );

  const contract = useApiResource<ContractResponse>(
    () => apiPost<ContractResponse>('/api/contract', {
      load_port_id: inputs.loadPortId,
      discharge_port_id: inputs.dischargePortId,
      commodity,
      vessel_class: inputs.vesselClass,
      cargo_tonnes: inputs.cargoTonnes,
      num_voyages: inputs.numVoyages,
      bunker_price_usd: inputs.bunkerPriceUsd,
      demurrage_usd_per_day: inputs.demurrageUsdPerDay,
      cvc_discount_pct: inputs.cvcDiscountPct,
    }),
    fallbackContract(inputs),
    [inputs, commodity],
  );

  const multiport = useApiResource<MultiPortResponse | null>(
    () => apiPost<MultiPortResponse>('/api/contract/multiport', {
      load_port_id: inputs.loadPortId,
      discharge_port_ids: [inputs.dischargePortId, secondPortId],
      vessel_class: inputs.vesselClass,
      commodity,
      total_tonnes: inputs.cargoTonnes,
      bunker_price_usd: inputs.bunkerPriceUsd,
      demurrage_usd_per_day: inputs.demurrageUsdPerDay,
    }),
    null,
    [inputs.loadPortId, inputs.dischargePortId, secondPortId, inputs.vesselClass, inputs.cargoTonnes, commodity, inputs.bunkerPriceUsd, inputs.demurrageUsdPerDay],
  );

  const res = contract.data;
  const cvcWins = res.delta_cr >= 0;
  const cheapest = res.cheapest_structure ?? (cvcWins ? 'cvc' : 'spot');

  const activePreset = PROGRAMME_PRESETS.find(
    p => p.inputs.loadPortId === inputs.loadPortId
      && p.inputs.dischargePortId === inputs.dischargePortId
      && p.inputs.vesselClass === inputs.vesselClass,
  );

  const dischargePorts = ports.data.discharge_ports;
  const otherPorts = dischargePorts.filter(p => p.id !== inputs.dischargePortId);

  // Probability the lock beats spot, from the same distribution the chart draws.
  const probCvc = 1 - res.prob_spot_wins;

  return (
    <div className="cc-page">
      {/* ① The trade, in one sentence ─────────────────────────────────── */}
      <div className={`cc-verdict ${cvcWins ? 'cc-verdict--green' : 'cc-verdict--red'}`}>
        <div className="cc-verdict__dot" />
        <p className="cc-verdict__text">{res.headline}</p>
        <span className="cc-verdict__tag">{cvcWins ? 'LOCK CVC' : 'STAY SPOT'}</span>
      </div>

      <div className="cc-body">
        <DataOriginNotice
          origin={contract.origin}
          error={contract.error}
          stale={res.sources_stale}
          bundledLabel="Backend unreachable. Priced with the in-browser engine: no live rates, no berth data, no time charter."
        />

        {/* ② The programme being priced ──────────────────────────────── */}
        <div className="card cc-scenario">
          <div className="cc-scenario__presets">
            <span className="card-title cc-scenario__presets-label">Programme</span>
            {PROGRAMME_PRESETS.map(p => (
              <button key={p.id} title={p.hint}
                className={`cc-preset ${activePreset?.id === p.id ? 'cc-preset--active' : ''}`}
                onClick={() => setInputs(prev => ({
                  ...p.inputs,
                  bunkerPriceUsd: prev.bunkerPriceUsd,
                  demurrageUsdPerDay: prev.demurrageUsdPerDay,
                  cvcDiscountPct: prev.cvcDiscountPct,
                }))}>
                {p.label}
              </button>
            ))}
          </div>

          <div className="cc-scenario__fields">
            <div className="cc-field">
              <label className="label" htmlFor="cc-load">Load port</label>
              <select id="cc-load" className="select" value={inputs.loadPortId}
                onChange={e => set('loadPortId', e.target.value)}>
                {ports.data.loading_ports.map(p => (
                  <option key={p.id} value={p.id}>{p.name}, {p.country}</option>
                ))}
              </select>
            </div>
            <div className="cc-field">
              <label className="label" htmlFor="cc-discharge">Discharge port</label>
              <select id="cc-discharge" className="select" value={inputs.dischargePortId}
                onChange={e => set('dischargePortId', e.target.value)}>
                {dischargePorts.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div className="cc-field">
              <label className="label" htmlFor="cc-commodity">Commodity</label>
              <select id="cc-commodity" className="select" value={commodity}
                onChange={e => setCommodity(e.target.value)}>
                {COMMODITIES.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select>
            </div>
            <div className="cc-field">
              <label className="label" htmlFor="cc-vessel">Vessel class</label>
              <select id="cc-vessel" className="select" value={inputs.vesselClass}
                onChange={e => set('vesselClass', e.target.value as VesselClass)}>
                {VESSEL_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="cc-field">
              <label className="label" htmlFor="cc-tonnes">Cargo per voyage</label>
              <input id="cc-tonnes" className="input mono" type="number"
                min={10_000} max={250_000} step={1_000} value={inputs.cargoTonnes}
                onChange={e => set('cargoTonnes', Math.max(1_000, Number(e.target.value) || 0))} />
            </div>
            <div className="cc-field">
              <label className="label" htmlFor="cc-voyages">Voyages</label>
              <input id="cc-voyages" className="input mono" type="number"
                min={1} max={12} step={1} value={inputs.numVoyages}
                onChange={e => set('numVoyages', Math.min(12, Math.max(1, Number(e.target.value) || 1)))} />
            </div>
          </div>
        </div>

        {/* ③ Constraint engine ──────────────────────────────────────── */}
        {(res.blocked_reason || res.lighterage_tonnes > 0 || res.berth) && (
          <div className="cc-flags">
            {res.blocked_reason && (
              <div className="cc-flag cc-flag--block">
                <AlertTriangle size={14} /><span>{res.blocked_reason}</span>
              </div>
            )}
            {res.berth && !res.blocked_reason && (
              <div className="cc-flag cc-flag--berth">
                <Ship size={14} />
                <span>
                  <b>{res.berth.berth_name ?? res.berth.berth_id}</b> · {res.berth.reason}
                  {res.berth.provenance.source_url && (
                    <a href={res.berth.provenance.source_url} target="_blank" rel="noreferrer" className="cc-flag__src">
                      source {res.berth.provenance.source_date}
                    </a>
                  )}
                </span>
              </div>
            )}
            {res.lighterage_tonnes > 0 && (
              <div className="cc-flag cc-flag--info">
                <Anchor size={14} />
                <span>{res.lighterage_tonnes.toLocaleString('en-US')} T lightered per voyage before berthing.</span>
              </div>
            )}
          </div>
        )}

        {/* ④ The four numbers that decide it ─────────────────────────── */}
        <div className="cc-kpis">
          <div className="cc-kpi cc-kpi--hero">
            <span className="cc-kpi__label">Programme delta</span>
            <span className="cc-kpi__hero mono" style={{ color: cvcWins ? 'var(--sig-green)' : 'var(--sig-red)' }}>
              {cr(Math.abs(res.delta_cr))}
            </span>
            <span className="cc-kpi__sub">
              {cvcWins ? 'CVC cheaper' : 'spot cheaper'} across {res.num_voyages} voyages
            </span>
          </div>
          <div className="cc-kpi">
            <span className="cc-kpi__label">Break-even spot rate</span>
            <span className="cc-kpi__val mono">{usd(res.break_even_usd_per_t)}<i>/T</i></span>
            <span className="cc-kpi__sub">the average spot level where both cost the same</span>
          </div>
          <div className="cc-kpi">
            <span className="cc-kpi__label">Chance spot wins</span>
            <span className="cc-kpi__val mono"
              style={{ color: res.prob_spot_wins > 0.4 ? 'var(--sig-amber)' : 'var(--chalk)' }}>
              {pct(res.prob_spot_wins)}
            </span>
            <span className="cc-kpi__sub">
              forecast {usd(res.forecast_avg_usd_per_t)}/T average across the programme
            </span>
          </div>
          <div className="cc-kpi">
            <span className="cc-kpi__label">Locked CVC rate</span>
            <span className="cc-kpi__val mono" style={{ color: CVC_HUE }}>{usd(res.locked_rate_usd_per_t)}<i>/T</i></span>
            <span className="cc-kpi__sub">
              {inputs.cvcDiscountPct.toFixed(1)}% off today's {usd(res.market_rate_usd_per_t)}/T market
            </span>
          </div>
        </div>

        {/* ⑤ Three structures side by side ───────────────────────────── */}
        <div className="card cc-structures">
          <p className="card-title">Contract structure — same cargo, same programme, three ways to buy it</p>
          <div className="cc-struct-grid">
            <StructureCard
              name="Single spot voyages" hue={SPOT_HUE} total={res.spot_total_cr}
              winner={cheapest === 'spot'}
              lines={[
                ['Priced at', `${res.num_voyages} separate fixtures`],
                ['Rate', `${usd(res.forecast_avg_usd_per_t)}/T forecast average`],
                ['Rate risk', 'carried in full'],
                ['Demurrage', 'charterer, on the owner’s clock'],
              ]}
              note="Every voyage at whatever the market is that week. Maximum flexibility, maximum exposure."
            />
            <StructureCard
              name="Consecutive voyage charter" hue={CVC_HUE} total={res.cvc_total_cr}
              winner={cheapest === 'cvc'}
              delta={-res.delta_cr}
              lines={[
                ['Priced at', `${res.num_voyages} voyages at one rate`],
                ['Rate', `${usd(res.locked_rate_usd_per_t)}/T locked`],
                ['Rate risk', 'transferred to the owner'],
                ['Demurrage', 'reduced by a nominated berth window'],
              ]}
              note="One rate across the programme. You give up the upside to buy certainty."
            />
            {res.ptc ? (
              <StructureCard
                name="Period time charter" hue={PTC_HUE} total={res.ptc.total_cr}
                winner={cheapest === 'ptc'}
                delta={res.ptc.vs_spot_cr * -1}
                lines={[
                  ['Priced at', `$${(res.ptc.hire_usd_per_day / 1000).toFixed(1)}k/day × ${res.ptc.hire_days.toFixed(0)} d`],
                  ['Hire', cr(res.ptc.hire_cr)],
                  ['Bunkers', `${cr(res.ptc.bunkers_cr)} — charterer buys the fuel`],
                  ['Demurrage', 'none, the waiting is your own time'],
                ]}
                note={res.ptc.note}
              />
            ) : (
              <div className="cc-struct cc-struct--empty">
                <span className="cc-struct__name">Period time charter</span>
                <p>Priced server-side. Start the backend to compare the third structure.</p>
              </div>
            )}
          </div>
        </div>

        {/* ⑥ The two pictures ────────────────────────────────────────── */}
        <div className="cc-charts">
          <div className="card cc-chart-card">
            <div className="cc-chart-head">
              <p className="card-title">Cumulative programme cost</p>
              <div className="cc-legend">
                <span className="cc-legend__item"><i style={{ background: SPOT_HUE }} />Spot at forecast</span>
                <span className="cc-legend__item"><i style={{ background: CVC_HUE }} />CVC locked</span>
              </div>
            </div>
            <CumulativeChart res={res} />
            {res.band && (
              <p className="cc-chart-note">
                At the floor and ceiling of the forecast's 90% interval, spot lands anywhere from{' '}
                {spotVersusLock(res.band.low_delta_cr)} than the lock to {spotVersusLock(res.band.high_delta_cr)}.
              </p>
            )}
          </div>

          <div className="card cc-chart-card">
            <div className="cc-chart-head">
              <p className="card-title">Where the forecast puts the average rate</p>
              <div className="cc-legend">
                <span className="cc-legend__item"><i style={{ background: SPOT_HUE }} />Spot wins {pct(res.prob_spot_wins)}</span>
                <span className="cc-legend__item"><i style={{ background: CVC_HUE }} />CVC wins {pct(probCvc)}</span>
              </div>
            </div>
            <BreakEvenChart res={res} />
            <p className="cc-chart-note">
              Area either side of the break-even is the probability that side comes out cheaper.
              Forecast misses travel together across months, so averaging {res.num_voyages} voyages
              narrows the spread far less than independent draws would.
            </p>
          </div>
        </div>

        {/* ⑦ Multi-port discharge ────────────────────────────────────── */}
        <MultiPortCard
          data={multiport.data}
          origin={multiport.origin}
          secondPortId={secondPortId}
          onSecondPort={setSecondPortId}
          options={otherPorts.map(p => ({ id: p.id, name: p.name }))}
          firstPortName={dischargePorts.find(p => p.id === inputs.dischargePortId)?.name ?? inputs.dischargePortId}
        />

        {/* ⑧ Line items ──────────────────────────────────────────────── */}
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
                {res.line_items.map(item => {
                  const d = item.cvc_cr - item.spot_cr;
                  const inert = Math.abs(d) < 0.005;
                  return (
                    <tr key={item.label}>
                      <td className="cc-table__label">
                        <span>{item.label}</span>
                        {item.note && <span className="cc-note">{item.note}</span>}
                      </td>
                      <td className="cc-num mono cc-col-spot">{cr(item.spot_cr)}</td>
                      <td className="cc-num mono cc-col-cvc">{cr(item.cvc_cr)}</td>
                      <td className="cc-num mono"
                        style={{ color: inert ? 'var(--chalk-faint)' : d < 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                        {inert ? 'cancels' : vsSpot(d)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="cc-table__total">
                  <td>Total</td>
                  <td className="cc-num">{cr(res.spot_total_cr)}</td>
                  <td className="cc-num">{cr(res.cvc_total_cr)}</td>
                  <td className="cc-num" style={{ color: cvcWins ? 'var(--sig-green)' : 'var(--sig-red)' }}>
                    {vsSpot(-res.delta_cr)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {/* ⑨ Assumptions ─────────────────────────────────────────────── */}
        <div className="card cc-controls">
          <p className="card-title">Assumptions — everything above recomputes live</p>
          <div className="cc-sliders">
            <Slider id="cc-slider-discount" label="CVC negotiated discount"
              value={inputs.cvcDiscountPct} display={`${inputs.cvcDiscountPct.toFixed(1)}%`}
              min={0} max={25} step={0.5} minLabel="0%" maxLabel="25%"
              hint={inputs.cvcDiscountPct < 3 ? 'thin — the lock is buying certainty, not price'
                : inputs.cvcDiscountPct > 15 ? 'unusually deep — check the owner can perform'
                  : 'typical range for a multi-voyage commitment'}
              onChange={v => set('cvcDiscountPct', v)} />
            <Slider id="cc-slider-bunker" label="Bunker price (VLSFO)"
              value={inputs.bunkerPriceUsd} display={`$${inputs.bunkerPriceUsd}/T`}
              min={350} max={950} step={10} minLabel="$350" maxLabel="$950"
              hint={inputs.bunkerPriceUsd === BUNKER_BASIS_USD
                ? `at the $${BUNKER_BASIS_USD} contract basis — no adjustment either way`
                : inputs.bunkerPriceUsd > BUNKER_BASIS_USD
                  ? 'above basis — the CVC clause absorbs most of it, the time charter none'
                  : 'below basis — spot keeps the whole credit'}
              onChange={v => set('bunkerPriceUsd', v)} />
            <Slider id="cc-slider-demurrage" label="Demurrage rate"
              value={inputs.demurrageUsdPerDay} display={`$${(inputs.demurrageUsdPerDay / 1000).toFixed(0)}k/day`}
              min={5_000} max={60_000} step={1_000} minLabel="$5k" maxLabel="$60k"
              hint={res.profile ? `${res.profile.wait_days_spot.toFixed(1)} d expected wait on spot` : 'expected berth waiting'}
              onChange={v => set('demurrageUsdPerDay', v)} />
          </div>
        </div>

        {/* ⑩ Voyage profile ──────────────────────────────────────────── */}
        {res.profile && (
          <div className="card cc-profile">
            <p className="card-title"><Ship size={12} /> Voyage profile behind these numbers</p>
            <div className="cc-profile__grid">
              <div><span>Sailed distance</span><b className="mono">{Math.round(res.profile.distance_nm).toLocaleString('en-US')} nm</b></div>
              <div><span>Sea days, round trip</span><b className="mono">{res.profile.sea_days.toFixed(1)} d</b></div>
              <div><span>Cargo operations</span><b className="mono">{res.profile.cargo_days.toFixed(1)} d</b></div>
              <div><span>Expected wait, spot</span><b className="mono">{res.profile.wait_days_spot.toFixed(1)} d</b></div>
              <div><span>Round trip</span><b className="mono">{res.profile.round_trip_days.toFixed(1)} d</b></div>
              <div><span>Bunkers burnt</span><b className="mono">{Math.round(res.profile.bunker_tonnes).toLocaleString('en-US')} T</b></div>
              <div><span>Programme span</span><b className="mono">{Math.round(res.profile.round_trip_days * res.num_voyages)} d</b></div>
              <div><span>Discharge berth</span><b className="mono">{res.berth?.berth_id ?? '—'}</b></div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Structure card ───────────────────────────────────────────────────────────

function StructureCard({ name, hue, total, winner, delta, lines, note }: {
  name: string; hue: string; total: number; winner: boolean;
  delta?: number; lines: [string, string][]; note: string;
}) {
  return (
    <div className={`cc-struct ${winner ? 'cc-struct--winner' : ''}`} style={winner ? { borderColor: hue } : {}}>
      <div className="cc-struct__head">
        <span className="cc-struct__name" style={{ color: hue }}>{name}</span>
        {winner && <span className="cc-struct__badge" style={{ color: hue, borderColor: hue }}>cheapest</span>}
      </div>
      <div className="cc-struct__total mono">{cr(total)}</div>
      {delta !== undefined && (
        <div className="cc-struct__delta mono" style={{ color: delta <= 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}>
          {vsSpot(delta)} vs spot
        </div>
      )}
      <div className="cc-struct__lines">
        {lines.map(([k, v]) => (
          <div key={k} className="cc-struct__line"><span>{k}</span><b>{v}</b></div>
        ))}
      </div>
      <p className="cc-struct__note">{note}</p>
    </div>
  );
}

// ─── Multi-port discharge ─────────────────────────────────────────────────────

function MultiPortCard({ data, origin, secondPortId, onSecondPort, options, firstPortName }: {
  data: MultiPortResponse | null;
  origin: string;
  secondPortId: string;
  onSecondPort: (id: string) => void;
  options: { id: string; name: string }[];
  firstPortName: string;
}) {
  return (
    <div className="card cc-multiport">
      <div className="cc-multiport__head">
        <p className="card-title"><Split size={12} /> Multi-port discharge</p>
        <div className="cc-multiport__control">
          <label className="label" htmlFor="cc-second-port">Second discharge port</label>
          <select id="cc-second-port" className="select" value={secondPortId}
            onChange={e => onSecondPort(e.target.value)}>
            {options.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>

      {!data ? (
        <p className="cc-multiport__empty">
          {origin === 'loading'
            ? 'Working out the best split…'
            : 'Split optimisation is priced server-side. Start the backend to compare it.'}
        </p>
      ) : (
        <>
          <p className="cc-multiport__verdict">{data.verdict}</p>

          <div className="cc-multiport__options">
            <OptionRow
              label={data.baseline.label}
              totalCr={data.baseline.total_cr}
              days={data.baseline.port_days}
              feasible={data.baseline.feasible}
              calls={data.baseline.calls}
              isBaseline
            />
            {data.best && (
              <OptionRow
                label={data.best.label}
                totalCr={data.best.total_cr}
                days={data.best.port_days}
                feasible={data.best.feasible}
                calls={data.best.calls}
                deltaCr={data.best.vs_baseline_cr}
              />
            )}
          </div>

          <p className="cc-multiport__note">
            {firstPortName} to {options.find(o => o.id === secondPortId)?.name} is{' '}
            {Math.round(data.inter_port_nm)} nm, about {data.inter_port_days.toFixed(1)} days of extra
            steaming. A split pays when it buys reach the single call cannot, or when two parcels
            beat a barge bill. It does not pay simply because it sounds clever.
          </p>
        </>
      )}
    </div>
  );
}

function OptionRow({ label, totalCr, days, feasible, calls, deltaCr, isBaseline }: {
  label: string; totalCr: number; days: number; feasible: boolean;
  calls: MultiPortResponse['baseline']['calls']; deltaCr?: number; isBaseline?: boolean;
}) {
  return (
    <div className={`cc-mp-option ${feasible ? '' : 'cc-mp-option--blocked'}`}>
      <div className="cc-mp-option__head">
        <span className="cc-mp-option__label">
          {isBaseline && <em>baseline</em>}
          {label}
        </span>
        <span className="cc-mp-option__total mono">{cr(totalCr)}</span>
        {deltaCr !== undefined && (
          <span className="cc-mp-option__delta mono"
            style={{ color: deltaCr <= 0 ? 'var(--sig-green)' : 'var(--sig-red)' }}>
            {deltaCr <= 0 ? '−' : '+'}₹{Math.abs(deltaCr).toFixed(2)} Cr
          </span>
        )}
      </div>
      <div className="cc-mp-calls">
        {calls.map(c => (
          <div key={`${c.port_id}-${c.tonnes}`} className={`cc-mp-call cc-mp-call--${c.outcome === 'REJECT' ? 'red' : c.outcome === 'ACCEPT_HIGH_TIDE_ONLY' ? 'amber' : 'green'}`}>
            <span className="cc-mp-call__port">{c.port_name}</span>
            <span className="mono">{c.tonnes.toLocaleString('en-US')} T</span>
            <span className="mono">arrives {c.arrival_draft_m.toFixed(2)} m</span>
            <span className="cc-mp-call__berth mono">{c.berth_id ?? '—'}</span>
          </div>
        ))}
      </div>
      <span className="cc-mp-option__days mono">{days.toFixed(1)} port and sea days</span>
    </div>
  );
}
