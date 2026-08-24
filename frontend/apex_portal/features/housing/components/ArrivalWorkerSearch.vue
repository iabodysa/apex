<script setup>
import { ref } from "vue";
import { Badge, Button, FormControl, createResource } from "frappe-ui";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const props = defineProps({ building: { type: String, required: true } });
const emit = defineEmits(["choose-bed", "issue-link", "error"]);

const search = createResource({ url: "apex.habitat.api.arrivals_desk.search_arrivals_workers" });
const query = ref("");
const candidates = ref([]);

async function findWorker() {
  emit("error", "");
  try {
    candidates.value = await search.fetch({ building: props.building, txt: query.value });
  } catch (reason) {
    emit("error", safeErrorMessage(reason, __("Could not search for the worker.")));
  }
}
</script>

<template>
  <section class="arrival-panel">
    <div class="arrival-panel__title"><h3>{{ __("Search for a registered worker") }}</h3><span>{{ __("By name or number") }}</span></div>
    <div class="arrival-search"><FormControl v-model="query" :label="__('worker')" /><Button icon-left="lucide-search" variant="outline" :loading="search.loading" @click="findWorker">{{ __("Search") }}</Button></div>
    <article v-for="row in candidates" :key="`${row.party_type}:${row.party}`" class="arrival-row">
      <div><strong dir="auto">{{ row.label }}</strong><small dir="auto">{{ row.sub }}</small></div>
      <Badge :label="row.party_type === 'Employee' ? __('Emp') : __('Temporary Worker')" />
      <div class="feature-actions">
        <Button v-if="row.party_type === 'Employee'" variant="subtle" @click="$emit('issue-link', row)">{{ __("Link the Worker") }}</Button>
        <Button theme="green" variant="solid" @click="$emit('choose-bed', row)">{{ __("Choose a Bed") }}</Button>
      </div>
    </article>
  </section>
</template>
