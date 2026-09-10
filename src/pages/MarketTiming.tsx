import { useMemo, useState } from 'react';
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { CalendarDays, TrendingDown, TrendingUp } from 'lucide-react';
import { apiPost } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { fallbackForecast } from '../lib/fallbacks';
import type { ForecastResponse } from '../lib/apiTypes';
import DataOriginNotice from '../components/common/DataOriginNotice';
import { VESSEL_CLASSES, VESSEL_SPECS, type VesselClass } from '../data/vessels';
import './MarketTiming.css';

const HUE = '#c87941';
const COOL = '#5a93e8';

type Grade = 'green' | 'amber' | 'red';

interface Week {
  index: number;
  label: string;
  date: string;
  rate: number;
  spread: number;
  vsToday: number;
  grade: Grade;
  reason: string;
}

const GRADE_LABEL: Record<Grade, string> = {
  green: 'Good entry',
  amber: 'Neutral',
  red: 'Poor entry',
};

/**
 * Grade each week of the forecast window.
 *
 * Two things make a week a good time to fix. The rate itself, relative to the
 * rest of the window, and how confident the forecast is about it. A cheap week
 * the model is unsure of is not the same buy as a cheap week it is sure of, and
 * grading on price alone would hide that.
 */
function gradeWeeks(res: ForecastResponse): Week[] {
  const today = res.history.at(-1)?.value ?? 0;
  const p80 = new Map(res.intervals.p80.map(p => [p.date, p]));

  // Sample the daily forecast weekly.
  const weekly = res.forecast.filter((_, i) => i % 7 === 0).slice(0, 16);
  if (!weekly.length) return [];

  const rates = weekly.map(p => p.value);
  const min = Math.min(...rates);
  const max = Math.max(...rates);
  const span = Math.max(1e-6, max - min);

  const spreads = weekly.map(p => {
    const band = p80.get(p.date);
    return band ? (band.upper - band.lower) / Math.max(1e-6, p.value) : 0;
  });
  const maxSpread = Math.max(1e-6, ...spreads);

  return weekly.map((p, i) => {
    const priceScore = (p.value - min) / span;          // 0 cheapest, 1 dearest
    const uncertainty = spreads[i] / maxSpread;          // 0 tightest, 1 widest
    // Price dominates; uncertainty is a penalty on top of it.
    const score = priceScore * 0.7 + uncertainty * 0.3;

    const grade: Grade = score < 0.34 ? 'green' : score < 0.67 ? 'amber' : 'red';
    const vsToday = today > 0 ? ((p.value - today) / today) * 100 : 0;

    const reason = grade === 'green'
      ? `Near the cheapest point of the window, ${Math.abs(vsToday).toFixed(1)}% ${vsToday <= 0 ? 'below' : 'above'} today.`
      : grade === 'red'
        ? uncertainty > 0.7
          ? 'Dear and the band is at its widest, so the forecast is least reliable here.'
          : `Toward the top of the window, ${vsToday.toFixed(1)}% above today.`
        : 'Middle of the window on both price and confidence.';

    return {
      index: i,
      label: i === 0 ? 'This week' : `+${i}w`,
      date: p.date,
      rate: p.value,
      spread: spreads[i],
      vsToday,
      grade,
      reason,
    };
  });
}

