import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { apiGet } from '../lib/api';
import { useApiResource } from '../hooks/useApiResource';
import { fallbackPorts } from '../lib/fallbacks';
import type { BerthOutcome, PortEntry, PortsResponse } from '../lib/apiTypes';
import DataOriginNotice from '../components/common/DataOriginNotice';
import { sailedNm } from '../lib/geo';
import { VESSEL_SPECS, VESSEL_CLASSES, type VesselClass } from '../data/vessels';
import './Map.css';

// ─── Colours ──────────────────────────────────────────────────────────────────
const OUTCOME_COLOR: Record<BerthOutcome, string> = {
  ACCEPT_ALL_TIDE: '#3ddc84',
  ACCEPT_HIGH_TIDE_ONLY: '#f0a500',
  REJECT: '#e05c5c',
};

const OUTCOME_LABEL: Record<BerthOutcome, string> = {
  ACCEPT_ALL_TIDE: 'Berths all tide',
  ACCEPT_HIGH_TIDE_ONLY: 'High tide only',
  REJECT: 'Cannot berth',
};

const LOAD_HUE = '#5a93e8';
const CORRIDOR_HUE = '#c87941';

interface SeriesPayload {
  series: Record<string, {
    adapter: string;
    source: string;
    points: { date: string; value: number }[];
  }>;
}

const EMPTY_SERIES: SeriesPayload = { series: {} };

/** Corridor boxes, mirroring backend/data/reference/corridors.json. */
const CORRIDORS: { id: string; name: string; bounds: [[number, number], [number, number]] }[] = [
  { id: 'au_east_to_eci', name: 'East Australia', bounds: [[-35, 105], [-8, 155]] },
  { id: 'indonesia_to_eci', name: 'Indonesia', bounds: [[-8, 95], [8, 120]] },
  { id: 'moz_to_eci', name: 'Mozambique', bounds: [[-28, 32], [0, 60]] },
  { id: 'bay_of_bengal', name: 'Bay of Bengal', bounds: [[5, 80], [22.5, 95]] },
  { id: 'eci_anchorages', name: 'East Coast anchorages', bounds: [[15, 82], [22.5, 89]] },
];

/**
 * Can this class work this port, and how?
 *
 * Uses the berth rows when the backend supplied them, so the answer matches the
 * resolver. Falls back to the port's single draft figure when it did not, which
 * is coarser and says so in the popup.
 */
function resolvePortMarker(
  port: PortEntry,
  vesselClass: VesselClass,
  cargoTonnes: number,
): { outcome: BerthOutcome; detail: string; berthCount: number } {
  const spec = VESSEL_SPECS[vesselClass];
  const utilisation = Math.max(0, Math.min(1, cargoTonnes / spec.dwt.max));
  const laden = spec.ballastDraftM + (spec.ladenDraftM - spec.ballastDraftM) * utilisation;
  const required = laden + 0.4;

  if (port.berths.length === 0) {
    if (spec.loaM > port.max_loa_m) {
      return { outcome: 'REJECT', detail: `LOA ${spec.loaM} m over the ${port.max_loa_m} m limit`, berthCount: 0 };
    }
    if (required <= port.current_draft_m) {
      return { outcome: 'ACCEPT_ALL_TIDE', detail: `${laden.toFixed(1)} m inside the ${port.current_draft_m} m declared draft`, berthCount: 0 };
    }
    if (required <= port.max_draft_m) {
      return { outcome: 'ACCEPT_HIGH_TIDE_ONLY', detail: `${laden.toFixed(1)} m needs tide over the ${port.current_draft_m} m declared draft`, berthCount: 0 };
    }
    return { outcome: 'REJECT', detail: `${laden.toFixed(1)} m over the ${port.max_draft_m} m maximum`, berthCount: 0 };
  }

  const fits = port.berths.filter(b => spec.loaM <= b.loa_max_m && spec.beamM <= b.beam_max_m);
  if (fits.length === 0) {
    return { outcome: 'REJECT', detail: `No berth takes ${spec.loaM} m LOA / ${spec.beamM} m beam`, berthCount: port.berths.length };
  }
  const allTide = fits.filter(b => required <= b.draft_max_m);
  if (allTide.length) {
    const best = allTide.reduce((a, b) => (b.discharge_rate_tpd > a.discharge_rate_tpd ? b : a));
    return { outcome: 'ACCEPT_ALL_TIDE', detail: `${allTide.length} berth${allTide.length === 1 ? '' : 's'} all tide, best ${best.berth_id}`, berthCount: port.berths.length };
  }
  const onTide = fits.filter(b => required <= b.draft_max_on_tide_m);
  if (onTide.length) {
    return { outcome: 'ACCEPT_HIGH_TIDE_ONLY', detail: `${onTide.length} berth${onTide.length === 1 ? '' : 's'} on a high-water window only`, berthCount: port.berths.length };
  }
  const deepest = Math.max(...fits.map(b => b.draft_max_on_tide_m));
  return { outcome: 'REJECT', detail: `${laden.toFixed(1)} m over the deepest eligible ${deepest.toFixed(1)} m`, berthCount: port.berths.length };
}

