// [#h991b9]
import { computed, ref } from "vue";

const STORAGE_KEY = "masar_portal_lang";
export const SUPPORTED = ["en", "ar"];

const messages = {
  en: {
    common: {
      loading: "Loading…",
      retry: "Retry",
      notAssigned: "Not assigned",
      none: "—",
      error: "Something went wrong.",
      workerApp: "Worker App",
      call: "Call",
      whatsapp: "WhatsApp",
      openMap: "Open map",
      close: "Close",
      send: "Send",
      cancel: "Cancel",
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
      profile: "Profile",
      accommodation: "Accommodation",
      transport: "Transport",
      requests: "Requests",
    },
    profile: {
      title: "My Profile",
      employeeNo: "Employee No.",
      designation: "Designation",
      department: "Department",
      project: "Project",
      status: "Status",
      joined: "Joined",
      phone: "Phone",
      documents: "My Documents",
      iqama: "Iqama / Residence ID",
      passport: "Passport",
      expires: "Expires",
      noExpiry: "No expiry on file",
      expired: "Expired",
      daysLeft: "{n} day(s) left",
      requestChange: "Request a data change",
      empty: "Your profile isn't available right now.",
    },
    accommodation: {
      title: "My Accommodation",
      building: "Building",
      room: "Room",
      bed: "Bed",
      floor: "Floor",
      checkIn: "Checked in",
      stayType: "Stay type",
      expectedCheckout: "Expected check-out",
      occupancy: "Occupancy",
      inCharge: "In-charge",
      address: "Address",
      notes: "Notes",
      empty: "You have no active accommodation assignment.",
      emptyHint: "Contact your supervisor if this is wrong.",
      reportIssue: "Report a room issue",
    },
    transport: {
      title: "My Transport",
      pickup: "Pickup",
      pickupPoint: "Pickup point",
      departs: "Departs",
      stops: "Route stops",
      stop: "Stop",
      vehicle: "Vehicle",
      plate: "Plate",
      driver: "Driver",
      status: "Status",
      empty: "No upcoming transport",
      emptyHint: "You have no shuttle scheduled right now.",
      reportIssue: "Report a transport issue",
    },
    requests: {
      title: "My Requests",
      new: "New request",
      category: "Category",
      priority: "Priority",
      subject: "Subject",
      subjectPlaceholder: "Short summary",
      description: "Description",
      descriptionPlaceholder: "Describe your request",
      submit: "Submit request",
      submitted: "Request submitted",
      mine: "My requests",
      empty: "You haven't raised any requests yet.",
      resolution: "Resolution",
      catMaintenance: "Maintenance",
      catCleaning: "Cleaning",
      catAC: "Air Conditioning",
      catPlumbing: "Plumbing",
      catElectrical: "Electrical",
      catWater: "Water",
      catPestControl: "Pest Control",
      catCustody: "Custody / Items",
      catComplaint: "Complaint",
      catSuggestion: "Suggestion",
      catOther: "Other",
      prioLow: "Low",
      prioMedium: "Medium",
      prioHigh: "High",
      prioCritical: "Critical",
      statusNew: "New",
    },
    errors: {
      loadFailed: "Couldn't load Masar",
      loadError: "Couldn't load this section.",
      invalidLink:
        "This worker link is invalid or has been disabled. Please ask your supervisor for a new link.",
      noLink:
        "No worker link was provided. Open the personal link your supervisor shared with you.",
      rateLimited: "Too many requests. Please wait a moment and try again.",
      sessionExpired: "Your session expired. Please refresh the page.",
    },
  },
  ar: {
    common: {
      loading: "جارٍ التحميل…",
      retry: "إعادة المحاولة",
      notAssigned: "غير مُعيَّن",
      none: "—",
      error: "حدث خطأ ما.",
      workerApp: "تطبيق العامل",
      call: "اتصال",
      whatsapp: "واتساب",
      openMap: "فتح الخريطة",
      close: "إغلاق",
      send: "إرسال",
      cancel: "إلغاء",
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
      profile: "ملفي",
      accommodation: "السكن",
      transport: "النقل",
      requests: "الطلبات",
    },
    profile: {
      title: "ملفي الشخصي",
      employeeNo: "الرقم الوظيفي",
      designation: "المسمى الوظيفي",
      department: "القسم",
      project: "المشروع",
      status: "الحالة",
      joined: "تاريخ الالتحاق",
      phone: "الهاتف",
      documents: "مستنداتي",
      iqama: "الإقامة",
      passport: "جواز السفر",
      expires: "تنتهي في",
      noExpiry: "لا يوجد تاريخ انتهاء مسجّل",
      expired: "منتهية",
      daysLeft: "متبقٍ {n} يوم",
      requestChange: "طلب تعديل بيانات",
      empty: "ملفك غير متاح حالياً.",
    },
    accommodation: {
      title: "سكني",
      building: "المبنى",
      room: "الغرفة",
      bed: "السرير",
      floor: "الطابق",
      checkIn: "تاريخ الدخول",
      stayType: "نوع الإقامة",
      expectedCheckout: "تاريخ الخروج المتوقع",
      occupancy: "الإشغال",
      inCharge: "المسؤول",
      address: "العنوان",
      notes: "ملاحظات",
      empty: "لا يوجد لديك سكن مُعيَّن حالياً.",
      emptyHint: "تواصل مع مشرفك إذا كان هذا غير صحيح.",
      reportIssue: "الإبلاغ عن مشكلة في الغرفة",
    },
    transport: {
      title: "نقلي",
      pickup: "الاستلام",
      pickupPoint: "نقطة الاستلام",
      departs: "المغادرة",
      stops: "محطات المسار",
      stop: "محطة",
      vehicle: "المركبة",
      plate: "اللوحة",
      driver: "السائق",
      status: "الحالة",
      empty: "لا يوجد نقل قادم",
      emptyHint: "لا توجد لديك رحلة مجدولة حالياً.",
      reportIssue: "الإبلاغ عن مشكلة في النقل",
    },
    requests: {
      title: "طلباتي",
      new: "طلب جديد",
      category: "الفئة",
      priority: "الأولوية",
      subject: "الموضوع",
      subjectPlaceholder: "ملخص قصير",
      description: "الوصف",
      descriptionPlaceholder: "صِف طلبك",
      submit: "إرسال الطلب",
      submitted: "تم إرسال الطلب",
      mine: "طلباتي",
      empty: "لم تقم بإنشاء أي طلبات بعد.",
      resolution: "المعالجة",
      catMaintenance: "صيانة",
      catCleaning: "نظافة",
      catAC: "تكييف",
      catPlumbing: "سباكة",
      catElectrical: "كهرباء",
      catWater: "مياه",
      catPestControl: "مكافحة حشرات",
      catCustody: "عُهدة / أغراض",
      catComplaint: "شكوى",
      catSuggestion: "اقتراح",
      catOther: "أخرى",
      prioLow: "منخفضة",
      prioMedium: "متوسطة",
      prioHigh: "عالية",
      prioCritical: "حرجة",
      statusNew: "جديد",
    },
    errors: {
      loadFailed: "تعذّر تحميل مسار",
      loadError: "تعذّر تحميل هذا القسم.",
      invalidLink:
        "رابط العامل غير صالح أو تم تعطيله. يرجى طلب رابط جديد من مشرفك.",
      noLink:
        "لم يتم تقديم رابط العامل. افتح الرابط الشخصي الذي شاركه معك مشرفك.",
      rateLimited: "طلبات كثيرة جداً. يرجى الانتظار قليلاً ثم المحاولة مرة أخرى.",
      sessionExpired: "انتهت صلاحية الجلسة. يرجى تحديث الصفحة.",
    },
  },
};

