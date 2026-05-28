<template>
  <div class="min-h-screen bg-gray-50 flex flex-col max-w-md mx-auto">
    <div v-if="ctx.loading" class="p-8 text-center text-gray-500">Loading…</div>
    <div v-else-if="ctx.data && !ctx.data.enabled" class="p-8 text-center text-gray-600">
      The driver portal is not enabled. Contact your supervisor.
    </div>
    <div v-else-if="ctx.error" class="p-8 text-center text-red-600">
      Your account is not linked to a driver profile.
    </div>
    <template v-else-if="ctx.data && ctx.data.driver">
      <header class="p-4 font-semibold text-gray-800 border-b bg-white">Salis Driver</header>
      <main class="flex-1 p-4"><router-view :ctx="ctx.data" /></main>
      <nav class="grid grid-cols-5 border-t bg-white text-xs text-center text-gray-600">
        <router-link to="/" class="p-2">Home</router-link>
        <router-link to="/attendance" class="p-2">Attend</router-link>
        <router-link to="/trips" class="p-2">Trips</router-link>
        <router-link to="/fuel" class="p-2">Fuel</router-link>
        <router-link to="/tickets" class="p-2">Tickets</router-link>
      </nav>
    </template>
  </div>
</template>

<script setup>
import { createResource } from "frappe-ui";

const ctx = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_driver_context",
  auto: true,
});
</script>
