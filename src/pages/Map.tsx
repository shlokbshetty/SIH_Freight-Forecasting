import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { DISCHARGE_PORTS, LOADING_PORTS, getPortStatus, type Port, type PortStatus } from '../data/ports';
import { VESSEL_SPECS, VESSEL_CLASSES, type VesselClass } from '../data/vessels';
import './Map.css';

// ─── Status colours ───────────────────────────────────────────────────────────
const STATUS_COLOR: Record<PortStatus, string> = {
  available:   '#22c55e',
  constrained: '#f59e0b',
  blocked:     '#ef4444',
};

const STATUS_LABEL: Record<PortStatus, string> = {
  available:   'Available',
  constrained: 'Constrained',
  blocked:     'Blocked / Lighterage',
};

// ─── SVG marker factory ───────────────────────────────────────────────────────
function makePortIcon(status: PortStatus, size = 18) {
  const color = STATUS_COLOR[status];
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size + 8}" height="${size + 8}" viewBox="0 0 ${size + 8} ${size + 8}">
      <circle cx="${(size + 8) / 2}" cy="${(size + 8) / 2}" r="${size / 2 + 2}" fill="${color}22" />
      <circle cx="${(size + 8) / 2}" cy="${(size + 8) / 2}" r="${size / 2}" fill="${color}" stroke="#0a0f1e" stroke-width="2" />
    </svg>`;
  return L.divIcon({
    className: '',
    html: svg,
    iconSize: [size + 8, size + 8],
    iconAnchor: [(size + 8) / 2, (size + 8) / 2],
    popupAnchor: [0, -(size / 2 + 4)],
  });
}

function makeLoadingIcon() {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">
      <rect x="2" y="2" width="10" height="10" rx="2" fill="#60a5fa44" stroke="#60a5fa" stroke-width="1.5"/>
    </svg>`;
  return L.divIcon({
    className: '',
    html: svg,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -8],
  });
}

