<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_return_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage :title="__('Return Queue')" :resource="resource" detail-base="/returns" :empty="__('No vehicles are awaiting return.')" />
</template>
