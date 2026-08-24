<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_incident_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage :title="__('Incidents')" :resource="resource" detail-base="/incidents" :empty="__('No incidents exist within your projects.')" />
</template>