// ─── Popup HTML ───────────────────────────────────────────────────────────────
function buildPopup(port: Port, status: PortStatus): string {
  const color = STATUS_COLOR[status];
  const label = STATUS_LABEL[status];
  return `
    <div class="map-popup">
      <div class="map-popup__header">
        <span class="map-popup__dot" style="background:${color};box-shadow:0 0 6px ${color}"></span>
        <strong>${port.name}</strong>
        <span class="map-popup__badge" style="color:${color};border-color:${color}22;background:${color}18">${label}</span>
      </div>
      <div class="map-popup__grid">
        <div class="map-popup__item"><span>Max Draft</span><b>${port.maxDraftM} m</b></div>
        <div class="map-popup__item"><span>Current Draft</span><b>${port.currentDraftM} m</b></div>
        <div class="map-popup__item"><span>Max LOA</span><b>${port.maxLoaM} m</b></div>
        <div class="map-popup__item"><span>Berths Avail.</span><b>${port.berthsAvailable}/${port.berthCount}</b></div>
        <div class="map-popup__item"><span>Discharge Rate</span><b>${port.cargoRateTpd.toLocaleString()} T/day</b></div>
        <div class="map-popup__item"><span>Congestion</span><b style="text-transform:capitalize">${port.congestionLevel}</b></div>
      </div>
      ${port.lighterageRequired ? `<div class="map-popup__warn">⚠ Lighterage required at this anchorage</div>` : ''}
      ${port.notes ? `<div class="map-popup__note">${port.notes}</div>` : ''}
    </div>`;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function MapPage() {
  const mapRef = useRef<L.Map | null>(null);
  const mapDivRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<Map<string, L.Marker>>(new Map());
  const [selectedVessel, setSelectedVessel] = useState<VesselClass>('Supramax');
  const [showRoutes, setShowRoutes] = useState(true);
  const routeLinesRef = useRef<L.Polyline[]>([]);

  const vesselSpec = VESSEL_SPECS[selectedVessel];

  // ── Init map once ────────────────────────────────────────────────────────
  useEffect(() => {
    if (mapRef.current || !mapDivRef.current) return;

    const map = L.map(mapDivRef.current, {
      center: [15, 82],
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 14,
    }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.attribution({ position: 'bottomleft', prefix: '© OpenStreetMap' }).addTo(map);

    mapRef.current = map;

    // Add loading port markers (static)
    LOADING_PORTS.forEach(lp => {
      const marker = L.marker([lp.lat, lp.lng], { icon: makeLoadingIcon() });
      marker.bindPopup(`
        <div class="map-popup">
          <div class="map-popup__header">
            <span class="map-popup__dot" style="background:#60a5fa;box-shadow:0 0 6px #60a5fa"></span>
            <strong>${lp.name}</strong>
            <span class="map-popup__badge" style="color:#60a5fa;border-color:#60a5fa22;background:#60a5fa18">Loading Port</span>
          </div>
          <div class="map-popup__grid">
            <div class="map-popup__item"><span>Country</span><b>${lp.country}</b></div>
            <div class="map-popup__item"><span>Cargo</span><b>${lp.commodities.join(', ')}</b></div>
          </div>
        </div>`);
      marker.addTo(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ── Update discharge port markers when vessel changes ────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Remove old discharge markers
    markersRef.current.forEach(m => m.remove());
    markersRef.current.clear();

    DISCHARGE_PORTS.forEach(port => {
      const status = getPortStatus(port, vesselSpec.ladenDraftM, vesselSpec.loaM);
      const marker = L.marker([port.lat, port.lng], { icon: makePortIcon(status) });
      marker.bindPopup(buildPopup(port, status), { maxWidth: 280 });
      marker.addTo(map);
      markersRef.current.set(port.id, marker);
    });
  }, [selectedVessel, vesselSpec]);

  // ── Draw/clear trade route lines ─────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    routeLinesRef.current.forEach(l => l.remove());
    routeLinesRef.current = [];

    if (!showRoutes) return;

    const indiaCenter: [number, number] = [19, 84];
    LOADING_PORTS.forEach(lp => {
      const line = L.polyline([[lp.lat, lp.lng], indiaCenter], {
        color: '#3b82f633',
        weight: 1.5,
        dashArray: '6 6',
      });
      line.addTo(map);
      routeLinesRef.current.push(line);
    });
  }, [showRoutes]);

  return (
    <div className="map-page">
      {/* Controls bar */}
      <div className="map-controls">
        <div className="map-controls__left">
          <span className="map-controls__label">Vessel Class</span>
          {VESSEL_CLASSES.map(cls => {
            const spec = VESSEL_SPECS[cls];
            return (
              <button
                key={cls}
                id={`vessel-btn-${cls.toLowerCase()}`}
                className={`map-vessel-btn ${selectedVessel === cls ? 'map-vessel-btn--active' : ''}`}
                style={selectedVessel === cls ? { borderColor: spec.color, color: spec.color, background: `${spec.color}18` } : {}}
                onClick={() => setSelectedVessel(cls)}
              >
                {cls}
                <span className="map-vessel-btn__spec">
                  {spec.ladenDraftM}m draft · {spec.loaM}m LOA
                </span>
              </button>
            );
          })}
        </div>
        <div className="map-controls__right">
          <button
            id="toggle-routes-btn"
            className={`btn btn-ghost btn--sm`}
            onClick={() => setShowRoutes(r => !r)}
          >
            {showRoutes ? '🔵 Routes ON' : '⚫ Routes OFF'}
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="map-legend">
        {(Object.entries(STATUS_COLOR) as [PortStatus, string][]).map(([status, color]) => (
          <div key={status} className="map-legend__item">
            <span className="map-legend__dot" style={{ background: color, boxShadow: `0 0 5px ${color}` }} />
            <span>{STATUS_LABEL[status]}</span>
          </div>
        ))}
        <div className="map-legend__item">
          <span className="map-legend__square" />
          <span>Loading Port</span>
        </div>
      </div>

      {/* Vessel info strip */}
      <div className="map-vessel-info">
        <span className="map-vessel-info__cls" style={{ color: vesselSpec.color }}>{selectedVessel}</span>
        <span>Laden Draft <b>{vesselSpec.ladenDraftM} m</b></span>
        <span>LOA <b>{vesselSpec.loaM} m</b></span>
        <span>Beam <b>{vesselSpec.beamM} m</b></span>
        <span>DWT <b>{vesselSpec.dwt.min.toLocaleString()}–{vesselSpec.dwt.max.toLocaleString()} T</b></span>
        <span className="map-vessel-info__desc">{vesselSpec.description}</span>
      </div>

      {/* Map container */}
      <div className="map-container" ref={mapDivRef} id="leaflet-map" />
    </div>
  );
}
