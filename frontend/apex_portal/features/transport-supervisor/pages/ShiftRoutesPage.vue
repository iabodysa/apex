<script setup>
import { createResource } from "frappe-ui";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const shifts = createResource({
  url: "apex.salis.api.route_supervisor.get_shift_routes",
  method: "GET",
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="الشفتات"
    description="جدول التشغيل اليومي وما خُصص لكل شفت من مسار وسائق ومركبة."
    icon="calendar"
    :resource="shifts"
    :collections="['items']"
    empty="لا توجد شفتات مسندة حالياً."
  >
    <template #default="{ rows }">
      <div class="supervisor-shift-grid">
        <article v-for="shift in rows" :key="shift.name" class="supervisor-shift-card">
          <header>
            <span>الشفت</span>
            <strong dir="auto">{{ shift.shift_name || 'شفت تشغيل' }}</strong>
          </header>
          <dl>
            <div><dt>المسار</dt><dd dir="auto">{{ shift.route_template || 'غير محدد' }}</dd></div>
            <div><dt>المشروع</dt><dd dir="auto">{{ shift.project || 'غير محدد' }}</dd></div>
            <div><dt>السائق</dt><dd dir="auto">{{ shift.driver || 'غير مسند' }}</dd></div>
            <div><dt>المركبة</dt><dd><bdi dir="auto" translate="no">{{ shift.vehicle || 'غير مسندة' }}</bdi></dd></div>
          </dl>
          <bdi class="record-reference" dir="auto" translate="no">{{ shift.name }}</bdi>
        </article>
      </div>
    </template>
  </SupervisorCollection>
</template>