export default function MarketTiming() {
  const [vesselClass, setVesselClass] = useState<VesselClass>('Supramax');
  const [tonnage, setTonnage] = useState(55_000);
  const [voyages, setVoyages] = useState(4);
  const [selected, setSelected] = useState(0);

  const spec = VESSEL_SPECS[vesselClass];

  const forecast = useApiResource<ForecastResponse>(
    () => apiPost<ForecastResponse>('/api/forecast', {
      vessel_class: vesselClass, horizon_days: 180, history_days: 60,
    }),
    fallbackForecast(vesselClass, 180),
    [vesselClass],
  );

  const res = forecast.data;
  const weeks = useMemo(() => gradeWeeks(res), [res]);
  const today = res.history.at(-1)?.value ?? 0;
  const best = useMemo(
    () => weeks.reduce((a, b) => (b.rate < a.rate ? b : a), weeks[0]),
    [weeks],
  );

  // ── Forward curve: lock now against waiting ─────────────────────────────────
  const programmeTonnes = tonnage * voyages;
  const USD_INR = 88.4;

  const delayRows = useMemo(() => {
    return [0, 1, 2, 3, 4].map(w => {
      // Week zero is today's observed rate. Using the first forecast point here
      // would compare the forecast against itself and always read zero.
      const rate = w === 0 ? today : (weeks[w]?.rate ?? today);
      const deltaUsd = (rate - today) * programmeTonnes;
      return {
        weeks: w,
        rate,
        deltaCr: (deltaUsd * USD_INR) / 1e7,
        spread: weeks[w]?.spread ?? 0,
      };
    });
  }, [weeks, today, programmeTonnes]);

  const chartData = useMemo(() => weeks.map(w => ({
    label: w.label,
    rate: +w.rate.toFixed(2),
    grade: w.grade,
  })), [weeks]);

  // Freight moves in cents over a few weeks, so whole-dollar ticks would print
  // the same label four times down the axis.
  const rateDecimals = useMemo(() => {
    if (!chartData.length) return 0;
    const values = chartData.map(d => d.rate).concat(today || []);
    const span = Math.max(...values) - Math.min(...values);
    return span >= 8 ? 0 : span >= 1.5 ? 1 : 2;
  }, [chartData, today]);

  const selectedWeek = weeks[selected] ?? weeks[0];

  return (
    <div className="page-content timing-page">
      <div className="timing-head">
        <div>
          <h1>Market Entry Timing</h1>
          <p>When to fix this programme, and what waiting costs if you do not.</p>
        </div>
        <div className="timing-controls">
          {VESSEL_CLASSES.map(c => (
            <button key={c}
              className={`forecast-cls-btn ${vesselClass === c ? 'forecast-cls-btn--active' : ''}`}
              style={vesselClass === c ? {
                borderColor: VESSEL_SPECS[c].color, color: VESSEL_SPECS[c].color,
                background: `${VESSEL_SPECS[c].color}18`,
              } : {}}
              onClick={() => { setVesselClass(c); setSelected(0); }}>
              {c}
            </button>
          ))}
        </div>
      </div>

      <DataOriginNotice
        origin={forecast.origin}
        error={forecast.error}
        stale={res.sources_stale}
        bundledLabel="Backend unreachable. Windows are graded off the bundled series, with no fitted model behind them."
      />

      {/* Headline */}
      {best && (
        <div className={`timing-verdict timing-verdict--${best.grade}`}>
          <CalendarDays size={16} />
          <p>
            Cheapest window for {vesselClass} is <b>{best.label}</b> at{' '}
            <b>${best.rate.toFixed(2)}/T</b>
            {best.index === 0
              ? ', which is now. Waiting only costs money on this curve.'
              : Math.abs(best.vsToday) < 0.05
                ? `, level with today's $${today.toFixed(2)}/T. The curve gives you no reason to hurry, and none to wait.`
                : `, ${Math.abs(best.vsToday).toFixed(1)}% ${best.vsToday <= 0 ? 'below' : 'above'} today's $${today.toFixed(2)}/T.`}
          </p>
        </div>
      )}

      {/* ── Window calendar ───────────────────────────────────────────── */}
      <section className="card timing-calendar">
        <p className="card-title">Charter window calendar — next {weeks.length} weeks</p>
        <div className="timing-grid">
          {weeks.map(w => (
            <button key={w.index}
              className={`timing-cell timing-cell--${w.grade} ${selected === w.index ? 'timing-cell--selected' : ''}`}
              onClick={() => setSelected(w.index)}>
              <span className="timing-cell__label">{w.label}</span>
              <span className="timing-cell__rate mono">${w.rate.toFixed(2)}</span>
              <span className="timing-cell__delta mono">
                {w.vsToday >= 0 ? '+' : '−'}{Math.abs(w.vsToday).toFixed(1)}%
              </span>
            </button>
          ))}
        </div>

        <div className="timing-legend">
          {(['green', 'amber', 'red'] as Grade[]).map(g => (
            <span key={g} className="timing-legend__item">
              <i className={`timing-swatch timing-swatch--${g}`} />{GRADE_LABEL[g]}
            </span>
          ))}
        </div>

        {selectedWeek && (
          <div className="timing-detail">
            <div className="timing-detail__head">
              <span className={`badge badge-${selectedWeek.grade === 'green' ? 'green' : selectedWeek.grade === 'amber' ? 'amber' : 'red'}`}>
                {GRADE_LABEL[selectedWeek.grade]}
              </span>
              <b>{selectedWeek.label}</b>
              <span className="mono">{new Date(selectedWeek.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
            </div>
            <p>{selectedWeek.reason}</p>
            <p className="timing-detail__band mono">
              80% band width {(selectedWeek.spread * 100).toFixed(1)}% of the rate
            </p>
          </div>
        )}
      </section>

      {/* ── Forward curve ─────────────────────────────────────────────── */}
      <div className="timing-lower">
        <section className="card timing-curve">
          <p className="card-title">
            Forward curve — {vesselClass}, next {weeks.length} weeks
            <span className="timing-curve__today mono">today ${today.toFixed(2)}/T</span>
          </p>
          <div className="timing-chart">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 18, right: 18, left: 4, bottom: 4 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: 'var(--chalk-faint)', fontSize: 10 }}
                  tickLine={false} axisLine={{ stroke: 'rgba(255,255,255,0.08)' }} interval={1} />
                <YAxis tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }} tickLine={false}
                  axisLine={false} width={48} domain={['auto', 'auto']}
                  tickFormatter={(v: number) => `$${v.toFixed(rateDecimals)}`} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--deck)', border: '1px solid var(--rule-strong)',
                    borderRadius: 4, fontSize: 12,
                  }}
                  labelStyle={{ color: 'var(--chalk)' }}
                  formatter={(v: unknown) => [`$${Number(v).toFixed(2)}/T`, 'Forecast'] as [string, string]} />
                <ReferenceLine y={today} stroke="var(--chalk-faint)" strokeWidth={1} />
                <Area dataKey="rate" stroke="none" fill={spec.color} fillOpacity={0.1} isAnimationActive={false} />
                <Line dataKey="rate" stroke={spec.color} strokeWidth={2} isAnimationActive={false}
                  dot={{ r: 3, fill: spec.color, strokeWidth: 0 }}
                  activeDot={{ r: 5, fill: spec.color, stroke: 'var(--hull)', strokeWidth: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card timing-delay">
          <div className="timing-delay__head">
            <p className="card-title">What delaying costs</p>
            <div className="timing-delay__inputs">
              <label className="label" htmlFor="timing-tonnes">Per voyage</label>
              <input id="timing-tonnes" className="input mono" type="number" min={10000} step={5000}
                value={tonnage} onChange={e => setTonnage(Math.max(1000, Number(e.target.value) || 0))} />
              <label className="label" htmlFor="timing-voyages">Voyages</label>
              <input id="timing-voyages" className="input mono" type="number" min={1} max={12}
                value={voyages} onChange={e => setVoyages(Math.min(12, Math.max(1, Number(e.target.value) || 1)))} />
            </div>
          </div>

          <table className="timing-table">
            <thead>
              <tr>
                <th>Fix</th>
                <th className="timing-num">Rate</th>
                <th className="timing-num">Programme cost vs fixing today</th>
              </tr>
            </thead>
            <tbody>
              {delayRows.map(r => (
                <tr key={r.weeks} className={r.weeks === 0 ? 'timing-table__now' : ''}>
                  <td>{r.weeks === 0 ? 'Today' : `In ${r.weeks} week${r.weeks === 1 ? '' : 's'}`}</td>
                  <td className="timing-num mono">${r.rate.toFixed(2)}/T</td>
                  <td className="timing-num mono" style={{
                    color: r.weeks === 0 || Math.abs(r.deltaCr) < 0.005 ? 'var(--chalk-faint)'
                      : r.deltaCr > 0 ? 'var(--sig-red)' : 'var(--sig-green)',
                  }}>
                    {r.weeks === 0 || Math.abs(r.deltaCr) < 0.005 ? '—' : (
                      <>
                        {r.deltaCr > 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}{' '}
                        {r.deltaCr >= 0 ? '+' : '−'}₹{Math.abs(r.deltaCr).toFixed(2)} Cr
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="timing-delay__note">
            Priced on {programmeTonnes.toLocaleString('en-US')} T across {voyages} voyages. A positive
            figure is what waiting adds to the programme if the forecast is right. It is not a
            forecast of the fixture you would actually get: a market that moves against you usually
            moves the owner's willingness to commit as well.
          </p>
        </section>
      </div>

      <p className="timing-footnote" style={{ borderTopColor: COOL, color: 'var(--chalk-faint)' }}>
        Windows are graded on where the forecast sits inside its own range, weighted seven to three
        against how wide the 80% band is that week. A cheap week the model is unsure of does not
        score as well as a cheap week it is confident about.
        <span style={{ color: HUE }}> Grading is relative to this window only</span>, so every
        forecast has a best week even when none of them is a good absolute level.
      </p>
    </div>
  );
}
