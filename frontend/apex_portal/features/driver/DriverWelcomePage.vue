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

const router = useRouter();
const driver = inject("driverGateway");
const push = inject("portalPush", null);

const step = ref(0);
const language = ref("ar");
const busy = ref(false);
const installEvent = ref(null);

const steps = computed(() => ["الجهاز", "التطبيق", "اللغة", "التنبيهات", "التثبيت"]);
const isLast = computed(() => step.value === steps.value.length - 1);
const canOfferPush = computed(() => Boolean(push?.canOffer?.value));
const canPromptInstall = computed(() => Boolean(installEvent.value));
const isIos = computed(() =>
  /iphone|ipad|ipod/i.test(globalThis.navigator?.userAgent || ""),
);

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
  } catch {
    busy.value = false;
    return;
  }
  busy.value = false;
  step.value += 1;
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
  <section class="driver-welcome" aria-live="polite">
    <ol class="driver-welcome__track" aria-hidden="true">
      <li v-for="(label, index) in steps" :key="label" :class="{ 'is-done': index <= step }" />
    </ol>

    <template v-if="step === 0">
      <span class="driver-welcome__seal lucide-shield-check" aria-hidden="true" />
      <h1>جهازك صار موثّق</h1>
      <p>ربطنا هذا الجوال باسمك. ما تحتاج رابط مرة ثانية، ولا اسم مستخدم ولا كلمة مرور.</p>
      <Button theme="green" variant="solid" @click="step += 1">تمام، كمّل</Button>
    </template>

    <template v-else-if="step === 1">
      <h1>وش تسوي فيه</h1>
      <ul class="driver-welcome__highlights">
        <li v-for="item in HIGHLIGHTS" :key="item.title">
          <span :class="item.icon" aria-hidden="true" />
          <div>
            <strong>{{ item.title }}</strong>
            <p>{{ item.body }}</p>
          </div>
        </li>
      </ul>
      <Button theme="green" variant="solid" @click="step += 1">كمّل</Button>
    </template>

    <template v-else-if="step === 2">
      <h1>اختر لغتك</h1>
      <p>تقدر تغيّرها بعدين من بياناتك.</p>
      <div class="driver-welcome__languages">
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
      </div>
    </template>

    <template v-else-if="step === 3">
      <span class="driver-welcome__seal lucide-bell" aria-hidden="true" />
      <h1>خلّ التنبيه يوصلك</h1>
      <p>نرسل لك تنبيه أول ما تنسند لك رحلة أو يتغيّر وقتها، حتى والتطبيق مقفل.</p>
      <p v-if="push?.error?.value" class="driver-welcome__warn">{{ push.error.value }}</p>
      <Button v-if="canOfferPush" theme="green" variant="solid" :loading="push?.busy?.value" @click="enablePush">
        فعّل التنبيهات
      </Button>
      <Button variant="subtle" @click="step += 1">بعدين</Button>
    </template>

    <template v-else>
      <span class="driver-welcome__seal lucide-download" aria-hidden="true" />
      <h1>ثبّته على جوالك</h1>
      <p v-if="isIos">اضغط زر المشاركة تحت، ثم «أضف إلى الشاشة الرئيسية».</p>
      <p v-else>ثبّته عشان يفتح مثل أي تطبيق، بدون متصفح.</p>
      <Button v-if="canPromptInstall" theme="green" variant="solid" @click="promptInstall">ثبّت الآن</Button>
      <Button theme="green" variant="solid" :loading="busy" @click="finish">ابدأ</Button>
    </template>
  </section>
</template>

<style scoped>
.driver-welcome {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: flex-start;
  padding: 1.5rem 1.25rem 2.5rem;
  min-height: 100%;
}

.driver-welcome__track {
  display: flex;
  gap: 0.375rem;
  width: 100%;
  padding: 0;
  margin: 0 0 0.5rem;
  list-style: none;
}

.driver-welcome__track li {
  flex: 1;
  height: 0.25rem;
  border-radius: 999px;
  background: var(--apex-surface-sunken, #e5e7eb);
}

.driver-welcome__track li.is-done {
  background: var(--apex-brand, #00844e);
}

.driver-welcome__seal {
  font-size: 2.5rem;
  color: var(--apex-brand, #00844e);
}

.driver-welcome h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.driver-welcome p {
  margin: 0;
  color: var(--apex-text-muted, #4b5563);
  line-height: 1.7;
}

.driver-welcome__warn {
  color: var(--apex-danger, #b91c1c);
}

.driver-welcome__highlights {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 0;
  margin: 0;
  list-style: none;
  width: 100%;
}

.driver-welcome__highlights li {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
}

.driver-welcome__highlights span {
  font-size: 1.25rem;
  color: var(--apex-brand, #00844e);
}

.driver-welcome__highlights strong {
  display: block;
  margin-bottom: 0.125rem;
}

.driver-welcome__languages {
  display: flex;
  gap: 0.75rem;
  width: 100%;
}
</style>
