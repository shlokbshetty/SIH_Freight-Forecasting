/**
 * Interactive Maritime Map — Stage 3 Full Stack Integration
 *
 * Features:
 * - Esri World Dark Gray tiles (100% free, 0 API key required, sleek dark UI)
 * - Catmull-Rom Spline Smoothing for silky-smooth, curved maritime sea lanes
 * - Canonical regional routing engine for all 15 x 15 port combinations (0 land cutting!)
 * - High-tech top-down vector SVG cargo vessel icon with dynamic 360° heading rotation
 * - Lighterage visual alerts (Sagar/Sandheads transshipment, dashed orange polyline, warning badge)
 * - Interactive port marker click selection & distance tooltips
 * - Automatic map resize handling (eliminates tile gaps)
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { fetchPorts, evaluate, horizonToVoyages } from '../lib/evaluateApi';
import type { PortResponse, EvaluationResult } from '../lib/evaluateApi';
import { apiPost } from '../lib/api';
import type { BerthOutcome, MatchResponse } from '../lib/apiTypes';
import './Map.css';

// ─── Maritime Shipping Waypoints & Regions ────────────────────────────────────

const WP_SRI_LANKA: [number, number]          = [5.5, 80.5];     // South of Sri Lanka
const WP_MALACCA_NORTH: [number, number]      = [5.8, 95.2];     // North entry of Malacca Strait
const WP_MALACCA_SOUTH: [number, number]      = [1.2, 103.8];    // Singapore / Malacca entrance
const WP_LOMBOK: [number, number]             = [-8.7, 115.7];    // Lombok Strait, Indonesia
const WP_SUNDA: [number, number]              = [-6.0, 105.8];    // Sunda Strait, Indonesia
const WP_JAVA_SEA: [number, number]           = [-4.5, 109.0];    // Java Sea
const WP_TORRES_STRAIT: [number, number]      = [-10.5, 142.2];  // Torres Strait (North of Australia)
const WP_ARAFURA_SEA: [number, number]        = [-9.5, 136.0];    // Arafura Sea (North of Australia)
const WP_TIMOR_SEA: [number, number]          = [-8.5, 126.0];    // Timor Sea
const WP_BASS_STRAIT: [number, number]         = [-39.5, 146.0];  // Bass Strait (South of Melbourne)
const WP_GREAT_AUST_BIGHT: [number, number]   = [-38.0, 130.0];  // Great Australian Bight
const WP_CAPE_LEEUWIN: [number, number]       = [-36.0, 115.0];  // Cape Leeuwin, WA
const WP_CAPE_GOOD_HOPE: [number, number]     = [-34.8, 20.0];   // Cape of Good Hope
const WP_MOZAMBIQUE_CH: [number, number]      = [-20.0, 42.0];   // Mozambique Channel
const WP_BAY_OF_BENGAL_SOUTH: [number, number]= [10.0, 83.5];    // South Bay of Bengal
const WP_BAY_OF_BENGAL_NORTH: [number, number]= [19.0, 87.0];    // North Bay of Bengal
const SAGAR_LL: [number, number]               = [21.2500, 88.1500];

// ─── Berth status colour code ─────────────────────────────────────────────────
//
// Discharge ports are coloured by what the selected vessel can actually do
// there, which is the question the map exists to answer. The three outcomes are
// commercially distinct and are kept distinct: berthing on arrival and berthing
// only on a high-water window are different fixtures at different prices.
//
// Loading ports used to be red, which collided with "cannot berth". They are
// now carried by shape instead: a neutral square, no status colour. Status
// colours mean status and nothing else.
const BERTH_STATUS: Record<BerthOutcome, { colour: string; label: string; short: string }> = {
  ACCEPT_ALL_TIDE:       { colour: '#3ddc84', label: 'Berths on arrival',   short: 'all tide' },
  ACCEPT_HIGH_TIDE_ONLY: { colour: '#f0a500', label: 'High water only',     short: 'on tide' },
  REJECT:                { colour: '#e05c5c', label: 'Cannot berth',        short: 'blocked' },
};

const LOAD_PORT_COLOUR = '#5a93e8';
const UNKNOWN_COLOUR   = '#4a5568';

const VESSEL_CODES = ['HANDYSIZE', 'SUPRAMAX', 'PANAMAX', 'CAPESIZE'] as const;

/** Typical full parcel per class, used to judge feasibility on the map. */
const TYPICAL_PARCEL: Record<string, number> = {
  HANDYSIZE: 35_000, SUPRAMAX: 55_000, PANAMAX: 72_000, CAPESIZE: 160_000,
};

