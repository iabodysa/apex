<template>
  <div class="space-y-4">
    <h2 class="font-semibold">Support</h2>
    <div class="bg-white rounded-xl p-3 shadow-sm space-y-2">
      <select v-model="form.category" class="w-full border rounded-lg p-2">
        <option>Vehicle</option><option>Fuel</option><option>Attendance</option><option>Salary</option><option>Other</option>
      </select>
      <select v-model="form.priority" class="w-full border rounded-lg p-2">
        <option>Low</option><option>Medium</option><option>High</option><option>Urgent</option>
      </select>
      <input v-model="form.subject" placeholder="Subject" class="w-full border rounded-lg p-2" />
      <textarea v-model="form.description" placeholder="Describe the issue" class="w-full border rounded-lg p-2"></textarea>
      <button class="w-full bg-gray-700 text-white rounded-xl p-3 disabled:opacity-50"
              :disabled="create.loading || !form.subject" @click="submit">Raise Ticket</button>
      <p v-if="err" class="text-sm text-red-600">{{ err }}</p>
    </div>
    <div v-for="t in list.data" :key="t.name" class="bg-white rounded-xl p-3 shadow-sm">
      <div class="font-medium">{{ t.subject }}</div>
      <div class="text-sm text-gray-500">{{ t.category }} · {{ t.priority }} · {{ t.status }}</div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { createResource } from "frappe-ui";

const err = ref("");
const form = reactive({ category: "Vehicle", priority: "Medium", subject: "", description: "" });

const list = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_support_tickets",
  auto: true,
});
const create = createResource({
  url: "apex_habitat.salis.api.driver_portal.raise_support_ticket",
  onSuccess: () => { form.subject = ""; form.description = ""; err.value = ""; list.reload(); },
  onError: (e) => { err.value = e.messages?.[0] || "Error"; },
});

function submit() {
  create.submit({ ...form });
}
</script>
