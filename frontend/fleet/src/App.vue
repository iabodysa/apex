<!-- Copyright (c) 2026, AFMCO and contributors -->
<script setup>
/*
 * Fleet EMPLOYEE self-service page — served at the primary /fleet route.
 *
 * A calm, single-purpose page (archetype 1 of the approved reference
 * scratch/portal-archetypes-preview.html): my vehicle status, a fuel-request
 * form, and my recent trips. Built on the shared FleetPageShell (imported by
 * DIRECT path, NOT the @shared/components barrel — the barrel re-exports
 * BuildingPicker, which needs a portal i18n export this portal doesn't provide,
 * so the direct path keeps the fleet bundle clean).
 *
 * The old supervisor board that used to live here is preserved untouched at
 * /fleet-os (bundle fleet_os_portal). This page is LIVE — src/useEmployee.js
 * calls the identity-scoped apex.salis.api.fleet_employee endpoints
 * (get_my_vehicle / get_my_recent_trips / get_fuel_stations /
 * submit_fuel_request).
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import FleetPageShell from "@shared/components/FleetPageShell.vue";
import Icon from "./components/Icon.vue";
// [#a281] Direct path, never the "@shared/components" barrel: a name-import from the
// barrel resolves EVERY component it re-exports (incl. any portal-i18n-coupled one)
// in this portal, which is what broke the A-041 builds. See components/index.js.
import EmptyState from "@shared/components/EmptyState.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import ThemeToggle from "@shared/components/ThemeToggle.vue";
import { useI18n } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { useToast } from "@shared/useToast.js";
import { useEmployee } from "./useEmployee.js";

const { t, lang, dir } = useI18n();

useDocumentLanguage(lang, dir);
watch(
  lang,
  () => {
    document.title = t("emp.brand") + " — " + t("emp.brandSub");
  },
  { immediate: true },
);

const { toast, showToast } = useToast();
const {
  vehicle,
  trips,
  fuelGrades,
  stations,
  form,
  submitting,
  loading,
  loadError,
  reload,
  submitFuelRequest,
} = useEmployee();

/* ---------------------------------------------------------------------------
 * [#emp-nav] Section navigation for this single-scrolling-page archetype.
 *
 * The MOVEMENT is native, not scripted: every nav item is a real in-page anchor
 * (<a href="#trips">), and index.css supplies `scroll-behavior: smooth` plus a
 * `scroll-margin-block-start` that clears the sticky header — so the browser
 * does the scrolling, it still works with JS disabled, it honours
 * prefers-reduced-motion, and `:target` tints the section the reader landed on
 * (the one guaranteed visible change at desktop, where the fuel card shares the
 * grid's top row with the vehicle card and therefore barely moves).
 *
 * Only the ACTIVE HIGHLIGHT needs script. It is a scroll-spy: an
 * IntersectionObserver watching a band just under the header names the section
 * being read. A click pins the highlight to the clicked section until the
 * reader scrolls by hand again — without that pin, clicking "fuel" at desktop
 * would scroll to the shared top row and the spy would snap the highlight back
 * to "vehicle".
 * ------------------------------------------------------------------------- */
const navItems = [
  { id: "vehicle", key: "emp.nav.home" },
  { id: "trips", key: "emp.nav.trips" },
  { id: "fuel", key: "emp.nav.fuel" },
];
const activeSection = ref(navItems[0].id);
// True while an explicit click owns the highlight; released by the next manual
// scroll gesture. A plain flag, not a timer — the release is a real user event.
let pinned = false;

