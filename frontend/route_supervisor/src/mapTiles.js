// Copyright (c) 2026, afmcoltd

const DEFAULT_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const DEFAULT_TILE_ATTRIBUTION = "© OpenStreetMap";

const config = (typeof window !== "undefined" && window.apex_map_tiles) || {};

export const TILE_URL = config.url || DEFAULT_TILE_URL;
export const TILE_ATTRIBUTION = config.attribution || DEFAULT_TILE_ATTRIBUTION;

export function leaflet() {
  return typeof window !== "undefined" ? window.L : undefined;
}
