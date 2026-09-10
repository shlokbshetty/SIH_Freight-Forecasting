import { useMemo, useState } from 'react';
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { apiGet, apiPost } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { fallbackForecast } from '../lib/fallbacks';
import type { ForecastResponse } from '../lib/apiTypes';
import DataOriginNotice from '../components/common/DataOriginNotice';
import { VESSEL_SPECS, VESSEL_CLASSES, type VesselClass } from '../data/vessels';
import './Forecast.css';

// Horizons the backend accepts, in days.
const HORIZONS = [30, 90, 180] as const;
type Horizon = (typeof HORIZONS)[number];

const HORIZON_LABEL: Record<Horizon, string> = { 30: '1 Month', 90: '3 Months', 180: '6 Months' };

// Diverging pair for driver contributions: warm pushes the rate up, cool pulls
// it down, and they must read as opposites.
const UP_HUE = '#c87941';
const DOWN_HUE = '#5a93e8';

interface BdiPayload {
  series: Record<string, { source: string; is_proxy: boolean; points: { date: string; value: number }[] }>;
}

function ForecastTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="fc-tip">
      <p className="fc-tip__date">{label}</p>
      {d.historical !== undefined && d.historical !== null && (
        <p className="fc-tip__row"><span>Observed</span><b>${d.historical.toFixed(2)}/T</b></p>
      )}
      {d.forecast !== undefined && d.forecast !== null && (
        <>
          <p className="fc-tip__row"><span>Forecast</span><b>${d.forecast.toFixed(2)}/T</b></p>
          {d.p80 && (
            <p className="fc-tip__row fc-tip__row--dim">
              <span>80% band</span><b>${d.p80[0].toFixed(2)} – ${d.p80[1].toFixed(2)}</b>
            </p>
          )}
          {d.p95 && (
            <p className="fc-tip__row fc-tip__row--dim">
              <span>95% band</span><b>${d.p95[0].toFixed(2)} – ${d.p95[1].toFixed(2)}</b>
            </p>
          )}
        </>
      )}
    </div>
  );
}

function buildHeadline(res: ForecastResponse, horizon: Horizon): string {
  const current = res.history.at(-1)?.value;
  const predicted = res.forecast.at(-1)?.value;
  if (current === undefined || predicted === undefined) return 'No forecast available for this class.';

  const pct = ((predicted - current) / current) * 100;
  const direction = pct > 0 ? 'rise' : 'fall';
  const advice = pct > 4
    ? 'locking a multi-voyage rate now looks cheap against the curve'
    : pct < -4
      ? 'spot is likely to be the cheaper way to buy this programme'
      : 'the market is close to flat, so the lock is buying certainty rather than price';

  return `${res.vessel_class} freight forecast to ${direction} ${Math.abs(pct).toFixed(1)}% to `
    + `$${predicted.toFixed(2)}/T over ${HORIZON_LABEL[horizon].toLowerCase()}. On that curve, ${advice}.`;
}

