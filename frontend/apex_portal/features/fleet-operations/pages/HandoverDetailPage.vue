<script setup>
import { useRoute } from "vue-router";
import { Badge, Button, createDocumentResource } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";

const route = useRoute();
const handover = createDocumentResource({
  doctype: "Vehicle Handover",
  name: route.params.name,
});

const directionLabel = (value) => ({ Receipt: __("Receipt"), Return: __("Return"), Transfer: __("Transfer") })[value] || value || __("Vehicle Handover");
</script>

<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>{{ directionLabel(handover.doc?.direction) }}</p>
        <h2 dir="auto">{{ handover.doc?.vehicle || __("Vehicle Handover Details") }}</h2>
        <bdi class="record-reference" dir="auto" translate="no">{{ route.params.name }}</bdi>
      </div>
      <Button variant="outline" icon-left="lucide-refresh-cw" :loading="handover.get.loading" @click="handover.reload()">{{ __("Refresh") }}</Button>
    </header>

    <PortalSkeleton v-if="handover.get.loading" :rows="3" :label="__('Loading vehicle handover')" />
    <PortalErrorState
      v-else-if="handover.get.error"
      :title="__('Could not load vehicle handover')"
      :message="handover.get.error"
      @retry="handover.reload()"
    />
    <template v-else-if="handover.doc">
      <article class="ops-card">
        <Badge :theme="statusTheme(handover.doc.discrepancy_status)" :label="statusLabel(handover.doc.discrepancy_status)" />
        <dl>
          <div><dt>{{ __("From Driver") }}</dt><dd><bdi dir="auto" translate="no">{{ handover.doc.from_driver || "—" }}</bdi></dd></div>
          <div><dt>{{ __("To Driver") }}</dt><dd><bdi dir="auto" translate="no">{{ handover.doc.to_driver || "—" }}</bdi></dd></div>
          <div><dt>{{ __("Date") }}</dt><dd><bdi>{{ handover.doc.handover_date || "—" }}</bdi></dd></div>
          <div><dt>{{ __("Current Odometer Reading") }}</dt><dd><bdi>{{ handover.doc.odometer_reading ?? "—" }}</bdi></dd></div>
          <div><dt>{{ __("Fuel Level") }}</dt><dd>{{ handover.doc.fuel_level || "—" }}</dd></div>
          <div><dt>{{ __("Location") }}</dt><dd dir="auto">{{ handover.doc.handover_location || "—" }}</dd></div>
        </dl>
      </article>

      <section class="ops-card">
        <h3>{{ __("Inspection Checklist") }}</h3>
        <p v-if="!handover.doc.handover_check_items?.length" class="ops-reason">{{ __("No inspection items have been loaded for this record yet.") }}</p>
        <div v-else class="ops-table" role="table" :aria-label="__('Vehicle Handover Inspection Checklist')">
          <div v-for="item in handover.doc.handover_check_items" :key="item.name || item.idx" class="ops-row" role="row">
            <div>
              <strong dir="auto">{{ item.check_item }}</strong>
              <span v-if="item.remark" dir="auto">{{ item.remark }}</span>
            </div>
            <Badge :theme="item.ok ? 'green' : 'orange'" :label="item.ok ? __('OK') : __('Needs Review')" />
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
