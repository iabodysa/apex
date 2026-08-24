<script setup>
import { Badge } from "frappe-ui";
import { dateTimeLabel, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";

defineProps({
  stops: { type: Array, default: () => [] },
  assignedRequests: { type: Array, default: () => [] },
  passengers: { type: Array, default: () => [] },
});
</script>

<template>
  <section v-if="stops.length" class="supervisor-detail__section">
    <header><h3>{{ __("Route Stops") }}</h3><span>{{ stops.length }}</span></header>
    <ol class="supervisor-stop-list">
      <li v-for="stop in stops" :key="stop.name || stop.stop_key">
        <bdi>{{ String(stop.idx || 0).padStart(2, '0') }}</bdi>
        <div><strong dir="auto">{{ stop.stop_name }}</strong><span dir="auto">{{ stop.location || stop.accommodation_building || __("Location Not Specified") }}</span></div>
        <span>{{ dateTimeLabel(stop.planned_time) || '—' }}</span>
      </li>
    </ol>
  </section>

  <section v-if="assignedRequests.length" class="supervisor-detail__section">
    <header><h3>{{ __("Requests Assigned to Trip") }}</h3><span>{{ assignedRequests.length }}</span></header>
    <ol class="supervisor-assigned-list">
      <li v-for="request in assignedRequests" :key="request.name || request.transport_request">
        <div class="record-identity">
          <strong dir="auto">{{ request.purpose || __("Transport Request") }}</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ request.transport_request }}</bdi>
        </div>
        <span dir="auto">{{ request.pickup_stop }} ← {{ request.dropoff_stop }}</span>
        <span><bdi>{{ request.requested_count || 0 }}</bdi> {{ __("passenger") }}</span>
      </li>
    </ol>
  </section>

  <!-- The planning panels the record type dispatches to belong between the two lists on screen. -->
  <slot />

  <section v-if="passengers.length" class="supervisor-detail__section">
    <header><h3>{{ __("Passenger List") }}</h3><span>{{ passengers.length }}</span></header>
    <ol class="supervisor-passenger-list">
      <li v-for="passenger in passengers" :key="passenger.passenger_key || passenger.name">
        <div><strong dir="auto">{{ passenger.passenger_name || __("Unnamed Passenger") }}</strong><span dir="auto">{{ passenger.pickup_stop }} ← {{ passenger.dropoff_stop }}</span></div>
        <Badge :theme="statusTheme(passenger.status)" :label="statusLabel(passenger.status)" />
      </li>
    </ol>
  </section>
</template>
