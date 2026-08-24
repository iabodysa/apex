<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_handover_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage :title="__('Handover Queue')" :resource="resource" detail-base="/handovers" :empty="__('No handover documents are pending.')" />
</template>
