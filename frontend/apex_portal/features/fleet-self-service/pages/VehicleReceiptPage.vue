<script setup>
import VehicleHandoverForm from "../components/VehicleHandoverForm.vue";
import { __ } from "../../../core/i18n.js";
</script>

<template>
  <VehicleHandoverForm
    direction="Receipt"
    :title="__('Vehicle Receipt')"
    :intro="__('Check every item in the approved template and attach the signed evidence before confirming receipt.')"
  />
</template>
