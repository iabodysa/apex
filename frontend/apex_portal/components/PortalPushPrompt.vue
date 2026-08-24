<script setup>
import { computed, inject } from "vue";
import { Button } from "frappe-ui";
import { __ } from "../core/i18n.js";

const push = inject("portalPush", null);
const visible = computed(() => Boolean(push?.canOffer?.value || push?.error?.value));
</script>

<template>
  <aside v-if="visible" class="portal-push-prompt" aria-live="polite">
    <span class="lucide-bell" aria-hidden="true" />
    <div>
      <strong>{{ __("Trip alerts") }}</strong>
      <p>{{ push.error.value || __("Let the bus arrival alert reach you even when the app is closed.") }}</p>
    </div>
    <Button
      v-if="push.canOffer.value"
      theme="green"
      variant="solid"
      :loading="push.busy.value"
      @click="push.enable"
    >
      {{ __("Enable alerts") }}
    </Button>
  </aside>
</template>
