import { createResource } from "frappe-ui";

export function createSupervisorBuildingsResource() {
  return createResource({
    url: "apex.habitat.api.front_desk.list_supervisor_buildings",
    method: "GET",
    auto: false,
  });
}
