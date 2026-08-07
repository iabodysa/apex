<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="trip-rating card card-pad" :dir="dir">
    <div v-if="success" class="text-center py-4 space-y-2">
      <Icon name="check-circle" :size="32" class="mx-auto text-success" />
      <h3 class="font-bold text-success">{{ t("tripRating.success") }}</h3>
    </div>
    <div v-else-if="hasRated" class="text-center py-4 space-y-2 text-muted">
      <Icon name="check-circle" :size="24" class="mx-auto" />
      <p class="text-sm">{{ t("tripRating.alreadyRated") }}</p>
    </div>
    <form v-else @submit.prevent="submitRating" class="space-y-4">
      <h3 class="font-bold leading-tight">{{ t("tripRating.title") }}</h3>

      <div class="flex items-center justify-between gap-1">
        <button
          v-for="star in 5"
          :key="star"
          type="button"
          class="rating-star"
          :class="rating >= star ? 'star-on' : 'star-off'"
          @click="setRating(star)"
          :aria-label="t('tripRating.star' + star)"
        >
          <svg class="w-8 h-8 md:w-10 md:h-10" fill="currentColor" viewBox="0 0 20 20">
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path>
          </svg>
        </button>
      </div>

      <div v-if="rating > 0">
        <textarea
          v-model="feedback"
          class="input w-full resize-none text-sm"
          rows="2"
          :placeholder="t('tripRating.feedbackPlaceholder')"
        ></textarea>
        <p v-if="errorMessage" class="text-sm text-danger mt-2" role="alert">
          {{ errorMessage }}
        </p>
        <button
          type="submit"
          class="btn btn-primary w-full mt-3"
          :disabled="submitting"
        >
          {{ t("tripRating.submit") }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { createResource } from "frappe-ui";
import { useI18n, resourceErrorMessage } from "../i18n";
import Icon from "../components/Icon.vue";

const { t, dir } = useI18n();

const props = defineProps({
  trip: { type: Object, required: true },
});

const emit = defineEmits(["rated"]);

const rating = ref(0);
const feedback = ref("");
const success = ref(false);
const errorMessage = ref("");

const hasRated = ref(props.trip.has_rated || false);

const ratingResource = createResource({
  url: "apex.salis.api.masar.submit_trip_rating",
  onSuccess: () => {
    errorMessage.value = "";
    success.value = true;
    hasRated.value = true;
    emit("rated", rating.value);
  },
  onError: (e) => {
    errorMessage.value = resourceErrorMessage(e, "tripRating.submitFailed");
  },
});

const submitting = computed(() => ratingResource.loading);

function setRating(val) {
  rating.value = val;
}

function submitRating() {
  if (!rating.value) return;
  errorMessage.value = "";
  ratingResource.submit({
    dispatch_trip: props.trip.dispatch_trip,
    transport_request: props.trip.transport_request,
    rating: rating.value,
    feedback: feedback.value,
  });
}
</script>

<style scoped>
.rating-star {
  transition: transform 0.1s ease-in-out, color 0.2s ease;
  flex: 1;
  display: flex;
  justify-content: center;
}
.rating-star:active {
  transform: scale(0.9);
}
@media (hover: hover) {
  .rating-star:hover {
    transform: scale(1.08);
  }
}
.star-on {
  color: var(--c-warning-fill);
}
.star-off {
  color: var(--c-border-strong);
}
.rating-star:focus-visible {
  outline: 2px solid var(--c-primary);
  border-radius: 4px;
}
</style>
