<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_fleet_os",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage :title="__('Vehicles')" :resource="resource" rows-key="vehicles" detail-base="/vehicles" :empty="__('No vehicles exist within the projects you are permitted to see.')" live-doctype="Salis Vehicle" live-event="fleet_update" />
</template>