// Offshore waypoints for Indian Ports to keep coastal sea lanes in ocean water
const PORT_OFFSHORE: Record<string, [number, number]> = {
  'HALDIA':          [21.7, 88.1],
  'SAGAR_SANDHEADS': [21.25, 88.15],
  'DHAMRA':          [20.6, 87.3],
  'PPA':             [20.0, 87.0],
  'GOPALPUR':        [19.0, 85.3],
  'VIZAG':           [17.5, 83.6],
  'GANGAVARAM':      [17.5, 83.6],
};

const ROUTE_DISTANCES: Record<string, number> = {
  'NEWCASTLE_HALDIA': 5800, 'NEWCASTLE_VIZAG': 5600, 'NEWCASTLE_PPA': 5700,
  'HAY_POINT_DHAMRA': 5400, 'TABONEO_VIZAG': 2800, 'MAPUTO_PPA': 4200,
  'BALTIMORE_GANGAVARAM': 9800, 'NORFOLK_GANGAVARAM': 9600,
  'BEIRA_NACALA_VIZAG': 4400, 'BANJARMASIN_VIZAG': 2900,
};

type Region = 'AFRICA' | 'AUSTRALIA' | 'BAY_OF_BENGAL' | 'INDONESIA' | 'USA';

function getPortRegion(code: string): Region {
  if (['PPA', 'VIZAG', 'GANGAVARAM', 'GOPALPUR', 'DHAMRA', 'SAGAR_SANDHEADS', 'HALDIA'].includes(code)) {
    return 'BAY_OF_BENGAL';
  }
  if (['TABONEO', 'BANJARMASIN'].includes(code)) {
    return 'INDONESIA';
  }
  if (['HAY_POINT', 'NEWCASTLE'].includes(code)) {
    return 'AUSTRALIA';
  }
  if (['MAPUTO', 'BEIRA_NACALA'].includes(code)) {
    return 'AFRICA';
  }
  return 'USA';
}

/**
 * Catmull-Rom Spline Curve Generator for smooth, silky nautical polyline paths.
 */
