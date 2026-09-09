import { useState, useMemo } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from 'recharts';
import { MOCK_FORECAST, type ForecastHorizon } from '../data/mockForecast';
import { VESSEL_SPECS, VESSEL_CLASSES, type VesselClass } from '../data/vessels';
import './Forecast.css';

const HORIZONS: ForecastHorizon[] = ['1M', '3M', '6M'];

const HORIZON_LABEL: Record<ForecastHorizon, string> = {
  '1M': '1 Month',
  '3M': '3 Months',
  '6M': '6 Months',
};

// ─── Custom Tooltip ───────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const d = payload[0]?.payload;
  const isHistory = d?.historical !== undefined;

  return (
    <div className="forecast-tooltip">
      <p className="forecast-tooltip__date">{label}</p>
      {isHistory ? (
        <p className="forecast-tooltip__row">
          <span>Spot Rate</span>
          <b className="forecast-tooltip__val">${d.historical}/MT</b>
        </p>
      ) : (
        <>
          <p className="forecast-tooltip__row">
            <span>Forecast</span>
            <b className="forecast-tooltip__val forecast-tooltip__val--forecast">${d.forecast}/MT</b>
          </p>
          {d.lower !== undefined && (
            <p className="forecast-tooltip__row">
              <span>Range</span>
              <b className="forecast-tooltip__val forecast-tooltip__range">${d.lower} – ${d.upper}</b>
            </p>
          )}
        </>
      )}
      {d.isToday && <p className="forecast-tooltip__today">← Today</p>}
    </div>
  );
}

// ─── Custom Today label ───────────────────────────────────────────────────────
function TodayLabel({ viewBox }: any) {
  if (!viewBox) return null;
  const { x, y } = viewBox;
  return (
    <text x={x + 6} y={y + 16} fill="#60a5fa" fontSize={11} fontWeight={600} fontFamily="Inter, sans-serif">
      TODAY
    </text>
  );
}

