<template>
  <div class="space-y-4">
    <div class="bg-ah-surface rounded-xl p-4 shadow-sm">
      <div class="text-lg font-semibold">{{ ctx.driver.full_name }}</div>
      <div class="text-sm text-ah-forest/60">Status: {{ ctx.driver.status }}</div>
      <div class="text-sm text-ah-forest/60">Vehicle: {{ ctx.driver.current_vehicle || "—" }}</div>
      <div v-if="ctx.driver.license_expiry" class="text-sm text-ah-forest/60">
        License expiry: {{ ctx.driver.license_expiry }}
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3">
      <router-link to="/attendance" class="bg-ah-primary text-white rounded-xl p-4 text-center">Attendance</router-link>
      <router-link to="/trips" class="bg-ah-forest text-white rounded-xl p-4 text-center">My Trips</router-link>
      <router-link to="/fuel" class="bg-ah-warning text-white rounded-xl p-4 text-center">Request Fuel</router-link>
      <router-link to="/tickets" class="bg-ah-accent text-ah-forest rounded-xl p-4 text-center">Support</router-link>
    </div>
  </div>
</template>

<script setup>
defineProps({ ctx: { type: Object, required: true } });
</script>
