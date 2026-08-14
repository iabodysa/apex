<script setup>
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, createResource } from "frappe-ui";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
const route = useRoute(),
  resource = createResource({
    url: "apex.salis.api.fleet_os.get_problem_detail",
    method: "GET",
    auto: false,
  }),
  doc = computed(() => resource.data || null);
onMounted(() => resource.fetch({ name: route.params.name }));
</script>
<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>بلاغ تشغيلي</p>
        <h2>{{ doc?.subject || "تفاصيل البلاغ" }}</h2>
        <bdi class="record-reference" dir="auto" translate="no">{{ route.params.name }}</bdi>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" label="تحديث" @click="resource.fetch({ name: route.params.name })" />
    </header>
    <PortalSkeleton v-if="resource.loading" :rows="3" label="جارٍ تحميل البلاغ" />
    <PortalErrorState
      v-else-if="resource.error"
      title="تعذّر فتح البلاغ"
      :message="resource.error"
      fallback="تعذّر تحميل السجل. تحقق من الاتصال ثم حاول مرة أخرى."
      @retry="resource.fetch({ name: route.params.name })"
    />
    <article v-else-if="doc" class="ops-card">
      <Badge :theme="statusTheme(doc.status)" :label="statusLabel(doc.status)" />
      <h3>{{ doc.subject }}</h3>
      <p>{{ doc.description }}</p>
      <h3>المحادثة</h3>
      <ol>
        <li v-for="item in doc.communications || []" :key="item.name">
          <strong>{{ item.sender }}</strong>
          <p>{{ item.content }}</p>
        </li>
      </ol>
    </article>
    <div v-else class="ops-state ops-state--error">البلاغ غير موجود أو خارج نطاق مشروعك.</div>
  </section>
</template>
