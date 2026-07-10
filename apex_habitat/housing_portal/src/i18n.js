// Copyright (c) 2026, AFMCO and contributors
// Mirrors safety_portal/src/i18n.js: a tiny EN/AR dictionary with the same
// translate / setLang / dir / useI18n machinery and a shared resource-error
// mapper. Arabic strings live here, which is allowed for *_portal bundles.
import { createI18n } from "@shared/i18n";

const STORAGE_KEY = "housing_portal_lang";
export const SUPPORTED = ["en", "ar"];

const messages = {
  en: {
    common: {
      loading: "Loading…",
      retry: "Retry",
      none: "—",
      error: "Something went wrong.",
      appName: "Inventory Count",
      submit: "Submit",
      cancel: "Cancel",
      confirm: "Confirm",
      note: "Note",
      back: "Back",
      change: "Change",
      refresh: "Refresh List",
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
      eyebrow: "Housing inventory count",
    },
    building: {
      title: "Choose a building",
      subtitle: "Pick the building you are counting today.",
      search: "Search buildings",
      empty: "No buildings available for your account.",
    },
    list: {
      title: "Items to count",
      subtitle: "Count each item, set its condition, then submit.",
      empty: "No inventory items for this building.",
      filterAll: "All items",
      filterNeedsCount: "Needs count / variance",
      noRoom: "No specific room",
      count: "{n} items",
      countedToday: "Counted today",
      lastCount: "Last counted {date}",
      neverCounted: "Never counted",
    },
    card: {
      expected: "Expected",
      counted: "Counted",
      variance: "Variance",
      varianceHint: "Counted minus expected (set by the system).",
      condition: "Condition",
      notePlaceholder: "Anything to note?",
      decrease: "Decrease",
      increase: "Increase",
    },
    submit: {
      cta: "Submit counts",
      sending: "Submitting…",
      hint: "Each counted item is saved and its variance recalculated.",
      needOne: "Count at least one item to submit.",
    },
    success: {
      title: "Counts submitted",
      subtitle: "The inventory counts were saved.",
      saved: "{n} items updated",
      partial: "{ok} saved, {failed} could not be saved",
      results: "Variance after count",
      shortage: "Shortage",
      surplus: "Surplus",
      balanced: "Balanced",
      done: "Done",
      another: "Count another building",
    },
    empty: {
      title: "Nothing to count here",
      subtitle: "There are no inventory items for this building right now.",
      switch: "Check another building",
    },
    condition: {
      New: "New",
      Good: "Good",
      Fair: "Fair",
      "Needs Maintenance": "Needs maintenance",
      Damaged: "Damaged",
      Missing: "Missing",
    },
    category: {
      Furniture: "Furniture",
      Appliance: "Appliance",
      "Bedding & Linen": "Bedding & Linen",
      Kitchenware: "Kitchenware",
      "Electrical Fixture": "Electrical Fixture",
      "Cleaning Equipment": "Cleaning Equipment",
      "Safety Equipment": "Safety Equipment",
      Other: "Other",
    },
    nav: {
      count: "Inventory Count",
      delivery: "Asset Delivery",
    },
    delivery: {
      title: "Asset Delivery",
      subtitle: "Clear exit checkpoints and confirm on-site receipt for assets in transit",
      emptyTitle: "All Caught Up",
      emptySubtitle: "There are no asset deliveries awaiting your action.",
      from: "From",
      to: "To",
      asset: "Asset",
      enterOtp: "Enter 6-digit confirmation code",
      confirmReceipt: "Confirm Receipt",
      awaitingExits: "Awaiting exit clearance",
      readyToReceive: "Ready to receive",
      exit1: "Security / Gate",
      exit2: "Logistics / Dispatch",
      exit3: "Receiving Acceptance",
      exitStep: "Checkpoint {n} of 3",
      clearCheckpoint: "Clear {label}",
      exitCleared: "Checkpoint cleared.",
      confirmed: "Receipt confirmed — asset delivered.",
    },
    errors: {
      loadFailed: "Couldn't load the inventory",
      loadError: "Couldn't load this section.",
      submitFailed: "Couldn't submit the counts.",
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
      appName: "جرد المخزون",
      submit: "إرسال",
      cancel: "إلغاء",
      confirm: "تأكيد",
      note: "ملاحظة",
      back: "رجوع",
      change: "تغيير",
      refresh: "تحديث القائمة",
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
      eyebrow: "جرد مخزون السكن",
    },
    building: {
      title: "اختر المبنى",
      subtitle: "اختر المبنى الذي تقوم بجرده اليوم.",
      search: "ابحث عن مبنى",
      empty: "لا توجد مبانٍ متاحة لحسابك.",
    },
    list: {
      title: "أصناف للجرد",
      subtitle: "اجرد كل صنف، حدّد حالته، ثم أرسل.",
      empty: "لا توجد أصناف مخزون لهذا المبنى.",
      filterAll: "كل الأصناف",
      filterNeedsCount: "بحاجة للجرد / فرق",
      noRoom: "بدون غرفة محددة",
      count: "{n} صنف",
      countedToday: "تم الجرد اليوم",
      lastCount: "آخر جرد {date}",
      neverCounted: "لم يُجرد بعد",
    },
    card: {
      expected: "المتوقع",
      counted: "المجرود",
      variance: "الفرق",
      varianceHint: "المجرود ناقص المتوقع (يحسبه النظام).",
      condition: "الحالة",
      notePlaceholder: "هل من ملاحظة؟",
      decrease: "إنقاص",
      increase: "زيادة",
    },
    submit: {
      cta: "إرسال الجرد",
      sending: "جارٍ الإرسال…",
      hint: "يُحفظ كل صنف مجرود ويُعاد احتساب الفرق.",
      needOne: "اجرد صنفاً واحداً على الأقل للإرسال.",
    },
    success: {
      title: "تم إرسال الجرد",
      subtitle: "تم حفظ نتائج الجرد.",
      saved: "تم تحديث {n} صنف",
      partial: "تم حفظ {ok}، وتعذّر حفظ {failed}",
      results: "الفرق بعد الجرد",
      shortage: "نقص",
      surplus: "زيادة",
      balanced: "متوازن",
      done: "تم",
      another: "اجرد مبنى آخر",
    },
    empty: {
      title: "لا يوجد ما يُجرد هنا",
      subtitle: "لا توجد أصناف مخزون لهذا المبنى حالياً.",
      switch: "افحص مبنى آخر",
    },
    condition: {
      New: "جديد",
      Good: "جيد",
      Fair: "مقبول",
      "Needs Maintenance": "يحتاج صيانة",
      Damaged: "تالف",
      Missing: "مفقود",
    },
    category: {
      Furniture: "أثاث",
      Appliance: "جهاز",
      "Bedding & Linen": "مفروشات وأغطية",
      Kitchenware: "أدوات مطبخ",
      "Electrical Fixture": "تجهيزات كهربائية",
      "Cleaning Equipment": "معدات تنظيف",
      "Safety Equipment": "معدات سلامة",
      Other: "أخرى",
    },
    nav: {
      count: "جرد السكن",
      delivery: "تسليم الأصول",
    },
    delivery: {
      title: "تسليم الأصول",
      subtitle: "خلّص نقاط الخروج وأكّد الاستلام الميداني للأصول قيد النقل",
      emptyTitle: "لا توجد مهام",
      emptySubtitle: "لا توجد عمليات نقل أصول بانتظار إجراء منك.",
      from: "من",
      to: "إلى",
      asset: "الأصل",
      enterOtp: "أدخل رمز التأكيد المكون من 6 أرقام",
      confirmReceipt: "تأكيد الاستلام",
      awaitingExits: "بانتظار تخليص المخارج",
      readyToReceive: "جاهز للاستلام",
      exit1: "الأمن / البوابة",
      exit2: "اللوجستيات / الإرسال",
      exit3: "قبول الاستلام",
      exitStep: "المرحلة {n} من 3",
      clearCheckpoint: "تخليص {label}",
      exitCleared: "تم تخليص المرحلة.",
      confirmed: "تم تأكيد الاستلام — تم تسليم الأصل.",
    },
    errors: {
      loadFailed: "تعذّر تحميل المخزون",
      loadError: "تعذّر تحميل هذا القسم.",
      submitFailed: "تعذّر إرسال الجرد.",
      noBuilding: "اختر مبنى للمتابعة.",
      rateLimited: "طلبات كثيرة جداً. يرجى الانتظار قليلاً ثم المحاولة مرة أخرى.",
      sessionExpired: "انتهت صلاحية الجلسة. يرجى تحديث الصفحة.",
    },
  },
};

// Server-driven enum display: a Select value the backend returns (condition,
// category) is mapped here; an unmapped value renders verbatim, so no hand map
// can silently diverge from the DocType's option set.
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
