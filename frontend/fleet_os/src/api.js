// Copyright (c) 2026, afmcoltd
import { call } from "@shared/call";

const FLEET_OS = "apex.salis.api.fleet_os";
const ALERTS = "apex.salis.api.operations_alerts";

const fleetOs = (method, opts = {}) => call(FLEET_OS + "." + method, opts);
const post = (method, args) => fleetOs(method, { args, type: "POST" });

export const getFleetOs = () => fleetOs("get_fleet_os");
export const getOpenAlerts = () => call(ALERTS + ".get_open_alerts");
export const searchDrivers = (q) => fleetOs("search_drivers", { args: { q }, type: "GET" });

export const reassign = (plate, driver_id, date) => post("reassign", { plate, driver_id, date });
export const createHandover = (args) => post("create_handover", args);
export const stopVehicle = (plate, reason) => post("stop_vehicle", { plate, reason });
export const workshopIn = (plate) => post("workshop_in", { plate });
export const workshopOut = (plate) => post("workshop_out", { plate });
export const recover = (plate) => post("recover", { plate });
export const reportTheft = (plate, location, report_number) =>
  post("report_theft", { plate, location, report_number });
export const bulkStopVehicles = (plates, reason) => post("bulk_stop_vehicles", { plates, reason });
export const bulkWorkshopIn = (plates, notes) => post("bulk_workshop_in", { plates, notes });
