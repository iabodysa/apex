<script setup>
import { computed, onMounted } from "vue";
import { Button, FeatherIcon } from "frappe-ui";

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, required: true },
  icon: { type: String, required: true },
  resource: { type: Object, required: true },
  collections: { type: Array, default: () => [] },
  empty: { type: String, required: true },
});

const rows = computed(() => {
  if (Array.isArray(props.resource.data)) return props.resource.data;
  for (const key of props.collections) {
    if (Array.isArray(props.resource.data?.[key])) return props.resource.data[key];
  }
  return [];
});

function refresh() {
  return props.resource.fetch();
}

onMounted(refresh);
</script>

<template>
  <section class="feature-page supervisor-collection" :aria-busy="resource.loading">
    <header class="feature-page__heading supervisor-collection__heading">
      <div>
        <p class="feature-page__eyebrow">تشغيل النقل</p>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
      <div class="supervisor-collection__actions">
        <slot name="action" />
        <Button
          variant="outline"
          icon-left="refresh-cw"
          :loading="resource.loading"
          @click="refresh"
        >
          تحديث
        </Button>
        <FeatherIcon :name="icon" aria-hidden="true" />
      </div>
    </header>

    <div v-if="resource.loading && !resource.data" class="feature-state" role="status">
      جارٍ تحميل {{ title }}…
    </div>
    <div v-else-if="resource.error" class="feature-state feature-state--error">
      <p role="alert">تعذّر تحميل {{ title }}.</p>
      <Button variant="outline" @click="refresh">إعادة المحاولة</Button>
    </div>
    <div v-else-if="!rows.length" class="feature-state">{{ empty }}</div>
    <slot v-else :rows="rows" :data="resource.data" />
  </section>
</template>
