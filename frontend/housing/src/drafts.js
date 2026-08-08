// Copyright (c) 2026, afmcoltd
import { makeCache } from "@shared/makeCache.js";

const roundCache = makeCache("apex_safety_draft_");
const countCache = makeCache("apex_housing_count_draft_");

function read(cache, key) {
  const saved = cache.cacheGet(key);
  if (!saved || !saved.data || typeof saved.data !== "object") return null;
  return saved.data;
}

export function readRoundDraft(buildingName, date) {
  if (!buildingName) return null;
  return read(roundCache, buildingName + "|" + date);
}

export function writeRoundDraft(buildingName, date, ratings) {
  if (!buildingName) return;
  roundCache.cacheSet(buildingName + "|" + date, ratings);
}

export function dropRoundDraft(buildingName, date) {
  if (!buildingName) return;
  roundCache.cacheSet(buildingName + "|" + date, {});
}

export function readCountDraft(buildingName) {
  if (!buildingName) return null;
  return read(countCache, buildingName);
}

export function writeCountDraft(buildingName, staged) {
  if (!buildingName) return;
  countCache.cacheSet(buildingName, staged);
}

export function dropCountDraft(buildingName) {
  if (!buildingName) return;
  countCache.cacheSet(buildingName, {});
}
