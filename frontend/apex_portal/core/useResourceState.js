import { computed } from "vue";

/**
 * Derive the loading / error / empty / ready ladder a page renders around a frappe-ui resource
 * (`createResource`, or a `createDocumentResource`'s `.get`). Every portal page that fetches data
 * re-derives this same four-way branch by hand from `resource.loading` and `resource.error`; this
 * reads those two reactive flags off whatever resource the caller already created and owns — it
 * does not create, fetch, or hold a reference to the resource itself.
 *
 * `loading` and `error` are checked before `isEmpty` runs, so a still-loading or failed resource
 * never has its stale or absent data read as "empty". With no `isEmpty`, the ladder only ever
 * reports "loading", "error", or "ready" — there is no generic definition of "empty" across
 * shapes as different as a list, a single document, or a scalar quota.
 *
 * @param {{ loading: boolean, error: unknown }} resource - read reactively; only `loading` and
 *   `error` are used here, so a document resource's `.get` fits without adapting it.
 * @param {() => boolean} [isEmpty] - true when a resource that finished loading without error has
 *   nothing to show. Defaults to never reporting "empty".
 * @returns {import("vue").ComputedRef<"loading"|"error"|"empty"|"ready">}
 */
export function useResourceState(resource, isEmpty = () => false) {
  return computed(() => {
    if (resource.loading) return "loading";
    if (resource.error) return "error";
    return isEmpty() ? "empty" : "ready";
  });
}
