<script setup>
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, createResource } from "frappe-ui";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
const route = useRoute(),
  resource = createResource({
    url: "apex.salis.api.fleet_os.get_incident_detail",
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
        <p>حادث</p>
        <h2>{{ doc?.vehicle_plate || doc?.vehicle || doc?.incident_type || "تفاصيل الحادث" }}</h2>
        <bdi class="record-reference" dir="auto" translate="no">{{ route.params.name }}</bdi>
      </div>
      <Button variant="outline" icon="refresh-cw" label="تحديث" @click="resource.fetch({ name: route.params.name })" />
    </header>
    <div v-if="resource.loading" class="ops-state">جاري التحميل…</div>
    <article v-else-if="doc" class="ops-card">
      <Badge :theme="statusTheme(doc.status)" :label="statusLabel(doc.status)" />
      <h3>{{ doc.incident_type }}</h3>
      <p>{{ doc.description }}</p>
      <dl>
        <div>
          <dt>المركبة</dt>
          <dd>
            <bdi>{{ doc.vehicle_plate || doc.vehicle }}</bdi>
          </dd>
        </div>
        <div>
          <dt>الموقع</dt>
          <dd>{{ doc.location || "—" }}</dd>
        </div>
      </dl>
      <p class="ops-reason">إجراءات التأمين والاسترداد والإغلاق تأتي من الصلاحيات التي يرجعها الخادم.</p>
    </article>
    <div v-else class="ops-state ops-state--error">السجل غير موجود أو خارج نطاق مشروعك.</div>
  </section>
</template>