// ─── Headline sentence generator ──────────────────────────────────────────────
function buildHeadline(cls: VesselClass, horizon: ForecastHorizon, data: ReturnType<typeof MOCK_FORECAST[VesselClass]['1M']>): string {
  const lastHistorical = [...data].reverse().find(d => d.historical !== undefined);
  const lastForecast   = [...data].reverse().find(d => d.forecast !== undefined);

  if (!lastHistorical || !lastForecast) return '';

  const current = lastHistorical.historical!;
  const predicted = lastForecast.forecast!;
  const delta = predicted - current;
  const pct = ((delta / current) * 100).toFixed(1);
  const dir = delta > 0 ? 'rise' : 'fall';
  const dirWord = delta > 0 ? 'up' : 'down';

  return `${cls} freight expected to ${dir} ${dirWord} ${Math.abs(Number(pct))}% to $${predicted}/MT over ${HORIZON_LABEL[horizon]} — ${delta > 2 ? 'consider locking CVC now' : delta < -2 ? 'spot market likely cheaper — hold chartering' : 'market stable, monitor weekly'}.`;
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function Forecast() {
  const [vesselClass, setVesselClass] = useState<VesselClass>('Supramax');
  const [horizon, setHorizon] = useState<ForecastHorizon>('3M');

  const spec = VESSEL_SPECS[vesselClass];

  const rawData = useMemo(
    () => MOCK_FORECAST[vesselClass][horizon],
    [vesselClass, horizon],
  );

  // Merge historical + forecast into one series for the chart
  const chartData = useMemo(() =>
    rawData.map(d => ({
      date: new Date(d.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }),
      historical: d.historical,
      forecast:   d.forecast,
      band:       d.lower !== undefined ? [d.lower, d.upper] : undefined,
      lower:      d.lower,
      upper:      d.upper,
      isToday:    d.isToday,
      _raw:       d,
    })),
    [rawData],
  );

  const todayIndex = chartData.findIndex(d => d.isToday);
  const todayLabel = todayIndex >= 0 ? chartData[todayIndex].date : '';

  const headline = useMemo(
    () => buildHeadline(vesselClass, horizon, rawData),
    [vesselClass, horizon, rawData],
  );

  // Stats
  const historicalPoints = rawData.filter(d => d.historical !== undefined);
  const forecastPoints   = rawData.filter(d => d.forecast !== undefined);
  const currentRate  = historicalPoints.at(-1)?.historical ?? 0;
  const peakForecast = Math.max(...forecastPoints.map(d => d.forecast!));
  const lowForecast  = Math.min(...forecastPoints.map(d => d.forecast!));

  return (
    <div className="forecast-page">
      {/* Top controls */}
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
              {h}
            </button>
          ))}
        </div>
      </div>

      {/* Stats strip */}
      <div className="forecast-stats">
        <div className="forecast-stat">
          <span className="forecast-stat__label">Current Spot</span>
          <span className="forecast-stat__val mono" style={{ color: spec.color }}>${currentRate}/MT</span>
        </div>
        <div className="forecast-stat__div" />
        <div className="forecast-stat">
          <span className="forecast-stat__label">Peak Forecast ({HORIZON_LABEL[horizon]})</span>
          <span className="forecast-stat__val mono">${peakForecast}/MT</span>
        </div>
        <div className="forecast-stat__div" />
        <div className="forecast-stat">
          <span className="forecast-stat__label">Low Forecast ({HORIZON_LABEL[horizon]})</span>
          <span className="forecast-stat__val mono">${lowForecast}/MT</span>
        </div>
        <div className="forecast-stat__div" />
        <div className="forecast-stat">
          <span className="forecast-stat__label">Baltic Index</span>
          <span className="forecast-stat__val mono" style={{ color: 'var(--accent-green)' }}>BDI 1,842 ▲</span>
        </div>
      </div>

      {/* Chart */}
      <div className="forecast-chart-wrap">
        <div className="forecast-chart-inner">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 10, bottom: 20 }}>
              <defs>
                {/* Confidence band gradient */}
                <linearGradient id="bandGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={spec.color} stopOpacity={0.15} />
                  <stop offset="95%" stopColor={spec.color} stopOpacity={0.02} />
                </linearGradient>
                {/* Historical line glow */}
                <filter id="lineGlow">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              <CartesianGrid
                strokeDasharray="3 6"
                stroke="rgba(255,255,255,0.04)"
                vertical={false}
              />

              <XAxis
                dataKey="date"
                tick={{ fill: '#4a5568', fontSize: 11, fontFamily: 'Inter' }}
                tickLine={false}
                axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                interval={Math.floor(chartData.length / 8)}
              />
              <YAxis
                tick={{ fill: '#4a5568', fontSize: 11, fontFamily: 'Inter' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${v}`}
                domain={['auto', 'auto']}
                width={48}
              />

              <Tooltip content={<CustomTooltip />} />

              {/* Today reference line */}
              {todayLabel && (
                <ReferenceLine
                  x={todayLabel}
                  stroke="#60a5fa"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  label={<TodayLabel />}
                />
              )}

              {/* Confidence band (area between lower/upper) */}
              <Area
                type="monotone"
                dataKey="upper"
                stroke="none"
                fill="url(#bandGrad)"
                fillOpacity={1}
                legendType="none"
                dot={false}
                activeDot={false}
                isAnimationActive={true}
                animationDuration={600}
              />
              <Area
                type="monotone"
                dataKey="lower"
                stroke="none"
                fill={`${spec.color}08`}
                fillOpacity={1}
                legendType="none"
                dot={false}
                activeDot={false}
                isAnimationActive={true}
                animationDuration={600}
              />

              {/* Historical line */}
              <Line
                type="monotone"
                dataKey="historical"
                stroke={spec.color}
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 5, fill: spec.color, strokeWidth: 0 }}
                filter="url(#lineGlow)"
                name="Historical Spot"
                isAnimationActive={true}
                animationDuration={600}
              />

              {/* Forecast line */}
              <Line
                type="monotone"
                dataKey="forecast"
                stroke={spec.color}
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={false}
                activeDot={{ r: 5, fill: spec.color, strokeWidth: 0, stroke: '#fff' }}
                opacity={0.75}
                name="Forecast"
                isAnimationActive={true}
                animationDuration={800}
              />

              <Legend
                wrapperStyle={{ fontSize: 12, color: '#64748b', paddingTop: 8 }}
                formatter={(value) => <span style={{ color: '#64748b' }}>{value}</span>}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Headline sentence */}
      <div className="forecast-headline">
        <span className="forecast-headline__dot" style={{ background: spec.color, boxShadow: `0 0 8px ${spec.color}` }} />
        <p className="forecast-headline__text">{headline}</p>
      </div>
    </div>
  );
}
