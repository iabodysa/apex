<script setup>
import { inject } from "vue";
import { Button } from "frappe-ui";
import { __ } from "../core/i18n.js";

const update = inject("portalUpdate", null);
</script>

<template>
  <aside v-if="update?.ready?.value" class="portal-update-prompt" aria-live="polite">
    <span class="lucide-download" aria-hidden="true" />
    <div>
      <strong>{{ __("A new version is ready") }}</strong>
      <p>{{ __("Update now to get the latest screens and fixes.") }}</p>
    </div>
    <Button theme="green" variant="solid" :loading="update.busy.value" @click="update.apply">
      {{ __("Update now") }}
    </Button>
  </aside>
</template>
