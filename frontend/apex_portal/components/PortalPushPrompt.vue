<script setup>
import { computed, inject } from "vue";
import { Button, FeatherIcon } from "frappe-ui";

const push = inject("portalPush", null);
const visible = computed(() => Boolean(push?.canOffer?.value || push?.error?.value));
</script>

<template>
  <aside v-if="visible" class="portal-push-prompt" aria-live="polite">
    <FeatherIcon name="bell" aria-hidden="true" />
    <div>
      <strong>تنبيهات الرحلة</strong>
      <p>{{ push.error.value || "خلّ تنبيه وصول الحافلة يوصلك حتى لو التطبيق مقفل." }}</p>
    </div>
    <Button
      v-if="push.canOffer.value"
      theme="green"
      variant="solid"
      :loading="push.busy.value"
      @click="push.enable"
    >
      فعّل التنبيهات
    </Button>
  </aside>
</template>
