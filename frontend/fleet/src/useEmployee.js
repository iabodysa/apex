// Copyright (c) 2026, afmcoltd
import { reactive, ref } from "vue";
import { call } from "./api.js";

const API = "apex.salis.api.fleet_employee";

const vehicle = reactive({
  empty: true,
  name: null,
  plate: "",
  model: "",
  office: "",
  status: "available",
  odometerKm: null,
  registrationExpiry: null,
});

const trips = ref([]);

const fuelGrades = ["petrol91", "petrol95", "diesel"];
const stations = ref([]);
const form = reactive({
  fuelGrade: "petrol91",
  litres: 60,
  station: "",
  notes: "",
});
const submitting = ref(false);
const loading = ref(true);
const loadError = ref(false);
let started = false;

async function loadVehicle() {
  const res = await call(`${API}.get_my_vehicle`);
  const v = res && res.vehicle;
  if (!v) {
    vehicle.empty = true;
    return;
  }
  Object.assign(vehicle, {
    empty: false,
    name: v.name,
    plate: v.plate || "",
    model: v.model || "",
    office: v.office || "",
    status: v.status || "available",
    odometerKm: v.odometerKm ?? null,
    registrationExpiry: v.registrationExpiry || null,
  });
}

async function loadTrips() {
  trips.value = (await call(`${API}.get_my_recent_trips`)) || [];
}

export function fetchFuelRequests({ days = 90, limit = 30 } = {}) {
  return call(`${API}.get_my_fuel_requests`, { args: { days, limit } }).then((rows) => rows || []);
}

export function fetchTrips({ days = 90, limit = 100 } = {}) {
  return call(`${API}.get_my_recent_trips`, { args: { days, limit } }).then((rows) => rows || []);
}

async function loadStations() {
  const list = (await call(`${API}.get_fuel_stations`)) || [];
  stations.value = list;
  if (list.length && !form.station) form.station = list[0];
}

async function load() {
  loading.value = true;
  loadError.value = false;
  try {
    await Promise.all([loadVehicle(), loadTrips(), loadStations()]);
  } catch (e) {
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

async function submitFuelRequest() {
  if (submitting.value) return { ok: false };
  submitting.value = true;
  try {
    const res = await call(`${API}.submit_fuel_request`, {
      type: "POST",
      args: {
        vehicle: vehicle.name || null,
        fuel_grade: form.fuelGrade,
        litres: form.litres,
        station: form.station || null,
        notes: form.notes || null,
      },
    });
    form.notes = "";
    return { ok: true, name: res && res.name };
  } finally {
    submitting.value = false;
  }
}

export function useEmployee() {
  if (!started) {
    started = true;
    load();
  }
  return {
    vehicle,
    trips,
    fuelGrades,
    stations,
    form,
    submitting,
    loading,
    loadError,
    submitFuelRequest,
    reload: load,
  };
}
