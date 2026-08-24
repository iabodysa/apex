<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Button } from "frappe-ui";
import { __ } from "../../core/i18n.js";

const LANGUAGES = Object.freeze([
  { code: "ar", label: "العربية" },
  { code: "en", label: "English" },
]);

const HIGHLIGHTS = Object.freeze([
  { icon: "lucide-home", title: __("Today's trip"), body: __("See your trip, its time and its stops as soon as you open the app.") },
  { icon: "lucide-navigation", title: __("Trip Execution"), body: __("Start the trip, mark every stop you reach, and end it from the same screen.") },
  { icon: "lucide-user", title: __("Your info"), body: __("Your housing, custody and requests are all with you without checking with anyone.") },
]);

const STEPS = 5;

const router = useRouter();
const driver = inject("driverGateway");
const push = inject("portalPush", null);

const step = ref(0);
const language = ref("ar");
const busy = ref(false);
const installEvent = ref(null);

const isIos = computed(() => /iphone|ipad|ipod/i.test(globalThis.navigator?.userAgent || ""));

function captureInstall(event) {
  event.preventDefault();
  installEvent.value = event;
}

onMounted(() => globalThis.window?.addEventListener("beforeinstallprompt", captureInstall));
onBeforeUnmount(() => globalThis.window?.removeEventListener("beforeinstallprompt", captureInstall));

async function chooseLanguage(code) {
  language.value = code;
  busy.value = true;
  try {
    await driver.chooseLanguage(code);
    step.value += 1;
  } finally {
    busy.value = false;
  }
}

async function enablePush() {
  await push?.enable?.();
  step.value += 1;
}

async function promptInstall() {
  const event = installEvent.value;
  installEvent.value = null;
  event.prompt();
  await event.userChoice.catch(() => {});
}

async function finish() {
  busy.value = true;
  try {
    await driver.finishOnboarding();
  } finally {
    busy.value = false;
  }
  await router.replace("/today");
  globalThis.location?.reload();
}
</script>

<template>
  <section class="journey-page journey-section" aria-live="polite">
    <ol class="welcome-track" aria-hidden="true">
      <li v-for="index in STEPS" :key="index" :class="{ 'is-done': index <= step + 1 }" />
    </ol>

    <div class="journey-card">
      <div v-if="step === 0" class="journey-card__main">
        <span class="welcome-seal lucide-shield-check" aria-hidden="true" />
        <h3>{{ __("Your device is verified") }}</h3>
        <p>{{ __("We linked this phone to your name. You won't need a link again, nor a username or password.") }}</p>
      </div>

      <div v-else-if="step === 1" class="journey-card__main">
        <h3>{{ __("What you can do in it") }}</h3>
        <p v-for="item in HIGHLIGHTS" :key="item.title">
          <span :class="item.icon" aria-hidden="true" /> <strong>{{ item.title }}</strong> — {{ item.body }}
        </p>
      </div>

      <div v-else-if="step === 2" class="journey-card__main">
        <h3>{{ __("Choose your language") }}</h3>
        <p>{{ __("You can change it later from your profile.") }}</p>
      </div>

      <div v-else-if="step === 3" class="journey-card__main">
        <span class="welcome-seal lucide-bell" aria-hidden="true" />
        <h3>{{ __("Let the alert reach you") }}</h3>
        <p>{{ __("We send you an alert as soon as a trip is assigned to you or its time changes, even while the app is closed.") }}</p>
        <p v-if="push?.error?.value" class="journey-hint">{{ push.error.value }}</p>
      </div>

      <div v-else class="journey-card__main">
        <span class="welcome-seal lucide-download" aria-hidden="true" />
        <h3>{{ __("Install it on your phone") }}</h3>
        <p v-if="isIos">{{ __('Tap the share button below, then "Add to Home Screen".') }}</p>
        <p v-else>{{ __("Install it so it opens like any app, without a browser.") }}</p>
      </div>

      <div class="journey-actions">
        <template v-if="step === 2">
          <Button
            v-for="option in LANGUAGES"
            :key="option.code"
            :theme="language === option.code ? 'green' : 'gray'"
            variant="solid"
            :loading="busy"
            @click="chooseLanguage(option.code)"
          >
            {{ option.label }}
          </Button>
        </template>
        <template v-else-if="step === 3">
          <Button v-if="push?.canOffer?.value" theme="green" variant="solid" :loading="push?.busy?.value" @click="enablePush">
            {{ __("Enable alerts") }}
          </Button>
          <Button variant="subtle" @click="step += 1">{{ __("Later") }}</Button>
        </template>
        <template v-else-if="step === 4">
          <Button v-if="installEvent" theme="green" variant="solid" @click="promptInstall">{{ __("Install now") }}</Button>
          <Button theme="green" variant="solid" :loading="busy" @click="finish">{{ __("Start") }}</Button>
        </template>
        <Button v-else theme="green" variant="solid" @click="step += 1">{{ __("Continue") }}</Button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.welcome-track {
  display: flex;
  gap: var(--sp-1);
  padding: 0;
  margin: 0;
  list-style: none;
}

.welcome-track li {
  flex: 1;
  block-size: 4px;
  border-radius: 999px;
  background: var(--border);
}

.welcome-track li.is-done {
  background: var(--brand-green);
}

.welcome-seal {
  font-size: 2.25rem;
  color: var(--accent-ink);
}
</style>
