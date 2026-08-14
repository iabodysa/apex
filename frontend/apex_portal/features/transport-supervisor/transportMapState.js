import { computed, ref } from "vue";
import { errorStatus, safeErrorMessage } from "../../core/errorMessage.js";

export const SAUDI_BOUNDS = Object.freeze({ minLat: 16, maxLat: 33, minLng: 34, maxLng: 56 });
const POSITION_STALE_SECONDS = 120;

export function coordinatePair(point) {
  const values = Array.isArray(point)
    ? [point[0], point[1]]
    : [point?.lat ?? point?.latitude, point?.lng ?? point?.longitude];
  if (values.some((value) => value === null || value === undefined || value === "")) return null;
  const pair = values.map(Number);
  if (!pair.every(Number.isFinite)) return null;
  const [lat, lng] = pair;
  if (lat < SAUDI_BOUNDS.minLat || lat > SAUDI_BOUNDS.maxLat) return null;
  if (lng < SAUDI_BOUNDS.minLng || lng > SAUDI_BOUNDS.maxLng) return null;
  return pair;
}

export function normalizePosition(row) {
  const pair = coordinatePair(row);
  const coordinatesAvailable = Boolean(row?.has_position && pair);
  const updatedAt = String(row?.updated_at || "").trim();
  const ageSeconds = row?.age_seconds === null || row?.age_seconds === undefined || row?.age_seconds === ""
    ? null
    : Number(row.age_seconds);
  const freshnessKnown = coordinatesAvailable && Boolean(updatedAt) && Number.isFinite(ageSeconds);
  const stale = freshnessKnown && (row?.stale === true || ageSeconds > POSITION_STALE_SECONDS);
  const positionState = !coordinatesAvailable
    ? "offline"
    : !freshnessKnown
      ? "unknown"
      : stale
        ? "stale"
        : "live";
  const positionAvailable = positionState === "live" || positionState === "stale";
  return {
    ...row,
    lat: coordinatesAvailable ? pair[0] : null,
    lng: coordinatesAvailable ? pair[1] : null,
    has_position: positionAvailable,
    position_available: positionAvailable,
    position_state: positionState,
    stale,
  };
}

export function positionStateLabel(value) {
  return {
    live: "مباشر",
    stale: "آخر موقع متأخر",
    unknown: "حداثة الموقع غير معروفة",
    offline: "الموقع غير متاح",
  }[value] || "حالة الموقع غير معروفة";
}

function uniqueValues(rows, key) {
  return [...new Set(rows.map((row) => row[key]).filter(Boolean))];
}

export function selectedMapRows(rows, selectedTrip) {
  return rows.filter((row) => row.dispatch_trip === selectedTrip);
}

export function createTransportMapState() {
  let loadGeneration = 0;
  const phase = ref("loading");
  const error = ref("");
  const positions = ref([]);
  const project = ref("");
  const status = ref("");
  const projects = computed(() => {
    const options = new Map();
    positions.value.forEach((row) => {
      if (row.project && !options.has(row.project)) {
        options.set(row.project, {
          value: row.project,
          label: row.project_label || row.project,
        });
      }
    });
    return [...options.values()];
  });
  const statuses = computed(() => uniqueValues(positions.value, "status"));
  const visible = computed(() => positions.value.filter((item) =>
    (!project.value || item.project === project.value)
    && (!status.value || item.status === status.value),
  ));

  function fail(reason) {
    phase.value = errorStatus(reason) === 403 ? "denied" : "error";
    error.value = safeErrorMessage(reason, "تعذّر تحميل حركة المركبات.");
  }

  async function load(readPositions) {
    const generation = ++loadGeneration;
    phase.value = "loading";
    error.value = "";
    try {
      const result = await readPositions();
      if (generation !== loadGeneration) return false;
      positions.value = Array.isArray(result?.positions)
        ? result.positions.map(normalizePosition)
        : [];
      phase.value = positions.value.length ? "ready" : "empty";
      return true;
    } catch (reason) {
      if (generation !== loadGeneration) return false;
      fail(reason);
      return true;
    }
  }

  function cancel() {
    loadGeneration += 1;
  }

  return Object.freeze({
    phase,
    error,
    positions,
    project,
    status,
    projects,
    statuses,
    visible,
    fail,
    load,
    cancel,
  });
}
