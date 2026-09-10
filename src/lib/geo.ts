// ─── Distance ─────────────────────────────────────────────────────────────────

/** Great-circle distance in nautical miles. */
export function haversineNm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const R = 3440.065; // Earth radius in nautical miles
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLng = toRad(bLng - aLng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/**
 * A great circle runs through land. Bulk routes detour round capes and through
 * straits, so sailed distance runs above the direct line by roughly this much.
 * Same constant the backend uses, for the same reason.
 */
export const ROUTING_FACTOR = 1.18;

export function sailedNm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  return haversineNm(aLat, aLng, bLat, bLng) * ROUTING_FACTOR;
}