export default function Forecast() {
  const [vesselClass, setVesselClass] = useState<VesselClass>('Supramax');
  const [horizon, setHorizon] = useState<Horizon>(90);
  const spec = VESSEL_SPECS[vesselClass];

  const forecast = useApiResource<ForecastResponse>(
    () => apiPost<ForecastResponse>('/api/forecast', {
      vessel_class: vesselClass,
      horizon_days: horizon,
      history_days: 180,
    }),
    fallbackForecast(vesselClass, horizon),
    [vesselClass, horizon],
  );

  const bdi = useApiResource<BdiPayload>(
    () => apiGet<BdiPayload>('/api/series?metrics=baltic.bdi&days=30'),
    { series: {} },
    [],
  );

  const res = forecast.data;

  const chartData = useMemo(() => {
    const fmt = (iso: string) =>
      new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });

    const history = res.history.map(p => ({
      date: fmt(p.date), historical: p.value, forecast: null as number | null,
    }));

    const p80 = new Map(res.intervals.p80.map(p => [p.date, [p.lower, p.upper] as [number, number]]));
    const p95 = new Map(res.intervals.p95.map(p => [p.date, [p.lower, p.upper] as [number, number]]));

    const forward = res.forecast.map(p => ({
      date: fmt(p.date),
      historical: null as number | null,
      forecast: p.value,
      p80: p80.get(p.date),
      p95: p95.get(p.date),
    }));

    // Join the two limbs at today so the line is continuous.
    if (history.length && forward.length) {
      history[history.length - 1] = {
        ...history[history.length - 1],
        forecast: history[history.length - 1].historical,
      };
    }
    return [...history, ...forward];
  }, [res]);

  const todayLabel = chartData[res.history.length - 1]?.date;
  const headline = useMemo(() => buildHeadline(res, horizon), [res, horizon]);

  const current = res.history.at(-1)?.value ?? 0;
  const forwardValues = res.forecast.map(p => p.value);
  const peak = forwardValues.length ? Math.max(...forwardValues) : 0;
  const low = forwardValues.length ? Math.min(...forwardValues) : 0;

  const bdiSeries = bdi.data.series['baltic.bdi'];
  const bdiPoints = bdiSeries?.points ?? [];
  const bdiNow = bdiPoints.at(-1)?.value ?? null;
  const bdiPrev = bdiPoints.at(-6)?.value ?? null;
  const bdiMove = bdiNow !== null && bdiPrev ? ((bdiNow - bdiPrev) / bdiPrev) * 100 : null;

  const maxDriver = Math.max(1e-6, ...res.drivers.map(d => Math.abs(d.contribution)));

  return (
    <div className="forecast-page">
      {/* Controls */}
      <div className="forecast-controls">
        <div className="forecast-controls__left">
          <span className="map-controls__label">Vessel Class</span>
          {VESSEL_CLASSES.map(cls => (
            <button
              key={cls}
              id={`forecast-vessel-${cls.toLowerCase()}`}
              className={`forecast-cls-btn ${vesselClass === cls ? 'forecast-cls-btn--active' : ''}`}
              style={vesselClass === cls ? {
                borderColor: VESSEL_SPECS[cls].color,
                color: VESSEL_SPECS[cls].color,
                background: `${VESSEL_SPECS[cls].color}18`,
              } : {}}
              onClick={() => setVesselClass(cls)}
            >
              {cls}
            </button>
          ))}
        </div>

        <div className="forecast-controls__right">
          <span className="map-controls__label">Horizon</span>
          {HORIZONS.map(h => (
            <button
              key={h}
              id={`horizon-btn-${h}`}
              className={`forecast-horizon-btn ${horizon === h ? 'forecast-horizon-btn--active' : ''}`}
              onClick={() => setHorizon(h)}
            >
              {h}d
            </button>
          ))}
        </div>
      </div>

      <div className="forecast-notice">
        <DataOriginNotice
          origin={forecast.origin}
          error={forecast.error}
          stale={res.sources_stale}
          bundledLabel="Backend unreachable. Showing the bundled series: no fitted model, no backtest, no drivers."
        />
        <span className={`fc-model fc-model--${res.model === 'sarimax' ? 'ok' : 'weak'}`}>
          {res.model === 'sarimax' ? 'SARIMAX' : res.model === 'bundled' ? 'bundled series' : 'random-walk fallback'}
        </span>
      </div>

      {/* Stats strip */}
      <div className="forecast-stats">
        <div className="forecast-stat">
          <span className="forecast-stat__label">Current Spot</span>
          <span className="forecast-stat__val mono" style={{ color: spec.color }}>${current.toFixed(2)}/T</span>
        </div>
        <div className="forecast-stat__div" />
        <div className="forecast-stat">
          <span className="forecast-stat__label">Peak ({HORIZON_LABEL[horizon]})</span>
          <span className="forecast-stat__val mono">${peak.toFixed(2)}/T</span>
        </div>
        <div className="forecast-stat__div" />
        <div className="forecast-stat">
          <span className="forecast-stat__label">Low ({HORIZON_LABEL[horizon]})</span>
          <span className="forecast-stat__val mono">${low.toFixed(2)}/T</span>
        </div>
        <div className="forecast-stat__div" />
        <div className="forecast-stat">
          <span className="forecast-stat__label">
            Baltic Dry {bdiSeries?.is_proxy && <em className="fc-proxy" title="Contract-for-difference quote tracking the licensed index, not a Baltic assessment">proxy</em>}
          </span>
          <span className="forecast-stat__val mono">
            {bdiNow === null ? '—' : bdiNow.toFixed(0)}
            {bdiMove !== null && (
              <em className={bdiMove >= 0 ? 'fc-up' : 'fc-down'}>
                {bdiMove >= 0 ? '▲' : '▼'} {Math.abs(bdiMove).toFixed(1)}%
              </em>
            )}
          </span>
        </div>
        <div className="forecast-stat__div" />
        <div className="forecast-stat">
          <span className="forecast-stat__label">Backtest ({horizon}d)</span>
          <span className="forecast-stat__val mono">
            {res.accuracy.mape === null
              ? <span className="fc-muted">not trained</span>
              : <>MAPE {res.accuracy.mape.toFixed(1)}%</>}
          </span>
        </div>
      </div>

      {/* Chart */}
      <div className="forecast-chart-wrap">
        <div className="forecast-chart-inner">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 20, right: 28, left: 10, bottom: 16 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
                interval={Math.max(1, Math.floor(chartData.length / 8))}
              />
              <YAxis
                tick={{ fill: 'var(--chalk-faint)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                domain={['auto', 'auto']}
                width={50}
              />
              <Tooltip content={<ForecastTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.16)' }} />

              {/* Wider band behind the narrower one, so both read. */}
              <Area dataKey="p95" stroke="none" fill={spec.color} fillOpacity={0.08} isAnimationActive={false} activeDot={false} />
              <Area dataKey="p80" stroke="none" fill={spec.color} fillOpacity={0.16} isAnimationActive={false} activeDot={false} />

              {todayLabel && (
                <ReferenceLine
                  x={todayLabel}
                  stroke="var(--chalk-faint)"
                  strokeWidth={1}
                  label={{ value: 'today', position: 'top', fill: 'var(--chalk-dim)', fontSize: 10.5 }}
                />
              )}

              <Line dataKey="historical" name="Observed" stroke={spec.color} strokeWidth={2}
                dot={false} connectNulls isAnimationActive={false}
                activeDot={{ r: 5, fill: spec.color, stroke: 'var(--hull)', strokeWidth: 2 }} />
              <Line dataKey="forecast" name="Forecast" stroke={spec.color} strokeWidth={2}
                strokeDasharray="5 4" dot={false} connectNulls opacity={0.8} isAnimationActive={false}
                activeDot={{ r: 5, fill: spec.color, stroke: 'var(--hull)', strokeWidth: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="fc-legend">
          <span className="fc-legend__item"><i style={{ background: spec.color }} />Observed</span>
          <span className="fc-legend__item"><i style={{ background: spec.color, opacity: 0.55 }} />Forecast</span>
          <span className="fc-legend__item"><i style={{ background: spec.color, opacity: 0.16 }} />80% band</span>
          <span className="fc-legend__item"><i style={{ background: spec.color, opacity: 0.08 }} />95% band</span>
        </div>
      </div>

      {/* Drivers and accuracy */}
      <div className="fc-lower">
        <div className="card fc-drivers">
          <p className="card-title">What is moving the {horizon}-day number</p>
          {res.drivers.length === 0 ? (
            <p className="fc-muted fc-drivers__empty">
              Driver attribution comes from the fitted model. Run <code>train.py</code> on the backend
              to populate it.
            </p>
          ) : (
            <div className="fc-driver-list">
              {res.drivers.map(d => {
                const share = Math.abs(d.contribution) / maxDriver;
                const up = d.contribution >= 0;
                return (
                  <div key={d.key ?? d.feature} className="fc-driver">
                    <span className="fc-driver__name">{d.feature}</span>
                    <span className="fc-driver__track">
                      <span
                        className="fc-driver__bar"
                        style={{ width: `${Math.max(2, share * 100)}%`, background: up ? UP_HUE : DOWN_HUE }}
                      />
                    </span>
                    <span className="fc-driver__val mono" style={{ color: up ? UP_HUE : DOWN_HUE }}>
                      {up ? '+' : '−'}${Math.abs(d.contribution).toFixed(2)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          <p className="fc-drivers__note">
            Each figure is dollars per tonne of the forecast level attributable to that regressor
            sitting where it does, relative to its training average.
          </p>
        </div>

        <div className="card fc-accuracy">
          <p className="card-title">Out-of-sample accuracy</p>
          {res.accuracy.mape === null ? (
            <p className="fc-muted">
              No backtest yet. The backend writes <code>models/metrics.json</code> when
              <code> train.py</code> runs.
            </p>
          ) : (
            <div className="fc-acc-rows">
              <div className="fc-acc-row">
                <span>MAPE at {res.accuracy.horizon_days}d</span>
                <b className="mono">{res.accuracy.mape.toFixed(2)}%</b>
              </div>
              <div className="fc-acc-row">
                <span>RMSE at {res.accuracy.horizon_days}d</span>
                <b className="mono">${res.accuracy.rmse?.toFixed(3)}/T</b>
              </div>
              <div className="fc-acc-row">
                <span>Method</span>
                <b className="mono">{res.accuracy.backtest ?? '—'}</b>
              </div>
              <div className="fc-acc-row">
                <span>Folds</span>
                <b className="mono">{res.accuracy.folds ?? '—'}</b>
              </div>
            </div>
          )}
          {res.notes.length > 0 && (
            <ul className="fc-notes">
              {res.notes.map(n => <li key={n}>{n}</li>)}
            </ul>
          )}
        </div>
      </div>

      {/* Headline */}
      <div className="forecast-headline">
        <span className="forecast-headline__dot" style={{ background: spec.color, boxShadow: `0 0 8px ${spec.color}` }} />
        <p className="forecast-headline__text">{headline}</p>
      </div>
    </div>
  );
}
