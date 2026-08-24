<script setup>
import VehicleHandoverForm from "../components/VehicleHandoverForm.vue";
import { __ } from "../../../core/i18n.js";
</script>

<template>
  <VehicleHandoverForm
    direction="Return"
    :title="__('Vehicle Return')"
    :intro="__('Check every item in the approved template and attach the signed evidence before confirming return.')"
  />
</template>