function makePortIcon(outcome: BerthOutcome, size = 18) {
  const color = OUTCOME_COLOR[outcome];
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size + 8}" height="${size + 8}" viewBox="0 0 ${size + 8} ${size + 8}">
      <circle cx="${(size + 8) / 2}" cy="${(size + 8) / 2}" r="${size / 2 + 2}" fill="${color}22" />
      <circle cx="${(size + 8) / 2}" cy="${(size + 8) / 2}" r="${size / 2}" fill="${color}" stroke="#0d1117" stroke-width="2" />
    </svg>`;
  return L.divIcon({
    className: '', html: svg,
    iconSize: [size + 8, size + 8],
    iconAnchor: [(size + 8) / 2, (size + 8) / 2],
    popupAnchor: [0, -(size / 2 + 4)],
  });
}

function makeLoadingIcon() {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">
      <rect x="2" y="2" width="10" height="10" rx="2" fill="${LOAD_HUE}44" stroke="${LOAD_HUE}" stroke-width="1.5"/>
    </svg>`;
  return L.divIcon({ className: '', html: svg, iconSize: [14, 14], iconAnchor: [7, 7], popupAnchor: [0, -8] });
}

const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string));

function buildPopup(
  port: PortEntry,
  marker: ReturnType<typeof resolvePortMarker>,
  weather: { precip: number | null; wind: number | null; stopped: boolean },
): string {
  const color = OUTCOME_COLOR[marker.outcome];
  const berthRows = port.berths.slice(0, 6).map(b => `
    <div class="map-popup__berth">
      <span class="map-popup__berth-id">${esc(b.berth_id)}</span>
      <span>${b.draft_max_m.toFixed(1)} / ${b.draft_max_on_tide_m.toFixed(1)} m</span>
      <span>${(b.discharge_rate_tpd / 1000).toFixed(0)}k t/d</span>
    </div>`).join('');

  const source = port.berths[0]?.provenance?.source_url;
  const sourceDate = port.berths[0]?.provenance?.source_date;

  return `
    <div class="map-popup">
      <div class="map-popup__header">
        <span class="map-popup__dot" style="background:${color};box-shadow:0 0 6px ${color}"></span>
        <strong>${esc(port.name)}</strong>
        <span class="map-popup__badge" style="color:${color};border-color:${color}22;background:${color}18">${OUTCOME_LABEL[marker.outcome]}</span>
      </div>

      <div class="map-popup__reason">${esc(marker.detail)}</div>

      <div class="map-popup__grid">
        <div class="map-popup__item"><span>Berths on file</span><b>${marker.berthCount || '—'}</b></div>
        <div class="map-popup__item"><span>Deepest all tide</span><b>${port.deepest_berth_m ? port.deepest_berth_m.toFixed(1) + ' m' : '—'}</b></div>
        <div class="map-popup__item"><span>Berth queue</span><b>${port.live.wait_days !== null ? port.live.wait_days.toFixed(1) + ' d' : '—'}</b></div>
        <div class="map-popup__item"><span>At anchor</span><b>${port.live.vessels_at_anchor ?? '—'}</b></div>
        <div class="map-popup__item"><span>Rain today</span><b>${weather.precip !== null ? weather.precip.toFixed(1) + ' mm' : '—'}</b></div>
        <div class="map-popup__item"><span>Wind</span><b>${weather.wind !== null ? Math.round(weather.wind) + ' km/h' : '—'}</b></div>
      </div>

      ${berthRows ? `<div class="map-popup__berths"><div class="map-popup__berths-head"><span>berth</span><span>all tide / on tide</span><span>rate</span></div>${berthRows}</div>` : ''}
      ${weather.stopped ? `<div class="map-popup__warn">Rain above the threshold for open-berth cargo work</div>` : ''}
      ${port.lighterage_nodes.length ? `<div class="map-popup__warn">Lighterage at ${esc(port.lighterage_nodes.map(n => n.node_name).join(', '))}</div>` : ''}
      ${port.notes ? `<div class="map-popup__note">${esc(port.notes)}</div>` : ''}
      ${source ? `<a class="map-popup__src" href="${esc(source)}" target="_blank" rel="noreferrer">source · ${esc(sourceDate ?? '')}</a>` : ''}
    </div>`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function MapPage() {
  const mapRef = useRef<L.Map | null>(null);
  const mapDivRef = useRef<HTMLDivElement>(null);
  const layersRef = useRef<L.Layer[]>([]);

  const [vesselClass, setVesselClass] = useState<VesselClass>('Supramax');
  const [tonnage] = useState(55_000);
  const [destinationId, setDestinationId] = useState('paradip');
  const [showRoutes, setShowRoutes] = useState(true);
  const [showWeather, setShowWeather] = useState(false);
  const [showCorridors, setShowCorridors] = useState(false);

  const spec = VESSEL_SPECS[vesselClass];

  const ports = useApiResource<PortsResponse>(
    () => apiGet<PortsResponse>('/api/ports'), fallbackPorts(), [],
  );

  const overlays = useApiResource<SeriesPayload>(
    () => apiGet<SeriesPayload>('/api/series?prefix=weather&days=2&latest_only=true')
      .then(async w => {
        const merged: SeriesPayload = { series: { ...w.series } };
        try {
          const ais = await apiGet<SeriesPayload>('/api/series?prefix=ais&days=90&latest_only=true');
          Object.assign(merged.series, ais.series);
        } catch { /* corridor density is optional */ }
        return merged;
      }),
    EMPTY_SERIES,
    [],
  );

  const weatherFor = useMemo(() => {
    const map = new Map<string, { precip: number | null; wind: number | null; stopped: boolean }>();
    for (const p of ports.data.discharge_ports) {
      const key = p.berth_port_name;
      const get = (suffix: string) =>
        overlays.data.series[`weather.${key}.${suffix}`]?.points.at(-1)?.value ?? null;
      map.set(p.id, { precip: get('precip_mm'), wind: get('wind_kmh'), stopped: (get('work_stopped') ?? 0) >= 1 });
    }
    return map;
  }, [ports.data, overlays.data]);

  const corridorCounts = useMemo(() => {
    const out = new Map<string, number>();
    for (const c of CORRIDORS) {
      const v = overlays.data.series[`ais.corridor.${c.id}.vessel_count`]?.points.at(-1)?.value;
      if (v !== undefined) out.set(c.id, v);
    }
    return out;
  }, [overlays.data]);

  // ── Init map once ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (mapRef.current || !mapDivRef.current) return;
    const map = L.map(mapDivRef.current, {
      center: [8, 95], zoom: 3, zoomControl: false, attributionControl: false,
    });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 14 }).addTo(map);
    L.control.zoom({ position: 'topright' }).addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // ── Redraw everything when anything changes ───────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    layersRef.current.forEach(l => l.remove());
    layersRef.current = [];
    const add = (layer: L.Layer) => { layer.addTo(map); layersRef.current.push(layer); };

    const destination = ports.data.discharge_ports.find(p => p.id === destinationId);

    // Corridor density, drawn first so it sits behind everything.
    if (showCorridors) {
      const counts = [...corridorCounts.values()];
      const maxCount = Math.max(1, ...counts);
      for (const c of CORRIDORS) {
        const count = corridorCounts.get(c.id);
        const share = count !== undefined ? count / maxCount : 0;
        add(L.rectangle(c.bounds, {
          color: CORRIDOR_HUE,
          weight: 1,
          opacity: count === undefined ? 0.18 : 0.45,
          fillColor: CORRIDOR_HUE,
          fillOpacity: count === undefined ? 0.03 : 0.06 + share * 0.16,
        }).bindTooltip(
          count === undefined
            ? `${c.name} — no AIS coverage`
            : `${c.name} — ${Math.round(count)} hulls`,
          { sticky: true },
        ));
      }
    }

    // Trade lanes into the selected discharge port.
    if (showRoutes && destination) {
      for (const lp of ports.data.loading_ports) {
        const nm = sailedNm(lp.lat, lp.lng, destination.lat, destination.lng);
        const days = nm / (spec.speedKts * 24);
        add(L.polyline([[lp.lat, lp.lng], [destination.lat, destination.lng]], {
          color: LOAD_HUE, weight: 1.4, opacity: 0.4,
        }).bindTooltip(
          `${lp.name} to ${destination.name} — ${Math.round(nm).toLocaleString('en-US')} nm, ${days.toFixed(1)} d at ${spec.speedKts} kts`,
          { sticky: true },
        ));
      }
    }

    // Load ports.
    for (const lp of ports.data.loading_ports) {
      add(L.marker([lp.lat, lp.lng], { icon: makeLoadingIcon() })
        .bindPopup(`<div class="map-popup"><div class="map-popup__header"><strong>${esc(lp.name)}</strong></div>
          <div class="map-popup__note">${esc(lp.country)} · ${esc(lp.commodities.join(', '))}</div></div>`));
    }

    // Discharge ports, coloured by what this class can actually do there.
    for (const port of ports.data.discharge_ports) {
      const marker = resolvePortMarker(port, vesselClass, tonnage);
      const weather = weatherFor.get(port.id) ?? { precip: null, wind: null, stopped: false };

      add(L.marker([port.lat, port.lng], { icon: makePortIcon(marker.outcome) })
        .bindPopup(buildPopup(port, marker, weather), { maxWidth: 340 }));

      // Weather ring, sized by rainfall.
      if (showWeather && weather.precip !== null && weather.precip > 1) {
        add(L.circle([port.lat, port.lng], {
          radius: 18_000 + weather.precip * 3_500,
          color: weather.stopped ? '#e05c5c' : '#5a93e8',
          weight: 1,
          opacity: 0.5,
          fillColor: weather.stopped ? '#e05c5c' : '#5a93e8',
          fillOpacity: 0.12,
        }).bindTooltip(
          `${port.name} — ${weather.precip.toFixed(1)} mm rain${weather.wind ? `, ${Math.round(weather.wind)} km/h` : ''}${weather.stopped ? ' · work stopped' : ''}`,
          { sticky: true },
        ));
      }
    }
  }, [ports.data, vesselClass, tonnage, destinationId, showRoutes, showWeather, showCorridors, weatherFor, corridorCounts, spec.speedKts]);

  const counts = useMemo(() => {
    const tally: Record<BerthOutcome, number> = { ACCEPT_ALL_TIDE: 0, ACCEPT_HIGH_TIDE_ONLY: 0, REJECT: 0 };
    for (const p of ports.data.discharge_ports) tally[resolvePortMarker(p, vesselClass, tonnage).outcome] += 1;
    return tally;
  }, [ports.data, vesselClass, tonnage]);

  return (
    <div className="map-page">
      {/* Controls */}
      <div className="map-controls">
        <div className="map-controls__left">
          <span className="map-controls__label">Vessel Class</span>
          {VESSEL_CLASSES.map(cls => {
            const s = VESSEL_SPECS[cls];
            return (
              <button key={cls} id={`vessel-btn-${cls.toLowerCase()}`}
                className={`map-vessel-btn ${vesselClass === cls ? 'map-vessel-btn--active' : ''}`}
                style={vesselClass === cls ? { borderColor: s.color, color: s.color, background: `${s.color}18` } : {}}
                onClick={() => setVesselClass(cls)}>
                {cls}
                <span className="map-vessel-btn__spec">{s.ladenDraftM}m draft · {s.loaM}m LOA</span>
              </button>
            );
          })}
        </div>

        <div className="map-controls__right">
          <select className="select map-dest" value={destinationId}
            onChange={e => setDestinationId(e.target.value)}
            title="Routes are drawn to this discharge port">
            {ports.data.discharge_ports.map(p => (
              <option key={p.id} value={p.id}>to {p.name}</option>
            ))}
          </select>
          <button className={`btn ${showRoutes ? 'btn-active' : 'btn-ghost'}`}
            onClick={() => setShowRoutes(r => !r)}>Routes</button>
          <button className={`btn ${showWeather ? 'btn-active' : 'btn-ghost'}`}
            onClick={() => setShowWeather(w => !w)}>Weather</button>
          <button className={`btn ${showCorridors ? 'btn-active' : 'btn-ghost'}`}
            onClick={() => setShowCorridors(c => !c)}>Fleet density</button>
        </div>
      </div>

      <div className="map-notice">
        <DataOriginNotice
          origin={ports.origin}
          error={ports.error}
          stale={ports.data.sources_stale}
          bundledLabel="Backend unreachable. Ports show their single declared draft, with no berth detail, weather or fleet density."
        />
      </div>

      {/* Legend */}
      <div className="map-legend">
        {(Object.keys(OUTCOME_COLOR) as BerthOutcome[]).map(o => (
          <div key={o} className="map-legend__item">
            <span className="map-legend__dot" style={{ background: OUTCOME_COLOR[o], boxShadow: `0 0 5px ${OUTCOME_COLOR[o]}` }} />
            <span>{OUTCOME_LABEL[o]} <b className="mono">{counts[o]}</b></span>
          </div>
        ))}
        <div className="map-legend__item">
          <span className="map-legend__square" />
          <span>Loading port</span>
        </div>
      </div>

      {/* Vessel info strip */}
      <div className="map-vessel-info">
        <span className="map-vessel-info__cls" style={{ color: spec.color }}>{vesselClass}</span>
        <span>Laden Draft <b>{spec.ladenDraftM} m</b></span>
        <span>LOA <b>{spec.loaM} m</b></span>
        <span>Beam <b>{spec.beamM} m</b></span>
        <span>DWT <b>{spec.dwt.min.toLocaleString('en-US')}–{spec.dwt.max.toLocaleString('en-US')} T</b></span>
        <span className="map-vessel-info__desc">{spec.description}</span>
      </div>

      <div className="map-container" ref={mapDivRef} id="leaflet-map" />
    </div>
  );
}
