<template>
  <div class="min-h-screen bg-ah-sand flex flex-col max-w-md mx-auto font-sans text-ah-forest">
    <div v-if="ctx.loading" class="p-8 text-center text-ah-forest/60">Loading…</div>

    <!-- Linked driver: the existing home/nav shell (unchanged). -->
    <template v-else-if="linkedDriver">
      <header class="p-4 font-extrabold text-ah-surface bg-ah-forest">Apex Habitat</header>
      <main class="flex-1 p-4"><router-view :ctx="ctx.data" /></main>
      <nav class="grid grid-cols-5 border-t bg-ah-surface text-xs text-center text-ah-forest/70">
        <router-link to="/" class="p-2">Home</router-link>
        <router-link to="/attendance" class="p-2">Attend</router-link>
        <router-link to="/trips" class="p-2">Trips</router-link>
        <router-link to="/fuel" class="p-2">Fuel</router-link>
        <router-link to="/tickets" class="p-2">Tickets</router-link>
      </nav>
    </template>

    <!-- A genuine server error: surface it. Do NOT mis-render it as "not linked". -->
    <div v-else-if="ctx.error" class="p-8 text-center text-ah-danger">
      <p class="font-bold mb-2">Couldn't load the portal</p>
      <p class="text-sm opacity-80">{{ ctx.error.message || ctx.error }}</p>
      <button class="mt-4 px-4 py-2 rounded bg-ah-forest text-ah-surface" @click="ctx.reload()">
        Retry
      </button>
    </div>

    <!-- Everyone else (staff or non-staff): a useful screen, never a dead-end. -->
    <Unlinked v-else :ctx="unlinkedCtx" />
  </div>
</template>

<style>
nav .router-link-active {
  color: #00844e;
  font-weight: 700;
}
</style>

<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import Unlinked from "./components/Unlinked.vue";

const ctx = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_driver_context",
  auto: true,
});

const linkedDriver = computed(
  () => ctx.data && ctx.data.enabled && ctx.data.linked && ctx.data.driver,
);

// Normalise the payload for the Unlinked screen. On a bootstrap error (rare —
// the API is designed not to 403) we fall back to a safe non-staff shape so the
// user still gets the friendly explainer instead of a blank/crashed page.
const unlinkedCtx = computed(() => {
  const d = ctx.data || {};
  return {
    is_staff: !!d.is_staff,
    full_name: d.full_name || "",
    links: d.links || [],
  };
});
</script>
