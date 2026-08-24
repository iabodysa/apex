<script setup>
import { ref } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import QRCode from "qrcode";
import { dateTimeLabel, workerTransportStatusLabel } from "../../core/displayLabels.js";
import { __ } from "../../core/i18n.js";

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
      <h3>{{ __("Upcoming trips") }}</h3>
      <span>{{ trips.length }}</span>
    </div>
    <article v-for="trip in trips" :key="trip.transport_request" class="journey-card">
      <div class="journey-card__main">
        <Badge :label="workerTransportStatusLabel(trip.boarding_window?.state || trip.trip_status)" />
        <h3>
          {{ trip.destination?.location || trip.destination?.stop_name || trip.pickup_point || __("Masar trip") }}
        </h3>
        <p>
          {{ trip.pickup_point || trip.my_pickup?.stop_name || __("Gathering Point") }}
        </p>
      </div>
      <dl class="journey-facts">
        <div>
          <dt>{{ __("Time") }}</dt>
          <dd>
            <bdi>{{ dateTimeLabel(trip.pickup_datetime || trip.depart_time) || __("To be determined later") }}</bdi>
          </dd>
        </div>
        <div>
          <dt>{{ __("Bus") }}</dt>
          <dd><bdi dir="auto" translate="no">{{ trip.vehicle?.plate_number || __("Not yet assigned") }}</bdi></dd>
        </div>
        <div>
          <dt>{{ __("driver") }}</dt>
          <dd>{{ trip.driver?.full_name || __("Not yet assigned") }}</dd>
        </div>
      </dl>
      <div class="journey-actions">
        <a v-if="trip.maps_route_url" class="journey-link" :href="trip.maps_route_url" target="_blank" rel="noopener">{{ __("View route") }}</a>
        <Button variant="outline" :loading="busy === `pass:${trip.transport_request}`" @click="showPass(trip.transport_request)">{{ __("Boarding pass") }}</Button>
      </div>
    </article>
  </div>

  <article v-if="pass" class="boarding-pass" aria-live="polite">
    <div>
      <span class="journey-kicker">{{ __("Boarding pass") }}</span>
      <h3>{{ pass.destination_label || __("Masar trip") }}</h3>
      <p>{{ pass.pickup_label }}</p>
    </div>
    <img v-if="passImage" :src="passImage" :alt="__('Boarding pass code')" />
  </article>
</template>
