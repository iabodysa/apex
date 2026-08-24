<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { __ } from "./core/i18n.js";

// The worker and driver personas hold no account and reach no desk, so the standard refusal
// sends them to a system administrator who does not exist for them. Their link is a one-time
// key: once it is spent the only way back is a new one from the supervisor who issued it.
const PASSWORDLESS_ENTRIES = ["worker", "driver"];

const route = useRoute();
const body = computed(() =>
  PASSWORDLESS_ENTRIES.includes(route.meta.entry)
    ? __("Ask your supervisor for a new link.")
    : __("Go back to the home page or contact your system administrator."),
);
</script>

<template>
  <section class="access-denied" aria-labelledby="access-denied-title">
    <h2 id="access-denied-title">{{ __("You do not have access") }}</h2>
    <p>{{ body }}</p>
  </section>
</template>
