<script setup>
import { ref } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import QRCode from "qrcode";
import { dateTimeLabel, workerTransportStatusLabel } from "../../core/displayLabels.js";

defineProps({ trips: { type: Array, default: () => [] } });
const emit = defineEmits(["error"]);

const boardingPassResource = createResource({
  url: "apex.salis.api.masar.get_worker_boarding_pass",
  method: "GET",
  auto: false,
});
const pass = ref(null);
const passImage = ref("");
const busy = ref("");

async function showPass(request) {
  busy.value = `pass:${request}`;
  emit("error", null);
  try {
    const result = await boardingPassResource.fetch({ transport_request: request });
    pass.value = result?.pass || null;
    passImage.value = pass.value?.qr_payload ? await QRCode.toDataURL(pass.value.qr_payload, { margin: 1, width: 320 }) : "";
  } catch (reason) {
    emit("error", reason);
  } finally {
    busy.value = "";
  }
}
</script>

<template>
  <div class="journey-section">
    <div class="journey-section__title">
      <h3>الرحلات القادمة</h3>
      <span>{{ trips.length }}</span>
    </div>
    <article v-for="trip in trips" :key="trip.transport_request" class="journey-card">
      <div class="journey-card__main">
        <Badge :label="workerTransportStatusLabel(trip.boarding_window?.state || trip.trip_status)" />
        <h3>
          {{ trip.destination?.location || trip.destination?.stop_name || trip.pickup_point || "رحلة مسار" }}
        </h3>
        <p>
          {{ trip.pickup_point || trip.my_pickup?.stop_name || "نقطة التجمع" }}
        </p>
      </div>
      <dl class="journey-facts">
        <div>
          <dt>الموعد</dt>
          <dd>
            <bdi>{{ dateTimeLabel(trip.pickup_datetime || trip.depart_time) || "يحدد لاحقاً" }}</bdi>
          </dd>
        </div>
        <div>
          <dt>الحافلة</dt>
          <dd>{{ trip.vehicle?.plate_number || "تحت الإسناد" }}</dd>
        </div>
        <div>
          <dt>السائق</dt>
          <dd>{{ trip.driver?.full_name || "تحت الإسناد" }}</dd>
        </div>
      </dl>
      <div class="journey-actions">
        <a v-if="trip.maps_route_url" class="journey-link" :href="trip.maps_route_url" target="_blank" rel="noopener">عرض المسار</a>
        <Button variant="outline" :loading="busy === `pass:${trip.transport_request}`" @click="showPass(trip.transport_request)">بطاقة الصعود</Button>
      </div>
    </article>
  </div>

  <article v-if="pass" class="boarding-pass" aria-live="polite">
    <div>
      <span class="journey-kicker">بطاقة الصعود</span>
      <h3>{{ pass.destination_label || "رحلة مسار" }}</h3>
      <p>{{ pass.pickup_label }}</p>
    </div>
    <img v-if="passImage" :src="passImage" alt="رمز بطاقة الصعود" />
  </article>
</template>
