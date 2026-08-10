// Copyright (c) 2026, afmcoltd
import { computed, reactive, ref } from "vue";

import {
  getFuelStations,
  getMyFuelRequests,
  getMyRecentTrips,
  getMyVehicle,
  submitFuelRequest,
} from "./api.js";
import { createResource } from "./resource.js";

const vehicleRes = createResource({
  fetcher: () => getMyVehicle().then((r) => (r && r.vehicle) || null),
  errorKey: "emp.loadError",
});
const tripsRes = createResource({
  fetcher: () => getMyRecentTrips().then((rows) => rows || []),
  initial: [],
  errorKey: "emp.loadError",
});
const fuelRes = createResource({
  fetcher: () => getMyFuelRequests().then((rows) => rows || []),
  initial: [],
  errorKey: "emp.loadError",
});
const stationsRes = createResource({
  fetcher: () => getFuelStations().then((rows) => rows || []),
  initial: [],
  errorKey: "emp.loadError",
});

const GRADES = ["petrol91", "petrol95", "diesel"];

const form = reactive({
  fuelGrade: "petrol91",
  litres: 60,
  station: "",
  notes: "",
});
const submitting = ref(false);

let started = false;

export async function ensureStations() {
  if (stationsRes.state.status === "idle") await stationsRes.reload();
  if (!form.station && stationsRes.state.data.length) form.station = stationsRes.state.data[0];
}

export async function submitFuel() {
  if (submitting.value) return { ok: false };
  submitting.value = true;
  try {
    const res = await submitFuelRequest({
      vehicle: vehicleRes.state.data?.name || null,
      fuel_grade: form.fuelGrade,
      litres: form.litres,
      station: form.station || null,
      notes: form.notes || null,
    });
    form.notes = "";
    await fuelRes.reload();
    return { ok: true, name: res && res.name };
  } catch (e) {
    return { ok: false, error: e };
  } finally {
    submitting.value = false;
  }
}

export function useEmployee() {
  if (!started) {
    started = true;
    vehicleRes.reload();
    tripsRes.reload();
    fuelRes.reload();
  }
  return {
    vehicle: vehicleRes,
    trips: tripsRes,
    fuelRequests: fuelRes,
    stations: stationsRes,
    grades: GRADES,
    form,
    submitting,
    hasVehicle: computed(() => Boolean(vehicleRes.state.data)),
    pendingFuelCount: computed(
      () => fuelRes.state.data.filter((r) => r.statusKey === "pending").length,
    ),
    latestFuelRequest: computed(() => fuelRes.state.data[0] || null),
  };
}
