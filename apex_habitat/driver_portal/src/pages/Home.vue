<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl p-4 shadow-sm">
      <div class="text-lg font-semibold">{{ ctx.driver.full_name }}</div>
      <div class="text-sm text-gray-500">Status: {{ ctx.driver.status }}</div>
      <div class="text-sm text-gray-500">Vehicle: {{ ctx.driver.current_vehicle || "—" }}</div>
      <div v-if="ctx.driver.license_expiry" class="text-sm text-gray-500">
        License expiry: {{ ctx.driver.license_expiry }}
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3">
      <router-link to="/attendance" class="bg-green-600 text-white rounded-xl p-4 text-center">Attendance</router-link>
      <router-link to="/trips" class="bg-blue-600 text-white rounded-xl p-4 text-center">My Trips</router-link>
      <router-link to="/fuel" class="bg-amber-600 text-white rounded-xl p-4 text-center">Request Fuel</router-link>
      <router-link to="/tickets" class="bg-gray-700 text-white rounded-xl p-4 text-center">Support</router-link>
    </div>
  </div>
</template>

<script setup>
defineProps({ ctx: { type: Object, required: true } });
</script>
