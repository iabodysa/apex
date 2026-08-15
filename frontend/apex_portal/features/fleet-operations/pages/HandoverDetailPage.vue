<script setup>
import { useRoute } from "vue-router";
import { Badge, Button, createDocumentResource } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";

const route = useRoute();
const handover = createDocumentResource({
  doctype: "Vehicle Handover",
  name: route.params.name,
});

const directionLabel = (value) => ({ Receipt: "استلام", Return: "إرجاع", Transfer: "نقل" })[value] || value || "تسليم مركبة";
</script>

<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>{{ directionLabel(handover.doc?.direction) }}</p>
        <h2 dir="auto">{{ handover.doc?.vehicle || "تفاصيل تسليم المركبة" }}</h2>
        <bdi class="record-reference" dir="auto" translate="no">{{ route.params.name }}</bdi>
      </div>
      <Button variant="outline" icon-left="lucide-refresh-cw" :loading="handover.get.loading" @click="handover.reload()">تحديث</Button>
    </header>

    <PortalSkeleton v-if="handover.get.loading" :rows="3" label="جارٍ تحميل تسليم المركبة" />
    <PortalErrorState
      v-else-if="handover.get.error"
      title="تعذّر تحميل تسليم المركبة"
      :message="handover.get.error"
      @retry="handover.reload()"
    />
    <template v-else-if="handover.doc">
      <article class="ops-card">
        <Badge :theme="statusTheme(handover.doc.discrepancy_status)" :label="statusLabel(handover.doc.discrepancy_status)" />
        <dl>
          <div><dt>من السائق</dt><dd><bdi dir="auto" translate="no">{{ handover.doc.from_driver || "—" }}</bdi></dd></div>
          <div><dt>إلى السائق</dt><dd><bdi dir="auto" translate="no">{{ handover.doc.to_driver || "—" }}</bdi></dd></div>
          <div><dt>التاريخ</dt><dd><bdi>{{ handover.doc.handover_date || "—" }}</bdi></dd></div>
          <div><dt>قراءة العداد</dt><dd><bdi>{{ handover.doc.odometer_reading ?? "—" }}</bdi></dd></div>
          <div><dt>مستوى الوقود</dt><dd>{{ handover.doc.fuel_level || "—" }}</dd></div>
          <div><dt>الموقع</dt><dd dir="auto">{{ handover.doc.handover_location || "—" }}</dd></div>
        </dl>
      </article>

      <section class="ops-card">
        <h3>قائمة الفحص</h3>
        <p v-if="!handover.doc.handover_check_items?.length" class="ops-reason">لم تُحمّل بنود فحص لهذا السجل بعد.</p>
        <div v-else class="ops-table" role="table" aria-label="قائمة فحص تسليم المركبة">
          <div v-for="item in handover.doc.handover_check_items" :key="item.name || item.idx" class="ops-row" role="row">
            <div>
              <strong dir="auto">{{ item.check_item }}</strong>
              <span v-if="item.remark" dir="auto">{{ item.remark }}</span>
            </div>
            <Badge :theme="item.ok ? 'green' : 'orange'" :label="item.ok ? 'سليم' : 'يحتاج مراجعة'" />
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
