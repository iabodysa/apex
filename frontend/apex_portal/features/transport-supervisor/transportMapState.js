import { computed, ref } from "vue";

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
      positions.value = Array.isArray(result?.positions) ? result.positions : [];
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
