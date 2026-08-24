<script setup>
import { inject, reactive, ref, watch } from "vue";
import { Badge, Button, FormControl, createResource } from "frappe-ui";
import { dateTimeLabel, workerTransportStatusLabel } from "../../core/displayLabels.js";
import { __ } from "../../core/i18n.js";

const props = defineProps({ trips: { type: Array, default: () => [] } });
const emit = defineEmits(["error", "rated"]);

const drafts = inject("portalDrafts", null);
const ratingResource = createResource({
  url: "apex.salis.api.masar.submit_trip_rating",
  method: "POST",
  auto: false,
});
const ratingDrafts = reactive({});
const ratingMessages = reactive({});
const busy = ref("");

const ratingKey = (trip) => `trip-rating-${trip.dispatch_trip}`;
const blankRating = Object.freeze({ rating: 0, feedback: "" });

// Drafts are restored once per past trip in a pre-flush watcher, so the template only reads them.
function seedRatingDraft(trip) {
  const id = trip.dispatch_trip;
  if (!id || ratingDrafts[id]) return;
  const saved = drafts?.read(ratingKey(trip));
  ratingDrafts[id] = {
    rating: [1, 2, 3, 4, 5].includes(Number(saved?.rating)) ? Number(saved.rating) : 0,
    feedback: String(saved?.feedback || "").slice(0, 2000),
  };
}

watch(() => props.trips, (list) => list.forEach(seedRatingDraft), { immediate: true });

function ratingDraft(trip) {
  return ratingDrafts[trip.dispatch_trip] || blankRating;
}

// portalDrafts is subject-scoped; only trip rating text is durable. QR and boarding tokens stay transient.
function persistRating(trip) {
  drafts?.write(ratingKey(trip), { ...ratingDraft(trip) });
}

function setRating(trip, rating) {
  seedRatingDraft(trip);
  ratingDraft(trip).rating = rating;
  persistRating(trip);
}

function setRatingFeedback(trip, feedback) {
  seedRatingDraft(trip);
  ratingDraft(trip).feedback = feedback;
  persistRating(trip);
}

function dismissRating(trip) {
  drafts?.clear(ratingKey(trip));
  ratingDrafts[trip.dispatch_trip] = { rating: 0, feedback: "" };
}

async function rateTrip(trip) {
  const draft = ratingDraft(trip);
  if (!draft.rating) return;
  const key = `rating:${trip.dispatch_trip}`;
  busy.value = key;
  emit("error", null);
  try {
    await ratingResource.submit({
      dispatch_trip: trip.dispatch_trip,
      rating: draft.rating,
      feedback: draft.feedback,
    });
    emit("rated", trip);
    drafts?.clear(ratingKey(trip));
    ratingMessages[trip.dispatch_trip] = __("Your rating has been sent, thank you.");
  } catch (reason) {
    emit("error", reason);
  } finally {
    busy.value = "";
  }
}
</script>

<template>
  <details v-if="trips.length" class="journey-history">
    <summary>
      {{ __("Past trips") }}
      <span>{{ trips.length }}</span>
    </summary>
    <article v-for="trip in trips" :key="trip.transport_request" class="journey-history__row">
      <div>
        <strong>{{ trip.destination?.location || trip.pickup_point || __("Masar trip") }}</strong>
        <bdi>{{ dateTimeLabel(trip.pickup_datetime) }}</bdi>
        <Badge :label="workerTransportStatusLabel(trip.trip_status)" />
      </div>
      <form
        v-if="trip.dispatch_trip && trip.trip_status === 'Completed' && !trip.has_rated"
        class="journey-rating"
        @submit.prevent="rateTrip(trip)"
      >
        <fieldset>
          <legend>{{ __("Rate the trip") }}</legend>
          <div class="journey-rating__stars">
            <button
              v-for="score in 5"
              :key="score"
              type="button"
              :aria-label="__('{0} stars', [score])"
              :aria-pressed="ratingDraft(trip).rating === score"
              @click="setRating(trip, score)"
            >★</button>
          </div>
        </fieldset>
        <FormControl
          type="textarea"
          :label="__('Optional notes')"
          :model-value="ratingDraft(trip).feedback"
          :data-rating-feedback="trip.dispatch_trip"
          maxlength="2000"
          :rows="2"
          @update:model-value="setRatingFeedback(trip, $event)"
        />
        <!-- The stars are a row of unlabelled buttons, so an untouched rating reads as an optional
             flourish rather than the thing holding the submit shut. -->
        <p v-if="!ratingDraft(trip).rating" class="journey-hint">{{ __("Choose a star rating first to send the rating.") }}</p>
        <Button
          type="button"
          variant="outline"
          :disabled="!ratingDraft(trip).rating"
          :loading="busy === `rating:${trip.dispatch_trip}`"
          :data-rating-submit="trip.dispatch_trip"
          @click="rateTrip(trip)"
        >{{ __("Send rating") }}</Button>
        <Button
          type="button"
          variant="ghost"
          :data-rating-dismiss="trip.dispatch_trip"
          @click="dismissRating(trip)"
        >{{ __("Discard draft") }}</Button>
      </form>
      <p v-else-if="trip.has_rated || ratingMessages[trip.dispatch_trip]" class="journey-rating__thanks" role="status">
        {{ ratingMessages[trip.dispatch_trip] || __("Your rating has already been sent.") }}
      </p>
    </article>
  </details>
</template>
