import { computed, ref } from "vue";

export const SAUDI_BOUNDS = Object.freeze({ minLat: 16, maxLat: 33, minLng: 34, maxLng: 56 });

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
  const positionAvailable = Boolean(row?.has_position && pair);
  return {
    ...row,
    lat: positionAvailable ? pair[0] : null,
    lng: positionAvailable ? pair[1] : null,
    has_position: positionAvailable,
    position_available: positionAvailable,
    stale: positionAvailable ? Boolean(row?.stale) : false,
  };
}

function uniqueValues(rows, key) {
  return [...new Set(rows.map((row) => row[key]).filter(Boolean))];
}

export function selectedMapRows(rows, selectedTrip) {
  return rows.filter((row) => row.dispatch_trip === selectedTrip);
}

export function createTransportMapState() {
  const phase = ref("loading");
  const error = ref("");
  const positions = ref([]);
  const project = ref("");
  const status = ref("");
  const projects = computed(() => uniqueValues(positions.value, "project"));
  const statuses = computed(() => uniqueValues(positions.value, "status"));
  const visible = computed(() => positions.value.filter((item) =>
    (!project.value || item.project === project.value)
    && (!status.value || item.status === status.value),
  ));

  function fail(reason) {
    phase.value = reason?.status === 403 ? "denied" : "error";
    error.value = reason?.message || "تعذّر تحميل حركة المركبات.";
  }

  async function load(readPositions) {
    phase.value = "loading";
    error.value = "";
    try {
      const result = await readPositions();
      positions.value = Array.isArray(result?.positions)
        ? result.positions.map(normalizePosition)
        : [];
      phase.value = positions.value.length ? "ready" : "empty";
    } catch (reason) {
      fail(reason);
    }
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
  });
}