// [#swa23s]
const enums = {
  ar: {
    // [#qtypp3]
    status: {
      Active: "نشط",
      Inactive: "غير نشط",
      Suspended: "موقوف",
      Left: "منتهي الخدمة",
    },
    // [#36b0x4]
    stayType: {
      Permanent: "دائم",
      Temporary: "مؤقت",
    },
    // [#ihaiue]
    requestType: {
      "Accommodation to Project Shuttle": "نقل من السكن إلى المشروع",
      "Inter-City Relocation": "نقل بين المدن",
      "Administrative Trip / Document Signing": "مهمة إدارية / توقيع مستندات",
    },
    // [#b5kbr2]
    transportStatus: {
      New: "جديد",
      Validated: "تم التحقق",
      Approved: "معتمد",
      Scheduled: "مجدول",
      Fulfilled: "مُنفَّذ",
      Rejected: "مرفوض",
      Cancelled: "ملغى",
    },
    // [#5mcbd5]
    requestCategory: {
      Maintenance: "صيانة",
      Safety: "سلامة",
      Cleaning: "نظافة",
      "Pest Control": "مكافحة حشرات",
      Custody: "عُهدة",
      "Facility Item": "عنصر مرفق",
      Water: "مياه",
      Electrical: "كهرباء",
      AC: "تكييف",
      Plumbing: "سباكة",
      Reimbursement: "تعويض",
      Complaint: "شكوى",
      Suggestion: "اقتراح",
      Other: "أخرى",
    },
    // [#lk929b]
    requestStatus: {
      New: "جديد",
      Triaged: "تم الفرز",
      Assigned: "مُسنَد",
      "In Progress": "قيد التنفيذ",
      "Waiting Evidence": "بانتظار إثبات",
      Resolved: "تمت المعالجة",
      Rejected: "مرفوض",
      Closed: "مغلق",
    },
    // [#asri7e]
    priority: {
      Low: "منخفضة",
      Medium: "متوسطة",
      High: "عالية",
      Critical: "حرجة",
    },
  },
};

export function translateEnum(namespace, value) {
  if (value == null || value === "") return value;
  const map = (enums[lang.value] || {})[namespace];
  return (map && map[value]) || value;
}

// [#93umvm]
export function resourceErrorMessage(e, invalidFallbackKey = "errors.loadError") {
  if (!e) return translate(invalidFallbackKey);
  const status = e.response?.status;
  const excType = e.exc_type || "";
  if (status === 429 || excType === "TooManyRequestsError") {
    return translate("errors.rateLimited");
  }
  if (excType.includes("CSRFTokenError") || excType.includes("Authorization")) {
    return translate("errors.sessionExpired");
  }
  return e.messages?.[0] || e.message || translate(invalidFallbackKey);
}

function detectInitial() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch (e) {
    // [#9qybx5]
  }
  return "ar"; // workers default to Arabic
}

const lang = ref(detectInitial());

function lookup(locale, key) {
  return key.split(".").reduce((o, part) => (o == null ? undefined : o[part]), messages[locale]);
}

function interpolate(str, params) {
  if (!params) return str;
  return str.replace(/\{(\w+)\}/g, (m, k) => (params[k] != null ? params[k] : m));
}

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
    // [#l7a9zm]
  }
}

const dir = computed(() => (lang.value === "ar" ? "rtl" : "ltr"));

export function useI18n() {
  return {
    t: (key, params) => translate(key, params),
    tEnum: (namespace, value) => translateEnum(namespace, value),
    lang,
    dir,
    setLang,
  };
}
