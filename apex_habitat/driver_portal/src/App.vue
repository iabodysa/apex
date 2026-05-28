<template>
  <div class="min-h-screen bg-ah-sand flex flex-col max-w-md mx-auto font-sans text-ah-forest">
    <div v-if="ctx.loading" class="p-8 text-center text-ah-forest/60">Loading…</div>
    <div v-else-if="ctx.data && !ctx.data.enabled" class="p-8 text-center text-ah-forest/70">
      The driver portal is not enabled. Contact your supervisor.
    </div>
    <div v-else-if="ctx.error || (ctx.data && !ctx.data.linked)" class="p-8 text-center text-ah-danger">
      Your account is not linked to a driver profile.
    </div>
    <template v-else-if="ctx.data && ctx.data.driver">
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
  </div>
</template>

<style>
nav .router-link-active {
  color: #00844e;
  font-weight: 700;
}
</style>

<script setup>
import { createResource } from "frappe-ui";

const ctx = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_driver_context",
  auto: true,
});
</script>
