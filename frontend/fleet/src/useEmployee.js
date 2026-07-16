// Copyright (c) 2026, AFMCO and contributors
//
// Employee self-service data layer for the /fleet page (my vehicle · fuel
// request · my recent trips). Wired to the identity-scoped backend in
// apex.salis.api.fleet_employee — every endpoint resolves the session user to
// their own Salis Driver server-side, so this only ever shows the caller's own
// vehicle / trips and can only submit fuel for the caller's own vehicle.
//
// A user with no fleet vehicle (an ordinary office employee) gets a clean empty
// state, never an error: get_my_vehicle -> {vehicle:null}, get_my_recent_trips
// -> [], and submitting fuel throws a friendly "no vehicle assigned" message.
import { reactive, ref, onMounted } from "vue";
import { call } from "./api.js";

const API = "apex.salis.api.fleet_employee";

export function useEmployee() {
  // ── my assigned vehicle ────────────────────────────────────────────────
  // Shape mirrors the get_my_vehicle() row. `empty` drives the card's empty
  // state (no fleet vehicle bound to this user). status ∈ available|assigned|
  // workshop|stopped so the status pill reuses the board's semantics.
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

  // ── my recent trips ────────────────────────────────────────────────────
  const trips = ref([]);

  // ── Fuel request form ──────────────────────────────────────────────────
  // Grades reuse the existing i18n dictionary; stations load from the backend.
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

  // Send the fuel request for supervisor approval. Resolves { ok, name } on
  // success; rejects (so the caller can surface the server's message) on error.
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

  onMounted(load);

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
