<template>
  <div class="space-y-5">
    <h2 class="section-title">Support</h2>

    <!-- Raise a ticket -->
    <section class="card card-pad space-y-3">
      <p class="text-sm text-soft">Need help? Raise a ticket and the team will follow up.</p>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="field-label">Category</label>
          <select v-model="form.category" class="select">
            <option>Vehicle</option><option>Fuel</option><option>Attendance</option><option>Salary</option><option>Other</option>
          </select>
        </div>
        <div>
          <label class="field-label">Priority</label>
          <select v-model="form.priority" class="select">
            <option>Low</option><option>Medium</option><option>High</option><option>Urgent</option>
          </select>
        </div>
      </div>

      <div>
        <label class="field-label">Subject</label>
        <input v-model="form.subject" placeholder="Short summary" class="input" />
      </div>
      <div>
        <label class="field-label">Description</label>
        <textarea v-model="form.description" placeholder="Describe the issue" class="textarea"></textarea>
      </div>

      <button class="btn btn-primary" :disabled="create.loading || !form.subject" @click="submit">
        <Icon name="help" :size="20" /> Raise Ticket
      </button>
      <p v-if="err" class="text-sm text-danger">{{ err }}</p>
    </section>

    <!-- My tickets -->
    <section v-if="list.data && list.data.length" class="space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">My tickets</h3>
      <div v-for="t in list.data" :key="t.name" class="card card-pad">
        <div class="flex items-start justify-between gap-2">
          <div class="font-bold leading-tight">{{ t.subject }}</div>
          <span class="pill shrink-0" :class="statusPill(t.status)">{{ t.status }}</span>
        </div>
        <div class="mt-1 text-sm text-muted">{{ t.category }} · {{ t.priority }}</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";

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

// Map ticket status to a status pill (purely cosmetic).
function statusPill(status) {
  const s = (status || "").toLowerCase();
  if (s === "resolved" || s === "closed") return "pill-success";
  if (s === "waiting") return "pill-warning";
  if (s === "cancelled") return "pill-danger";
  return "pill-accent";
}
</script>
