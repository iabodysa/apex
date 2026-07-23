// Copyright (c) 2026, AFMCO and contributors
// Mirrors worker_portal/src/i18n.js: a tiny EN/AR dictionary with the same
// translate / setLang / dir / useI18n machinery and a shared resource-error
// mapper. Arabic strings live here, which is allowed for *_portal bundles.
import { createI18n } from "@shared/i18n";

const STORAGE_KEY = "safety_portal_lang";
export const SUPPORTED = ["en", "ar"];

const messages = {
  en: {
    common: {
      loading: "Loading…",
      retry: "Retry",
      none: "—",
      error: "Something went wrong.",
      appName: "Safety Rounds",
      submit: "Submit",
      cancel: "Cancel",
      note: "Note",
      back: "Back",
      change: "Change",
    },
    lang: {
      label: "Language",
      en: "EN",
      ar: "ع",
      english: "English",
      arabic: "العربية",
    },
    greeting: {
      morning: "Good morning",
      afternoon: "Good afternoon",
      evening: "Good evening",
      eyebrow: "Safety walkthrough",
    },
    building: {
      title: "Choose a building",
      subtitle: "Pick the building you are inspecting today.",
      search: "Search buildings",
      empty: "No buildings available for your account.",
      current: "Inspecting",
      start: "Start the round",
    },
    due: {
      title: "Due today",
      subtitle: "Tap each task to mark it, then submit.",
      rated: "rated",
      of: "of",
      tasksDone: "{done} / {total}",
      period: "Period",
      pass: "Pass",
      fail: "Fail",
      issue: "Issue",
      addNote: "Add a note",
      notePlaceholder: "What did you find?",
      instructions: "How to check",
      evidence: "Evidence required",
      priority: "Priority",
      progress: "{done} of {total} rated",
      allRated: "All tasks rated",
      someLeft: "{n} left to rate",
    },
    submit: {
      cta: "Submit & email the manager",
      sending: "Submitting…",
      hint: "A report is emailed to the manager on submit.",
      needOne: "Rate at least one task to submit.",
    },
    success: {
      title: "Round submitted",
      subtitle: "The safety report has been emailed to the manager.",
      emailed: "Report emailed to the manager",
      notEmailed: "Saved. The email could not be sent.",
      results: "Results by cadence",
      done: "Done",
      another: "Start another building",
    },
    empty: {
      title: "All safety rounds are up to date",
      subtitle: "Nothing is due for this building right now. Great work.",
      switch: "Check another building",
    },
    result: {
      Pass: "Pass",
      "Needs Attention": "Needs attention",
      Fail: "Fail",
    },
    priority: {
      Low: "Low",
      Medium: "Medium",
      High: "High",
      Critical: "Critical",
    },
    cadence: {
      Daily: "Daily",
      Weekly: "Weekly",
      Monthly: "Monthly",
      Quarterly: "Quarterly",
      Annual: "Annual",
    },
    errors: {
      loadFailed: "Couldn't load safety rounds",
      loadError: "Couldn't load this section.",
      submitFailed: "Couldn't submit the round.",
      noBuilding: "Select a building to continue.",
      rateLimited: "Too many requests. Please wait a moment and try again.",
      sessionExpired: "Your session expired. Please refresh the page.",
    },
  },
  ar: {
    common: {
      loading: "جارٍ التحميل…",
      retry: "إعادة المحاولة",
      none: "—",
      error: "حدث خطأ ما.",
      appName: "جولات السلامة",
      submit: "إرسال",
      cancel: "إلغاء",
      note: "ملاحظة",
      back: "رجوع",
      change: "تغيير",
    },
    lang: {
      label: "اللغة",
      en: "EN",
      ar: "ع",
      english: "English",
      arabic: "العربية",
    },
    greeting: {
      morning: "صباح الخير",
      afternoon: "مساء الخير",
      evening: "مساء الخير",
      eyebrow: "جولة السلامة",
    },
    building: {
      title: "اختر المبنى",
      subtitle: "اختر المبنى الذي تقوم بتفتيشه اليوم.",
      search: "ابحث عن مبنى",
      empty: "لا توجد مبانٍ متاحة لحسابك.",
      current: "قيد التفتيش",
      start: "ابدأ الجولة",
    },
    due: {
      title: "المستحق اليوم",
      subtitle: "اضغط على كل مهمة لتقييمها ثم أرسل.",
      rated: "مُقيَّم",
      of: "من",
      tasksDone: "{done} / {total}",
      period: "الفترة",
      pass: "ناجح",
      fail: "غير منجز",
      issue: "ملاحظة",
      addNote: "أضف ملاحظة",
      notePlaceholder: "ماذا وجدت؟",
      instructions: "طريقة الفحص",
      evidence: "إثبات مطلوب",
      priority: "الأولوية",
      progress: "تم تقييم {done} من {total}",
      allRated: "تم تقييم كل المهام",
      someLeft: "بقي {n} للتقييم",
    },
    submit: {
      cta: "إرسال وإرسال بريد للمدير",
      sending: "جارٍ الإرسال…",
      hint: "يُرسَل تقرير للمدير عند الإرسال.",
      needOne: "قيّم مهمة واحدة على الأقل للإرسال.",
    },
    success: {
      title: "تم إرسال الجولة",
      subtitle: "تم إرسال تقرير السلامة إلى المدير عبر البريد.",
      emailed: "تم إرسال التقرير إلى المدير",
      notEmailed: "تم الحفظ. تعذّر إرسال البريد.",
      results: "النتائج حسب الدورية",
      done: "تم",
      another: "ابدأ مبنى آخر",
    },
    empty: {
      title: "جميع جولات السلامة محدّثة",
      subtitle: "لا يوجد مستحق لهذا المبنى حالياً. عمل رائع.",
      switch: "افحص مبنى آخر",
    },
    result: {
      Pass: "ناجح",
      "Needs Attention": "يحتاج إلى انتباه",
      Fail: "غير منجز",
    },
    priority: {
      Low: "منخفضة",
      Medium: "متوسطة",
      High: "عالية",
      Critical: "حرجة",
    },
    cadence: {
      Daily: "يومي",
      Weekly: "أسبوعي",
      Monthly: "شهري",
      Quarterly: "ربع سنوي",
      Annual: "سنوي",
    },
    errors: {
      loadFailed: "تعذّر تحميل جولات السلامة",
      loadError: "تعذّر تحميل هذا القسم.",
      submitFailed: "تعذّر إرسال الجولة.",
      noBuilding: "اختر مبنى للمتابعة.",
      rateLimited: "طلبات كثيرة جداً. يرجى الانتظار قليلاً ثم المحاولة مرة أخرى.",
      sessionExpired: "انتهت صلاحية الجلسة. يرجى تحديث الصفحة.",
    },
  },
};

// Server-driven enum display: the period_label the backend returns for Monthly /
// Quarterly / Annual ("June 2026", "Q2 2026", "2026") is rendered verbatim, so
// no hand-maintained month/quarter map can drift from it.
export function translateEnum(namespace, value) {
  if (value == null || value === "") return value;
  const map = lookup(lang.value, namespace);
  return (map && map[value]) || value;
}

// Shared translate / setLang / dir / resource-error machinery. Supervisors on
// site default to Arabic. translateEnum stays local (reads namespaces from the
// messages dict via the factory's lookup).
const { lang, dir, lookup, translate, setLang, resourceErrorMessage } = createI18n({
  messages,
  storageKey: STORAGE_KEY,
  supported: SUPPORTED,
});

export { translate, setLang, resourceErrorMessage };

export function useI18n() {
  return {
    t: (key, params) => translate(key, params),
    tEnum: (namespace, value) => translateEnum(namespace, value),
    lang,
    dir,
    setLang,
  };
}