function selectSection(id) {
  if (!navItems.some((n) => n.id === id)) return;
  activeSection.value = id;
  pinned = true;
}
function syncFromHash() {
  // Deep link, reload, or browser back/forward: honour the fragment.
  selectSection(decodeURIComponent(window.location.hash.replace(/^#/, "")));
}
function releasePin() {
  pinned = false;
}

// keydown covers space/arrow/page scrolling; wheel and touchmove cover the rest.
const MANUAL_SCROLL_EVENTS = ["wheel", "touchmove", "keydown"];
let spy = null;

onMounted(() => {
  syncFromHash();
  window.addEventListener("hashchange", syncFromHash);
  MANUAL_SCROLL_EVENTS.forEach((ev) =>
    window.addEventListener(ev, releasePin, { passive: true }),
  );

  const sections = navItems.map((n) => document.getElementById(n.id)).filter(Boolean);
  if (!sections.length || typeof IntersectionObserver === "undefined") return;
  const visible = new Set();
  spy = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) visible.add(e.target.id);
        else visible.delete(e.target.id);
      }
      if (pinned) return;
      // Several sections share the band on the two-column desktop layout;
      // reading order (navItems) breaks the tie deterministically.
      const current = navItems.find((n) => visible.has(n.id));
      if (current) activeSection.value = current.id;
    },
    // Detector band: starts below the sticky header, ends in the upper part of
    // the viewport, so "current" means "at the top of what is being read".
    { rootMargin: "-104px 0px -55% 0px", threshold: 0 },
  );
  sections.forEach((s) => spy.observe(s));
});

onBeforeUnmount(() => {
  if (spy) spy.disconnect();
  window.removeEventListener("hashchange", syncFromHash);
  MANUAL_SCROLL_EVENTS.forEach((ev) => window.removeEventListener(ev, releasePin));
});

const userName = (typeof window !== "undefined" && window.user_full_name) || "";
const avatarInitial = computed(() => Array.from(userName || t("emp.brand"))[0] || "•");

// Time-of-day greeting.
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return t("emp.greetMorning");
  if (h < 18) return t("emp.greetAfternoon");
  return t("emp.greetEvening");
});

// Localized integer formatting: Arabic-Indic digits + separator under `ar`.
// One numeral system on screen. Plain "ar-SA" renders Arabic-Indic digits, but every
// count that reaches the page through a translation placeholder is a raw JS number and
// stays Latin — so a single line read "الأحد، ٢ أغسطس · ... 0 رحلة", two systems in one
// sentence. `-u-nu-latn` pins the Arabic locale to Latin digits, which is what the rest
// of the product already shows.
const AR_LOCALE = "ar-SA-u-nu-latn";

function fmtInt(n) {
  if (n == null) return "—";
  const grouped = new Intl.NumberFormat(lang.value === "ar" ? AR_LOCALE : "en-US").format(n);
  return grouped;
}
const todayLabel = computed(() =>
  new Intl.DateTimeFormat(lang.value === "ar" ? AR_LOCALE : "en-US", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date()),
);
const scheduledCount = computed(() => trips.value.filter((x) => x.status !== "completed").length);
const subtitleText = computed(() => t("emp.subtitle", { date: todayLabel.value, n: scheduledCount.value }));

// Vehicle status → pill class + label (reuses the board's status vocabulary).
const statusMeta = {
  available: { cls: "pill-ok", key: "statusShort.available" },
  assigned: { cls: "pill-ok", key: "statusShort.assigned" },
  workshop: { cls: "pill-warn", key: "statusShort.workshop" },
  stopped: { cls: "pill-neutral", key: "statusShort.stopped" },
  stolen: { cls: "pill-warn", key: "statusShort.stolen" },
};
const vehicleStatus = computed(() => statusMeta[vehicle.status] || statusMeta.available);

const tripMeta = {
  planned: { cls: "pill-warn", key: "emp.trips.planned" },
  inProgress: { cls: "pill-ok", key: "emp.trips.inProgress" },
  completed: { cls: "pill-ok", key: "emp.trips.completed" },
};

// The server's rejection reason names the limit that was exceeded, so it is held
// on the form until the next attempt rather than only flashed in a toast.
const formError = ref("");

async function onSubmit() {
  if (submitting.value) return;
  formError.value = "";
  try {
    const res = await submitFuelRequest();
    if (res && res.ok) showToast(t("emp.fuel.sent"), "green");
  } catch (e) {
    const msg = (e && (e.messages?.[0] || e.message)) || t("emp.fuel.error");
    formError.value = msg;
    showToast(msg, "red");
  }
}
</script>

