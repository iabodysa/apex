<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Button } from "frappe-ui";

const LANGUAGES = Object.freeze([
  { code: "ar", label: "العربية" },
  { code: "en", label: "English" },
]);

const HIGHLIGHTS = Object.freeze([
  { icon: "lucide-home", title: "رحلة اليوم", body: "تشوف رحلتك ووقتها ومحطاتها أول ما تفتح التطبيق." },
  { icon: "lucide-navigation", title: "تنفيذ الرحلة", body: "تبدأ الرحلة، وتعلّم كل محطة وصلتها، وتنهيها من نفس الشاشة." },
  { icon: "lucide-user", title: "بياناتك", body: "سكنك وعهدك وطلباتك كلها معك بدون ما تراجع أحد." },
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
        <h3>جهازك صار موثّق</h3>
        <p>ربطنا هذا الجوال باسمك. ما تحتاج رابط مرة ثانية، ولا اسم مستخدم ولا كلمة مرور.</p>
      </div>

      <div v-else-if="step === 1" class="journey-card__main">
        <h3>وش تسوي فيه</h3>
        <p v-for="item in HIGHLIGHTS" :key="item.title">
          <span :class="item.icon" aria-hidden="true" /> <strong>{{ item.title }}</strong> — {{ item.body }}
        </p>
      </div>

      <div v-else-if="step === 2" class="journey-card__main">
        <h3>اختر لغتك</h3>
        <p>تقدر تغيّرها بعدين من بياناتك.</p>
      </div>

      <div v-else-if="step === 3" class="journey-card__main">
        <span class="welcome-seal lucide-bell" aria-hidden="true" />
        <h3>خلّ التنبيه يوصلك</h3>
        <p>نرسل لك تنبيه أول ما تنسند لك رحلة أو يتغيّر وقتها، حتى والتطبيق مقفل.</p>
        <p v-if="push?.error?.value" class="journey-hint">{{ push.error.value }}</p>
      </div>

      <div v-else class="journey-card__main">
        <span class="welcome-seal lucide-download" aria-hidden="true" />
        <h3>ثبّته على جوالك</h3>
        <p v-if="isIos">اضغط زر المشاركة تحت، ثم «أضف إلى الشاشة الرئيسية».</p>
        <p v-else>ثبّته عشان يفتح مثل أي تطبيق، بدون متصفح.</p>
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
            فعّل التنبيهات
          </Button>
          <Button variant="subtle" @click="step += 1">بعدين</Button>
        </template>
        <template v-else-if="step === 4">
          <Button v-if="installEvent" theme="green" variant="solid" @click="promptInstall">ثبّت الآن</Button>
          <Button theme="green" variant="solid" :loading="busy" @click="finish">ابدأ</Button>
        </template>
        <Button v-else theme="green" variant="solid" @click="step += 1">كمّل</Button>
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
