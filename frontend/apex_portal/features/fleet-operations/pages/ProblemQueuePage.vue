<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_problem_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage :title="__('Problems and Reports')" :resource="resource" detail-base="/problems" :empty="__('No problems exist within your projects.')" />
</template>
