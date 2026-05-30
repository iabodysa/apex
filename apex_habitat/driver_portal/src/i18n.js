/* Lightweight client i18n for the Salis Driver Portal.
 *
 * The portal carries its OWN translation dictionary here (EN + AR) — it does NOT
 * read Frappe's desk translations (translations/ar.csv). English is the default;
 * the driver picks a language in the header and the choice persists in
 * localStorage. On Arabic the app root flips to dir="rtl" (see App.vue); the
 * design tokens are unchanged — only direction + text differ.
 *
 * Usage (composable):
 *   import { useI18n } from "./i18n";
 *   const { t, lang, dir, setLang } = useI18n();
 *   t("home.title")
 */
import { computed, ref } from "vue";

const STORAGE_KEY = "salis_portal_lang";
export const SUPPORTED = ["en", "ar"];

// Flat, dotted-key dictionaries. Keep EN and AR in lockstep.
const messages = {
  en: {
    common: {
      loading: "Loading…",
      retry: "Retry",
      notAssigned: "Not assigned",
      none: "—",
      error: "Error",
      back: "Back",
      driverPortal: "Driver Portal",
      staff: "Staff",
      goToApp: "Go to the main app",
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
    },
    nav: {
      home: "Home",
      attendance: "Attend",
      trips: "Trips",
      fuel: "Fuel",
      tickets: "Support",
      profile: "Profile",
    },
    home: {
      vehicle: "Vehicle",
      license: "License",
      quickActions: "Quick actions",
      attendance: "Attendance",
      myTrips: "My Trips",
      requestFuel: "Request Fuel",
      support: "Support",
      profile: "My Profile",
      myVehicle: "My Vehicle",
    },
    license: {
      expired: "expired",
      daysLeft: "{n} day(s) left",
    },
    profile: {
      title: "My Profile",
      fullName: "Full name",
      employee: "Employee",
      status: "Status",
      phone: "Phone",
      licenseNumber: "License number",
      licenseExpiry: "License expiry",
      currentVehicle: "Current vehicle",
      project: "Project",
      empty: "Your profile isn't available right now.",
    },
    vehicle: {
      title: "My Vehicle",
      plate: "Plate",
      category: "Category",
      status: "Status",
      assignmentStart: "Assigned since",
      ownership: "Ownership",
      project: "Project",
      empty: "No vehicle is assigned to you yet.",
      emptyHint: "Ask your supervisor to assign one.",
    },
    attendance: {
      title: "Daily Attendance",
      hint: "Record your shift below. We stamp the time for you.",
      checkIn: "Check In",
      checkOut: "Check Out",
      checkedInAt: "Checked in at {time}",
      checkedOutAt: "Checked out at {time}",
    },
    trips: {
      title: "My Trips Today",
      empty: "No trips scheduled",
      emptyHint: "You have nothing on the board today.",
    },
    fuel: {
      title: "Request Fuel",
      litres: "Litres",
      placeholder: "e.g. 40",
      submit: "Submit Request",
      submitted: "Submitted: {name}",
    },
    tickets: {
      title: "Support",
      hint: "Need help? Raise a ticket and the team will follow up.",
      category: "Category",
      priority: "Priority",
      subject: "Subject",
      subjectPlaceholder: "Short summary",
      description: "Description",
      descriptionPlaceholder: "Describe the issue",
      raise: "Raise Ticket",
      myTickets: "My tickets",
      catVehicle: "Vehicle",
      catFuel: "Fuel",
      catAttendance: "Attendance",
      catSalary: "Salary",
      catOther: "Other",
      prioLow: "Low",
      prioMedium: "Medium",
      prioHigh: "High",
      prioUrgent: "Urgent",
    },
    unlinked: {
      staffHint:
        "This mobile portal is for drivers. As staff, use your desk tools below to manage the fleet.",
      hello: "Hello",
      notLinked:
        "Your account isn't linked to a driver profile yet. If you're a driver, ask your supervisor to link your account.",
    },
    errors: {
      loadFailed: "Couldn't load the portal",
    },
  },
  ar: {
    common: {
      loading: "جارٍ التحميل…",
      retry: "إعادة المحاولة",
      notAssigned: "غير مُعيَّن",
      none: "—",
      error: "خطأ",
      back: "رجوع",
      driverPortal: "بوابة السائق",
      staff: "موظف",
      goToApp: "الذهاب إلى التطبيق الرئيسي",
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
    },
    nav: {
      home: "الرئيسية",
      attendance: "الحضور",
      trips: "الرحلات",
      fuel: "الوقود",
      tickets: "الدعم",
      profile: "الملف",
    },
    home: {
      vehicle: "المركبة",
      license: "الرخصة",
      quickActions: "إجراءات سريعة",
      attendance: "الحضور",
      myTrips: "رحلاتي",
      requestFuel: "طلب وقود",
      support: "الدعم",
      profile: "ملفي الشخصي",
      myVehicle: "مركبتي",
    },
    license: {
      expired: "منتهية",
      daysLeft: "متبقٍ {n} يوم",
    },
    profile: {
      title: "ملفي الشخصي",
      fullName: "الاسم الكامل",
      employee: "الموظف",
      status: "الحالة",
      phone: "الهاتف",
      licenseNumber: "رقم الرخصة",
      licenseExpiry: "انتهاء الرخصة",
      currentVehicle: "المركبة الحالية",
      project: "المشروع",
      empty: "ملفك غير متاح حالياً.",
    },
    vehicle: {
      title: "مركبتي",
      plate: "اللوحة",
      category: "الفئة",
      status: "الحالة",
      assignmentStart: "مُعيَّنة منذ",
      ownership: "الملكية",
      project: "المشروع",
      empty: "لا توجد مركبة مُعيَّنة لك بعد.",
      emptyHint: "اطلب من مشرفك تعيين مركبة.",
    },
    attendance: {
      title: "الحضور اليومي",
      hint: "سجّل ورديتك أدناه. نقوم بتسجيل الوقت نيابةً عنك.",
      checkIn: "تسجيل الدخول",
      checkOut: "تسجيل الخروج",
      checkedInAt: "تم تسجيل الدخول في {time}",
      checkedOutAt: "تم تسجيل الخروج في {time}",
    },
    trips: {
      title: "رحلاتي اليوم",
      empty: "لا توجد رحلات مجدولة",
      emptyHint: "لا يوجد لديك شيء على اللوحة اليوم.",
    },
    fuel: {
      title: "طلب وقود",
      litres: "اللترات",
      placeholder: "مثال: 40",
      submit: "إرسال الطلب",
      submitted: "تم الإرسال: {name}",
    },
    tickets: {
      title: "الدعم",
      hint: "تحتاج مساعدة؟ أنشئ تذكرة وسيتابعها الفريق.",
      category: "الفئة",
      priority: "الأولوية",
      subject: "الموضوع",
      subjectPlaceholder: "ملخص قصير",
      description: "الوصف",
      descriptionPlaceholder: "صف المشكلة",
      raise: "إنشاء تذكرة",
      myTickets: "تذاكري",
      catVehicle: "مركبة",
      catFuel: "وقود",
      catAttendance: "حضور",
      catSalary: "راتب",
      catOther: "أخرى",
      prioLow: "منخفضة",
      prioMedium: "متوسطة",
      prioHigh: "عالية",
      prioUrgent: "عاجلة",
    },
    unlinked: {
      staffHint:
        "هذه البوابة المحمولة مخصصة للسائقين. كموظف، استخدم أدوات سطح المكتب أدناه لإدارة الأسطول.",
      hello: "مرحباً",
      notLinked:
        "حسابك غير مرتبط بملف سائق بعد. إذا كنت سائقاً، اطلب من مشرفك ربط حسابك.",
    },
    errors: {
      loadFailed: "تعذّر تحميل البوابة",
    },
  },
};

function detectInitial() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch (e) {
    /* localStorage may be unavailable (private mode); fall back to default */
  }
  return "en";
}

// Module-level singleton so every component shares the same reactive language.
const lang = ref(detectInitial());

function lookup(locale, key) {
  return key.split(".").reduce((o, part) => (o == null ? undefined : o[part]), messages[locale]);
}

function interpolate(str, params) {
  if (!params) return str;
  return str.replace(/\{(\w+)\}/g, (m, k) => (params[k] != null ? params[k] : m));
}

/** Translate a dotted key for the active language, with EN fallback. */
export function translate(key, params) {
  const val = lookup(lang.value, key);
  if (val != null) return interpolate(val, params);
  const fallback = lookup("en", key);
  return interpolate(fallback != null ? fallback : key, params);
}

export function setLang(next) {
  if (!SUPPORTED.includes(next)) return;
  lang.value = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch (e) {
    /* ignore persistence failure — in-memory choice still applies */
  }
}

const dir = computed(() => (lang.value === "ar" ? "rtl" : "ltr"));

export function useI18n() {
  return {
    t: (key, params) => translate(key, params),
    lang,
    dir,
    setLang,
  };
}