function smoothWaypoints(pts: [number, number][], samplesPerSeg: number = 8): [number, number][] {
  if (pts.length < 3) return pts;

  const smoothed: [number, number][] = [];
  const p = [pts[0], ...pts, pts[pts.length - 1]];

  for (let i = 0; i < p.length - 3; i++) {
    const p0 = p[i];
    const p1 = p[i + 1];
    const p2 = p[i + 2];
    const p3 = p[i + 3];

    for (let tStep = 0; tStep < samplesPerSeg; tStep++) {
      const t = tStep / samplesPerSeg;
      const t2 = t * t;
      const t3 = t2 * t;

      const lat = 0.5 * (
        (2 * p1[0]) +
        (-p0[0] + p2[0]) * t +
        (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
        (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
      );

      const lng = 0.5 * (
        (2 * p1[1]) +
        (-p0[1] + p2[1]) * t +
        (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
        (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
      );

      smoothed.push([lat, lng]);
    }
  }

  smoothed.push(pts[pts.length - 1]);
  return smoothed;
}

function computeSeaRoute(
  originCode: string,
  destCode: string,
  originLL: [number, number],
  destLL: [number, number]
): [number, number][] {
  const regA = getPortRegion(originCode);
  const regB = getPortRegion(destCode);

  const offA = PORT_OFFSHORE[originCode] || originLL;
  const offB = PORT_OFFSHORE[destCode] || destLL;

  // 1. Same region (e.g. Indian coastal trade or Indonesia internal)
  if (regA === regB) {
    if (regA === 'BAY_OF_BENGAL') {
      return [originLL, offA, WP_BAY_OF_BENGAL_NORTH, offB, destLL];
    }
    return [originLL, destLL];
  }

  // Canonical ordering: sort alphabetically by region name
  const isReverse = regA > regB;
  const r1 = isReverse ? regB : regA;
  const r2 = isReverse ? regA : regB;
  const p1_LL = isReverse ? destLL : originLL;
  const p2_LL = isReverse ? originLL : destLL;
  const p1_code = isReverse ? destCode : originCode;
  const p2_code = isReverse ? originCode : destCode;
  const p1_off = PORT_OFFSHORE[p1_code] || p1_LL;
  const p2_off = PORT_OFFSHORE[p2_code] || p2_LL;

  let route: [number, number][] = [];

  // Pair: AFRICA <-> BAY_OF_BENGAL
  if (r1 === 'AFRICA' && r2 === 'BAY_OF_BENGAL') {
    route = [
      p1_LL,
      WP_MOZAMBIQUE_CH,
      [-12.0, 48.0],
      [-5.0, 60.0],
      WP_SRI_LANKA,
      WP_BAY_OF_BENGAL_SOUTH,
      p2_off,
      p2_LL
    ];
  }
  // Pair: AUSTRALIA <-> BAY_OF_BENGAL (Sails around North Australia via Coral Sea & Torres Strait!)
  else if (r1 === 'AUSTRALIA' && r2 === 'BAY_OF_BENGAL') {
    route = [
      p1_LL,
      [-28.0, 156.0],            // Coral Sea (Offshore East Australia)
      [-18.0, 155.0],            // Coral Sea
      [-13.0, 146.0],            // Torres Strait approach
      WP_TORRES_STRAIT,          // Torres Strait (North of Australia)
      WP_ARAFURA_SEA,            // Arafura Sea
      WP_TIMOR_SEA,              // Timor Sea
      WP_LOMBOK,                 // Lombok Strait
      WP_JAVA_SEA,               // Java Sea
      WP_MALACCA_SOUTH,          // Singapore
      WP_MALACCA_NORTH,          // Malacca North
      WP_BAY_OF_BENGAL_SOUTH,    // South Bay of Bengal
      p2_off,
      p2_LL
    ];
  }
  // Pair: AUSTRALIA <-> INDONESIA (Sails around Torres Strait & Timor Sea into Java Sea!)
  else if (r1 === 'AUSTRALIA' && r2 === 'INDONESIA') {
    route = [
      p1_LL,
      [-28.0, 156.0],
      [-18.0, 155.0],
      WP_TORRES_STRAIT,
      WP_ARAFURA_SEA,
      WP_TIMOR_SEA,
      WP_LOMBOK,
      [-5.0, 114.5],
      p2_LL
    ];
  }
  // Pair: AFRICA <-> AUSTRALIA (Sails around South Australia via Bass Strait & Cape Leeuwin!)
  else if (r1 === 'AFRICA' && r2 === 'AUSTRALIA') {
    route = [
      p1_LL,
      WP_MOZAMBIQUE_CH,
      [-28.0, 50.0],
      [-32.0, 80.0],
      WP_CAPE_LEEUWIN,
      WP_GREAT_AUST_BIGHT,
      WP_BASS_STRAIT,
      p2_LL
    ];
  }
  // Pair: AUSTRALIA <-> USA (Sails around South Australia & Cape of Good Hope!)
  else if (r1 === 'AUSTRALIA' && r2 === 'USA') {
    route = [
      p1_LL,
      WP_BASS_STRAIT,
      WP_GREAT_AUST_BIGHT,
      WP_CAPE_LEEUWIN,
      [-32.0, 90.0],
      [-30.0, 60.0],
      WP_CAPE_GOOD_HOPE,
      [-10.0, -25.0],
      [15.0, -45.0],
      [35.0, -72.0],
      p2_LL
    ];
  }
  // Pair: BAY_OF_BENGAL <-> INDONESIA
  else if (r1 === 'BAY_OF_BENGAL' && r2 === 'INDONESIA') {
    route = [
      p1_LL,
      p1_off,
      WP_BAY_OF_BENGAL_SOUTH,
      WP_MALACCA_NORTH,
      WP_MALACCA_SOUTH,
      WP_JAVA_SEA,
      p2_LL
    ];
  }
  // Pair: BAY_OF_BENGAL <-> USA
  else if (r1 === 'BAY_OF_BENGAL' && r2 === 'USA') {
    route = [
      p1_LL,
      p1_off,
      WP_BAY_OF_BENGAL_SOUTH,
      WP_SRI_LANKA,
      [-10.0, 60.0],
      [-25.0, 45.0],
      WP_CAPE_GOOD_HOPE,
      [-10.0, -25.0],
      [15.0, -45.0],
      [35.0, -72.0],
      p2_LL
    ];
  }
  // Pair: AFRICA <-> INDONESIA
  else if (r1 === 'AFRICA' && r2 === 'INDONESIA') {
    route = [
      p1_LL,
      WP_MOZAMBIQUE_CH,
      [-25.0, 60.0],
      [-15.0, 90.0],
      WP_SUNDA,
      p2_LL
    ];
  }
  // Pair: USA <-> INDONESIA / AFRICA
  else if (r2 === 'USA') {
    route = [
      p2_LL,
      [35.0, -72.0],
      [15.0, -45.0],
      [-10.0, -25.0],
      WP_CAPE_GOOD_HOPE,
      [-25.0, 60.0],
      [-15.0, 90.0],
      p1_LL
    ];
  }
  else {
    route = [originLL, destLL];
  }

  const rawRoute = isReverse ? [...route].reverse() : route;
  return smoothWaypoints(rawRoute, 10);
}

// ─── Polyline Waypoint Interpolator for Ship Animation ────────────────────────

function interpolateWaypoints(pts: [number, number][], progress: number): [number, number] {
  if (pts.length === 0) return [0, 0];
  if (pts.length === 1 || progress <= 0) return pts[0];
  if (progress >= 1) return pts[pts.length - 1];

  let totalDist = 0;
  const dists: number[] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const d = Math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1]);
    dists.push(d);
    totalDist += d;
  }

  const targetDist = progress * totalDist;
  let accumulated = 0;

  for (let i = 0; i < dists.length; i++) {
    if (accumulated + dists[i] >= targetDist) {
      const segProgress = (targetDist - accumulated) / dists[i];
      const lat = pts[i][0] + (pts[i+1][0] - pts[i][0]) * segProgress;
      const lng = pts[i][1] + (pts[i+1][1] - pts[i][1]) * segProgress;
      return [lat, lng];
    }
    accumulated += dists[i];
  }

  return pts[pts.length - 1];
}

function calculateBearing(p1: [number, number], p2: [number, number]): number {
  const dLng = p2[1] - p1[1];
  const dLat = p2[0] - p1[0];
  const angle = (Math.atan2(dLng, dLat) * 180) / Math.PI;
  return (angle + 360) % 360;
}

// ─── Icon Factories ──────────────────────────────────────────────────────────

function makeStatusIcon(colour: string, size = 16) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size+8}" height="${size+8}" viewBox="0 0 ${size+8} ${size+8}">
      <circle cx="${(size+8)/2}" cy="${(size+8)/2}" r="${size/2+2}" fill="${colour}33"/>
      <circle cx="${(size+8)/2}" cy="${(size+8)/2}" r="${size/2}" fill="${colour}" stroke="#0d1117" stroke-width="2"/>
    </svg>`;
  return L.divIcon({
    className: '', html: svg,
    iconSize: [size+8, size+8], iconAnchor: [(size+8)/2, (size+8)/2], popupAnchor: [0, -(size/2+4)],
  });
}

/** Loading ports carry identity by shape, so the traffic-light hues stay free. */
function makeLoadPortIcon(size = 13) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size+6}" height="${size+6}" viewBox="0 0 ${size+6} ${size+6}">
      <rect x="3" y="3" width="${size}" height="${size}" rx="2"
            fill="${LOAD_PORT_COLOUR}44" stroke="${LOAD_PORT_COLOUR}" stroke-width="1.8"/>
    </svg>`;
  return L.divIcon({
    className: '', html: svg,
    iconSize: [size+6, size+6], iconAnchor: [(size+6)/2, (size+6)/2], popupAnchor: [0, -(size/2+4)],
  });
}