<template>
  <FleetPageShell :title="greeting" :subtitle="subtitleText" max-width="1120">
    <template #brand>
      <span class="emp-brandmark"><Icon name="car" :size="19" /></span>
      <span class="emp-brandword">
        {{ t("emp.brand") }}
        <small>{{ t("emp.brandSub") }}</small>
      </span>
    </template>

    <!-- Real in-page anchors: the browser scrolls (see [#emp-nav] above), the
         spy-driven `is-active` class marks the section being read. -->
    <template #nav>
      <a
        v-for="item in navItems"
        :key="item.id"
        :href="'#' + item.id"
        :class="{ 'is-active': activeSection === item.id }"
        :aria-current="activeSection === item.id ? 'location' : undefined"
        @click="selectSection(item.id)"
        >{{ t(item.key) }}</a
      >
    </template>

    <template #actions>
      <ThemeToggle />
      <!-- variant="header" tints the control for the forest header bar, matching
           the sibling driver / safety / route_supervisor portals. -->
      <LangToggle variant="header" />
      <span class="emp-avatar" :title="userName || t('emp.brand')" :aria-label="userName || t('emp.brand')">{{ avatarInitial }}</span>
    </template>

    <!-- Greeting subtitle is provided via the `subtitle` prop above; the shell
         renders it under the title. -->

    <div class="emp-grid">
      <!-- LEFT: vehicle + trips -->
      <div class="emp-col">
        <!-- MY VEHICLE -->
        <section id="vehicle" class="emp-card reveal d1">
          <header class="emp-card-head">
            <span class="emp-ic"><Icon name="car" :size="17" /></span>
            <div class="emp-card-titles">
              <h3>{{ t("emp.vehicle.title") }}</h3>
              <p class="emp-hint">{{ t("emp.vehicle.hint") }}</p>
            </div>
          </header>

          <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
          <!-- [#emp-fail] Failure BEFORE the empty state. `vehicle.empty` starts true and
               a broken load never clears it, so without this branch a failed request
               rendered as "no vehicle is assigned to you" — a driver WITH a vehicle was
               told they had none. Also gated on `empty` so a vehicle that did load still
               shows when only a sibling request failed. -->
          <div v-else-if="loadError && vehicle.empty" class="emp-fail">
            <p>{{ t("emp.loadError") }}</p>
            <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="reload">
              <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
            </button>
          </div>
          <EmptyState v-else-if="vehicle.empty" :title="t('emp.vehicle.empty')">
            <template #icon><Icon name="car" :size="20" /></template>
          </EmptyState>
          <template v-else>
            <div class="emp-vehicle-hero">
              <span class="emp-plate">{{ vehicle.plate }}</span>
              <div class="emp-vinfo">
                <b>{{ vehicle.model }}</b>
                <span>{{ vehicle.office }}</span>
              </div>
              <span class="emp-pill" :class="vehicleStatus.cls">
                <span class="dot"></span>{{ t(vehicleStatus.key) }}
              </span>
            </div>

            <div class="emp-kv-row">
              <div class="emp-kv">
                <small>{{ t("emp.vehicle.odometer") }}</small>
                <b class="tnum">{{ fmtInt(vehicle.odometerKm) }} {{ t("emp.vehicle.kmUnit") }}</b>
              </div>
              <div class="emp-kv">
                <small>{{ t("emp.vehicle.registration") }}</small>
                <b>{{ vehicle.registrationExpiry ? t("emp.vehicle.validUntil", { date: vehicle.registrationExpiry }) : t("common.none") }}</b>
              </div>
            </div>
          </template>
        </section>

        <!-- MY TRIPS -->
        <section id="trips" class="emp-card reveal d2">
          <header class="emp-card-head">
            <span class="emp-ic"><Icon name="clipboard-list" :size="17" /></span>
            <div class="emp-card-titles">
              <h3>{{ t("emp.trips.title") }}</h3>
              <p class="emp-hint">{{ t("emp.trips.hint") }}</p>
            </div>
          </header>

          <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
          <!-- Same [#emp-fail] rule: "the trips request broke" is not "you have no trips". -->
          <div v-else-if="loadError && !trips.length" class="emp-fail">
            <p>{{ t("emp.loadError") }}</p>
            <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="reload">
              <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
            </button>
          </div>
          <EmptyState v-else-if="!trips.length" :title="t('emp.trips.empty')">
            <template #icon><Icon name="clipboard-list" :size="20" /></template>
          </EmptyState>
          <ul v-else class="emp-trips">
            <li v-for="trip in trips" :key="trip.id" class="emp-trip">
              <span class="emp-pill" :class="(tripMeta[trip.status] || tripMeta.planned).cls">
                <span class="dot"></span>{{ t((tripMeta[trip.status] || tripMeta.planned).key) }}
              </span>
              <div class="emp-route">
                <b>{{ trip.title }}</b>
                <span>
                  <template v-if="trip.date">{{ trip.date }}</template>
                  <template v-if="trip.when"> · {{ trip.when }}</template>
                  <template v-if="trip.distanceKm"> · {{ t("emp.trips.distance", { n: fmtInt(trip.distanceKm) }) }}</template>
                </span>
              </div>
              <span class="emp-arrow"><Icon name="chevron" :size="17" /></span>
            </li>
          </ul>
        </section>
      </div>

      <!-- RIGHT: fuel request -->
      <section id="fuel" class="emp-card emp-form-card reveal d3">
        <header class="emp-card-head">
          <span class="emp-ic"><Icon name="fuel" :size="17" /></span>
          <div class="emp-card-titles">
            <h3>{{ t("emp.fuel.title") }}</h3>
            <p class="emp-hint">{{ t("emp.fuel.hint") }}</p>
          </div>
        </header>

        <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
        <!-- Same [#emp-fail] rule as the two cards on the left: a broken stations
             load must not render a silently empty select. Gated on the list being
             empty, so stations that did load keep the form usable when only a
             sibling request failed. -->
        <div v-else-if="loadError && !stations.length" class="emp-fail">
          <p>{{ t("emp.loadError") }}</p>
          <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="reload">
            <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
          </button>
        </div>
        <form v-else @submit.prevent="onSubmit">
          <div class="emp-field">
            <label for="ff-grade">{{ t("emp.fuel.fuelType") }}</label>
            <div class="emp-select-wrap">
              <select id="ff-grade" v-model="form.fuelGrade" class="emp-control">
                <option v-for="g in fuelGrades" :key="g" :value="g">{{ t("fuelGrade." + g) }}</option>
              </select>
              <Icon class="emp-select-caret" name="chevron" :size="15" />
            </div>
          </div>

          <div class="emp-field">
            <label for="ff-litres">{{ t("emp.fuel.quantity") }}</label>
            <div class="emp-control emp-control-num">
              <input id="ff-litres" v-model.number="form.litres" type="number" min="1" step="1" inputmode="numeric" />
              <span class="emp-unit">{{ t("emp.fuel.litresUnit") }}</span>
            </div>
          </div>

          <div class="emp-field">
            <label for="ff-station">{{ t("emp.fuel.station") }}</label>
            <div class="emp-select-wrap">
              <select id="ff-station" v-model="form.station" class="emp-control">
                <option v-for="s in stations" :key="s" :value="s">{{ s }}</option>
              </select>
              <Icon class="emp-select-caret" name="chevron" :size="15" />
            </div>
          </div>

          <div class="emp-field">
            <label for="ff-notes">{{ t("emp.fuel.notes") }}</label>
            <textarea
              id="ff-notes"
              v-model="form.notes"
              class="emp-control emp-textarea"
              rows="2"
              :placeholder="t('emp.fuel.notesPlaceholder')"
            ></textarea>
          </div>

          <!-- The rejection reason names a limit the employee has to act on, so it
               stays on the form next to the field that caused it. The toast alone
               took it away after three seconds. -->
          <p v-if="formError" id="ff-error" class="emp-form-error" role="alert">
            <Icon name="triangle-alert" :size="15" />
            {{ formError }}
          </p>

          <!-- No "Save as draft" here. The control that used to sit below this one
               raised a "Saved as a draft" toast and made no call at all, so a
               request the employee believed was kept was silently discarded. A
               draft needs somewhere to be stored before it can be offered. -->
          <button
            type="submit"
            class="emp-btn emp-btn-primary"
            :disabled="submitting"
            :aria-describedby="formError ? 'ff-error' : undefined"
          >
            <Icon v-if="!submitting" name="rotate-cw" :size="17" />
            {{ submitting ? t("emp.fuel.sending") : t("emp.fuel.submit") }}
          </button>
        </form>
      </section>
    </div>
  </FleetPageShell>

  <!-- TOAST -->
  <div class="toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]">{{ toast.msg }}</div>
</template>
