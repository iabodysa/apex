<script setup>
import { Button } from "frappe-ui";
import { dateTimeLabel } from "../../core/displayLabels.js";

defineProps({
  stops: { type: Array, default: () => [] },
  started: { type: Boolean, default: false },
  busy: { type: String, default: "" },
  mapsRouteUrl: { type: String, default: "" },
});
defineEmits(["arrive", "toggle"]);
</script>

<template>
  <section class="journey-section">
    <div class="journey-section__title">
      <h3>المحطات</h3>
      <a v-if="mapsRouteUrl" class="journey-link" :href="mapsRouteUrl" target="_blank" rel="noopener">افتح الخريطة</a>
    </div>
    <ol class="driver-timeline">
      <li v-for="(stop, index) in stops" :key="stop.route_stop || index" :class="{ 'is-done': stop.done }">
        <span class="driver-timeline__number">{{ index + 1 }}</span>
        <div class="driver-timeline__copy">
          <strong>{{ stop.stop_name || stop.location || "محطة" }}</strong>
          <small>
            {{ stop.arrived ? "وصلت" : stop.done ? "اكتملت" : "قادمة" }}
            <template v-if="stop.planned_time">
              ·
              <bdi>{{ dateTimeLabel(stop.planned_time) }}</bdi>
            </template>
          </small>
          <div v-if="stop.pickup" class="driver-stop-meta">
            <span v-if="stop.pickup.building_name">{{ stop.pickup.building_name }}</span>
            <span v-if="stop.pickup.city">{{ stop.pickup.city }}</span>
            <a v-if="stop.pickup.google_maps_url" :href="stop.pickup.google_maps_url" target="_blank" rel="noopener">افتح موقع المحطة</a>
          </div>
        </div>
        <div class="journey-actions">
          <Button variant="outline" :disabled="!started || stop.arrived" :loading="busy === `arrive:${stop.route_stop}`" @click="$emit('arrive', stop.route_stop)">وصلت</Button>
          <Button variant="outline" :disabled="!started" :loading="busy === `stop:${stop.route_stop}`" @click="$emit('toggle', stop.route_stop, Boolean(stop.done))">{{ stop.done ? "إلغاء اكتمال المحطة" : "غادرت المحطة" }}</Button>
        </div>
      </li>
    </ol>
    <p v-if="!stops.length" class="feature-state">لا توجد محطات مخططة لهذه الرحلة.</p>
  </section>
</template>