function makeAnchorageIcon(size = 16) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size+12}" height="${size+12}" viewBox="0 0 ${size+12} ${size+12}">
    <circle cx="${(size+12)/2}" cy="${(size+12)/2}" r="${size/2+3}" fill="none" stroke="#3b82f6" stroke-width="2" stroke-dasharray="4 3"/>
    <circle cx="${(size+12)/2}" cy="${(size+12)/2}" r="${size/2-1}" fill="#3b82f6aa" stroke="#3b82f6" stroke-width="1.5"/>
  </svg>`;
  return L.divIcon({ className: '', html: svg, iconSize: [size+12, size+12], iconAnchor: [(size+12)/2, (size+12)/2], popupAnchor: [0, -(size/2+6)] });
}


function makeLighterageIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
    <circle cx="14" cy="14" r="12" fill="#f9731644" stroke="#f97316" stroke-width="2.5"/>
    <text x="14" y="19" text-anchor="middle" font-size="13" fill="#f97316" font-weight="bold">⚓</text>
  </svg>`;
  return L.divIcon({ className: '', html: svg, iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -16] });
}

function makeWarningIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
    <polygon points="12,2 22,20 2,20" fill="#ef444433" stroke="#ef4444" stroke-width="2" stroke-linejoin="round"/>
    <text x="12" y="17" text-anchor="middle" font-size="10" fill="#ef4444" font-weight="bold">!</text>
  </svg>`;
  return L.divIcon({ className: '', html: svg, iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -14] });
}

/**
 * Top-down Vector SVG Cargo Vessel with dynamic 360° heading rotation & engine glow.
 */
function makeVesselIcon(rotationDeg: number = 0) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
    <defs>
      <filter id="vesselGlow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2.5" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
    <!-- Engine Wake Pulse -->
    <ellipse cx="20" cy="34" rx="5" ry="3" fill="#38bdf8" opacity="0.5" />
    <!-- Ship Hull Vector -->
    <path d="M 20 4 C 26 12, 27 20, 25 32 C 23 35, 17 35, 15 32 C 13 20, 14 12, 20 4 Z"
          fill="#0f172a" stroke="#38bdf8" stroke-width="2" filter="url(#vesselGlow)"/>
    <!-- Cargo Container Stacks -->
    <rect x="16" y="12" width="8" height="10" fill="#0284c7" rx="1"/>
    <line x1="16" y1="17" x2="24" y2="17" stroke="#38bdf8" stroke-width="1"/>
    <!-- Navigation Bridge -->
    <rect x="17" y="24" width="6" height="5" fill="#f8fafc" rx="1"/>
  </svg>`;

  return L.divIcon({
    className: 'vessel-animated-icon',
    html: `<div style="transform: rotate(${rotationDeg}deg); transform-origin: center center; width: 40px; height: 40px; transition: transform 0.15s linear;">${svg}</div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function MapPage() {
  const mapRef            = useRef<L.Map | null>(null);
  const mapDivRef         = useRef<HTMLDivElement>(null);
  const portMarkersRef    = useRef<Map<string, L.Marker>>(new Map());
  const sealaneLayersRef  = useRef<L.Layer[]>([]);
  const animFrameRef      = useRef<number | null>(null);

  const [ports, setPorts]             = useState<PortResponse[]>([]);
  const [loading, setLoading]         = useState(true);
  const [originCode, setOriginCode]   = useState<string>('NEWCASTLE');
  const [destCode, setDestCode]       = useState<string>('HALDIA');
  const [vesselCode, setVesselCode]   = useState<string>('PANAMAX');
  // Berth outcome per discharge port for the selected class, from the resolver.
  const [berthStatus, setBerthStatus] = useState<Record<string, MatchResponse['recommendations'][number]>>({});
  const [evalResult, setEvalResult]   = useState<EvaluationResult | null>(null);

  // Fetch ports
  useEffect(() => {
    fetchPorts()
      .then(setPorts)
      .catch(() => setPorts([]))
      .finally(() => setLoading(false));
  }, []);

  // Initialize Leaflet Map with Esri World Dark Gray tiles (NO API Key required!)
  useEffect(() => {
    if (mapRef.current || !mapDivRef.current) return;

    const map = L.map(mapDivRef.current, {
      center: [15, 88],
      zoom: 4,
      zoomControl: false,
      attributionControl: false,
    });

    // Dark sleek maritime map layer (100% Free, NO API Key needed)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 16,
      attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
    }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.attribution({ position: 'bottomleft', prefix: '© Esri / OpenStreetMap' }).addTo(map);

    setTimeout(() => {
      map.invalidateSize();
    }, 150);

    mapRef.current = map;
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Ask the berth resolver what this class can do at each Indian port. One call
  // per port, in parallel. Doing the draft arithmetic here instead would be a
  // second implementation of a rule that already exists server-side.
  useEffect(() => {
    const hubs = ports.filter(p => p.is_indian_hub && !p.is_anchorage);
    if (hubs.length === 0) return;

    let cancelled = false;
    const tonnes = TYPICAL_PARCEL[vesselCode] ?? 55_000;

    Promise.all(hubs.map(port =>
      apiPost<MatchResponse>('/api/match', {
        discharge_port_id: port.port_id,
        commodity: 'thermal_coal',
        cargo_tonnes: tonnes,
      })
        .then(res => {
          const verdict = res.recommendations.find(
            r => r.vessel_class.toUpperCase() === vesselCode,
          );
          return verdict ? [port.code, verdict] as const : null;
        })
        .catch(() => null),
    )).then(entries => {
      if (cancelled) return;
      setBerthStatus(Object.fromEntries(entries.filter(Boolean) as [string, MatchResponse['recommendations'][number]][]));
    });

    return () => { cancelled = true; };
  }, [ports, vesselCode]);

  // Render Port Markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || ports.length === 0) return;

    portMarkersRef.current.forEach(m => m.remove());
    portMarkersRef.current.clear();

    ports.forEach(port => {
      const verdict = berthStatus[port.code];
      const status = verdict ? BERTH_STATUS[verdict.outcome] : null;

      let icon: L.DivIcon;
      let color: string;
      let roleLabel: string;

      if (port.is_anchorage) {
        icon = makeAnchorageIcon();
        color = LOAD_PORT_COLOUR;
        roleLabel = 'Anchorage';
      } else if (port.is_indian_hub) {
        // Coloured by what this class can do here, grey until the resolver answers.
        color = status ? status.colour : UNKNOWN_COLOUR;
        icon = makeStatusIcon(color);
        roleLabel = status ? status.label : 'Checking berths';
      } else {
        icon = makeLoadPortIcon();
        color = LOAD_PORT_COLOUR;
        roleLabel = 'Loading Port';
      }

      const marker = L.marker([port.latitude, port.longitude], { icon });
      marker.bindPopup(`
        <div class="map-popup">
          <div class="map-popup__header">
            <span class="map-popup__dot" style="background:${color};box-shadow:0 0 5px ${color}"></span>
            <strong>${port.name}</strong>
            <span class="map-popup__badge" style="color:${color};border-color:${color}44;background:${color}18">${roleLabel}</span>
          </div>
          <div class="map-popup__grid">
            <div class="map-popup__item"><span>Code</span><b>${port.code}</b></div>
            <div class="map-popup__item"><span>Country</span><b>${port.country}</b></div>
            <div class="map-popup__item"><span>Max Draft</span><b>${port.max_draft}m</b></div>
            <div class="map-popup__item"><span>Max LOA</span><b>${port.max_loa > 999 ? '∞' : port.max_loa + 'm'}</b></div>
            ${verdict ? `
            <div class="map-popup__item"><span>Berth</span><b>${verdict.berth?.berth_id ?? '—'}</b></div>
            <div class="map-popup__item"><span>Turnaround</span><b>${verdict.turnaround_days?.toFixed(1) ?? '—'} d</b></div>` : ''}
          </div>
          ${verdict ? `<div class="map-popup__reason">${verdict.reason}</div>` : ''}
          ${verdict?.lighterage ? `<div class="map-popup__warn">${verdict.lighterage.narrative}</div>` : ''}
          ${port.is_anchorage ? '<div class="map-popup__warn">⚓ Lighterage / Transshipment Anchorage</div>' : ''}
        </div>`, { maxWidth: 280 });

      marker.on('click', () => {
        setOriginCode(prev => {
          if (!prev || prev === port.code) return port.code;
          setDestCode(port.code);
          return prev;
        });
      });

      marker.addTo(map);
      portMarkersRef.current.set(port.code, marker);
    });
  }, [ports, berthStatus]);

  // Draw Sea Lane + Animated Vector Vessel
  const drawSeaLane = useCallback(async () => {
    const map = mapRef.current;
    if (!map || !originCode || !destCode || originCode === destCode) return;

    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    sealaneLayersRef.current.forEach(l => map.removeLayer(l));
    sealaneLayersRef.current = [];

    let result: EvaluationResult | null = null;
    try {
      result = await evaluate({
        cargo_tonnage: 75000,
        origin_code: originCode,
        destination_code: destCode,
        vessel_code: vesselCode,
        num_voyages: horizonToVoyages(3),
        cvc_discount_pct: 5.0,
      });
      setEvalResult(result);
    } catch {
      setEvalResult(null);
    }

    const originPort = ports.find(p => p.code === originCode);
    const destPort   = ports.find(p => p.code === destCode);
    if (!originPort || !destPort) return;

    const originLL: [number, number] = [originPort.latitude, originPort.longitude];
    const destLL:   [number, number] = [destPort.latitude,   destPort.longitude];

    const routeKey = `${originCode}_${destCode}`;
    const distNM = ROUTE_DISTANCES[routeKey] ?? 4500;
    const waypoints = computeSeaRoute(originCode, destCode, originLL, destLL);

    const lighterageRequired = result?.lighterage_plan?.is_required ?? false;

    if (lighterageRequired) {
      // Leg A: Origin → Sagar/Sandheads (glowing cyan spline)
      const legA = L.polyline(
        [...waypoints.slice(0, -1), SAGAR_LL],
        { color: '#38bdf8', weight: 4, opacity: 0.95 }
      );

      // Leg B: Sagar/Sandheads → Destination (dashed orange)
      const legB = L.polyline(
        [SAGAR_LL, destLL],
        { color: '#f97316', weight: 4, dashArray: '8 5', opacity: 0.95 }
      );

      const lightMarker = L.marker(SAGAR_LL, { icon: makeLighterageIcon() });
      const lp = result!.lighterage_plan;
      lightMarker.bindPopup(
        `<div class="map-popup">
          <b style="color:#f97316">[LIGHTERAGE_REQUIRED]</b><br/>
          Vessel draft exceeds port max.<br/>
          Transship <b>${lp.lightered_tonnage.toLocaleString(undefined,{maximumFractionDigits:0})}T</b> at Sagar/Sandheads.<br/>
          Time penalty: <b>${lp.time_penalty_days} days</b>
        </div>`, { maxWidth: 240 }
      );

      const warnMarker = L.marker(destLL, { icon: makeWarningIcon() });
      warnMarker.bindPopup('<b style="color:#ef4444">[LIGHTERAGE_REQUIRED]</b><br/>Shallow port — lighterage required.');

      [legA, legB, lightMarker, warnMarker].forEach(l => {
        l.addTo(map);
        sealaneLayersRef.current.push(l);
      });

    } else {
      // Glowing outer shadow line
      const shadowLane = L.polyline(waypoints, { color: '#0284c7', weight: 8, opacity: 0.3 });

      // Direct ocean sea lane (glowing cyan spline)
      const lane = L.polyline(waypoints, { color: '#38bdf8', weight: 4, opacity: 0.95 });

      const midIdx = Math.floor(waypoints.length / 2);
      const midLL = waypoints[midIdx] || waypoints[0];

      const distLabel = L.marker(midLL, {
        icon: L.divIcon({
          className: '',
          html: `<div class="map-dist-label">${distNM} NM</div>`,
          iconSize: [80, 22],
          iconAnchor: [40, 11],
        }),
      });

      lane.on('click', () => {
        const avgP50 = result
          ? result.p50_rates.reduce((a, b) => a + b, 0) / result.p50_rates.length
          : null;
        L.popup()
          .setLatLng(midLL)
          .setContent(`
            <div class="map-popup">
              <b>${originCode} → ${destCode}</b><br/>
              Distance: <b>${distNM} NM</b><br/>
              ${avgP50 ? `Forecast Rate: <b>$${result!.p10_rates[0].toFixed(2)}–$${result!.p90_rates[0].toFixed(2)}/T</b>` : ''}
            </div>`)
          .openOn(map);
      });

      [shadowLane, lane, distLabel].forEach(l => {
        l.addTo(map);
        sealaneLayersRef.current.push(l);
      });
    }

    // ── Animated Vector Cargo Vessel Marker along smooth waypoints with 360° heading rotation ──
    const initialBearing = calculateBearing(waypoints[0], waypoints[1] || waypoints[0]);
    const vesselMarker = L.marker(waypoints[0], { icon: makeVesselIcon(initialBearing), zIndexOffset: 1000 });
    vesselMarker.addTo(map);
    sealaneLayersRef.current.push(vesselMarker);

    const animDuration = 45000; // 45 seconds for a realistic, majestic nautical voyage speed
    let startTime: number | null = null;
    let lastBearing = -1;

    function stepAnimation(timestamp: number) {
      if (!startTime) startTime = timestamp;
      const elapsed = (timestamp - startTime) % animDuration;
      const progress = elapsed / animDuration;

      const pos = interpolateWaypoints(waypoints, progress);
      const nextPos = interpolateWaypoints(waypoints, Math.min(progress + 0.002, 1.0));
      const bearing = Math.round(calculateBearing(pos, nextPos));

      vesselMarker.setLatLng(pos);
      if (Math.abs(bearing - lastBearing) >= 2) {
        vesselMarker.setIcon(makeVesselIcon(bearing));
        lastBearing = bearing;
      }

      animFrameRef.current = requestAnimationFrame(stepAnimation);
    }

    animFrameRef.current = requestAnimationFrame(stepAnimation);

    map.fitBounds(L.latLngBounds([originLL, destLL, ...waypoints]).pad(0.25));
  }, [originCode, destCode, vesselCode, ports]);

  useEffect(() => {
    drawSeaLane();
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [drawSeaLane]);

  const resetMap = () => {
    const map = mapRef.current;
    if (!map) return;
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    sealaneLayersRef.current.forEach(l => map.removeLayer(l));
    sealaneLayersRef.current = [];
    setEvalResult(null);
    map.setView([15, 88], 4);
    setTimeout(() => map.invalidateSize(), 100);
  };

  const originPorts = ports.filter(p => !p.is_anchorage);
  const destPorts   = ports.filter(p => !p.is_anchorage && p.code !== originCode);

  return (
    <div className="map-page">
      {/* Controls bar */}
      <div className="map-controls">
        <div className="map-controls__left">
          <span className="map-controls__label">Origin</span>
          <select
            className="map-select"
            value={originCode}
            onChange={e => setOriginCode(e.target.value)}
            disabled={loading}
          >
            {originPorts.map(p => (
              <option key={p.code} value={p.code}>{p.name} ({p.country})</option>
            ))}
          </select>

          <span className="map-controls__label" style={{ marginLeft: '0.75rem' }}>Destination</span>
          <select
            className="map-select"
            value={destCode}
            onChange={e => setDestCode(e.target.value)}
            disabled={loading}
          >
            {destPorts.map(p => (
              <option key={p.code} value={p.code}>{p.name} ({p.country})</option>
            ))}
          </select>
          <span className="map-controls__label" style={{ marginLeft: '0.75rem' }}>Vessel</span>
          <div className="map-vessel-codes">
            {VESSEL_CODES.map(code => (
              <button
                key={code}
                className={`map-vessel-code ${vesselCode === code ? 'map-vessel-code--active' : ''}`}
                onClick={() => setVesselCode(code)}
                title={`Colour the discharge ports by what a ${code[0] + code.slice(1).toLowerCase()} can do at a ${TYPICAL_PARCEL[code].toLocaleString('en-US')} T parcel`}
              >
                {code[0] + code.slice(1).toLowerCase()}
              </button>
            ))}
          </div>
        </div>
        <div className="map-controls__right">
          <button className="btn btn-ghost btn--sm" onClick={resetMap}>
            🔄 Reset Map
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="map-legend">
        <span className="map-legend__title">
          Can a {vesselCode[0] + vesselCode.slice(1).toLowerCase()} berth here?
        </span>
        {(Object.keys(BERTH_STATUS) as BerthOutcome[]).map(outcome => {
          const n = Object.values(berthStatus).filter(v => v.outcome === outcome).length;
          const s = BERTH_STATUS[outcome];
          return (
            <div key={outcome} className="map-legend__item">
              <span className="map-legend__dot" style={{ background: s.colour, boxShadow: `0 0 5px ${s.colour}` }} />
              <span>{s.label} <b className="mono">{n}</b></span>
            </div>
          );
        })}
        <div className="map-legend__item">
          <span className="map-legend__square" style={{ borderColor: LOAD_PORT_COLOUR, background: `${LOAD_PORT_COLOUR}44` }} />
          <span>Loading port</span>
        </div>
        <div className="map-legend__item">
          <span style={{ display: 'inline-block', width: 14, height: 14, borderRadius: '50%', border: `2px dashed ${LOAD_PORT_COLOUR}`, marginRight: 6 }} />
          <span>Anchorage</span>
        </div>
        <div className="map-legend__item">
          <span style={{ display: 'inline-block', width: 18, height: 3, background: '#38bdf8', marginRight: 6, borderRadius: 2 }} />
          <span>Sea lane</span>
        </div>
        <div className="map-legend__item">
          <span style={{ display: 'inline-block', width: 18, height: 3, background: '#f97316', marginRight: 6, borderRadius: 2 }} />
          <span>Lighterage leg</span>
        </div>
      </div>

      {/* Evaluation headline strip */}
      {evalResult && (
        <div className={`map-eval-strip ${evalResult.is_cvc_favorable ? 'map-eval-strip--green' : 'map-eval-strip--amber'}`}>
          <span>{evalResult.headline_summary}</span>
          {evalResult.lighterage_plan.is_required && (
            <span className="map-lighterage-badge">[LIGHTERAGE_REQUIRED]</span>
          )}
        </div>
      )}

      {/* Map container */}
      <div className="map-container" ref={mapDivRef} id="leaflet-map" />
    </div>
  );
}
