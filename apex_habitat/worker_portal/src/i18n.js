// [#h991b9]
import { computed, ref } from "vue";

const STORAGE_KEY = "masar_portal_lang";
export const SUPPORTED = ["en", "ar"];

const messages = {
  en: {
    common: {
      loading: "Loading…",
      retry: "Retry",
      offline: "You're offline — showing last known info.",
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
      home: "Home",
      profile: "Profile",
      accommodation: "Accommodation",
      transport: "Transport",
      custody: "Custody",
      requests: "Requests",
    },
    home: {
      title: "Today",
      nextRide: "Next ride",
      noRide: "No upcoming ride.",
      today: "Today",
      inHm: "in {h}h {m}m",
      inM: "in {m}m",
      now: "Now",
      openRequests: "Open requests",
      tileNextRide: "Next ride",
      tileIqama: "Iqama",
      daysShort: "{n}d",
      expiredShort: "Expired",
      bed: "Bed",
      alerts: "Documents to renew",
      alertExpired: "Expired",
      alertDaysLeft: "{n} day(s) left",
      notifyHr: "Notify HR",
      notifyHrSending: "Notifying…",
      notifyHrDone: "HR notified",
      notifyHrFailed: "Couldn't notify HR. Please try again.",
    },
    contacts: {
      title: "My Contacts",
      buildingInCharge: "Building in-charge",
      todayDriver: "Today's driver",
      housingOffice: "Housing office",
      empty: "No contacts available right now.",
    },
    profile: {
      title: "My Profile",
      more: "More",
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
      emptyHint: "Try reopening your link, or ask your supervisor.",
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
    custody: {
      title: "My Custody",
      qty: "Quantity",
      building: "Building",
      receivedDate: "Received on",
      issuedBy: "Issued by",
      acknowledge: "Acknowledge receipt",
      empty: "You hold no custody items.",
      emptyHint: "Items issued to you will appear here.",
    },
    transport: {
      title: "My Transport",
      pickup: "Pickup",
      pickupPoint: "Pickup point",
      departs: "Departs",
      stops: "Route stops",
      stop: "Stop",
      noRoutePlanned: "No route planned for this trip yet — no stops to show.",
      vehicle: "Vehicle",
      plate: "Plate",
      driver: "Driver",
      status: "Status",
      empty: "No upcoming transport",
      emptyHint: "You have no shuttle scheduled right now.",
      past: "Past trips",
      reportIssue: "Report a transport issue",
      atPickup: "I'm at the pickup",
      atPickupSending: "Confirming…",
      atPickupDone: "Boarding confirmed",
      atPickupFailed: "Couldn't confirm. Please try again.",
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
      emptyHint: "Use the form above to raise your first request.",
      resolution: "Resolution",
      issueLocation: "Where is the issue?",
      issueLocationNone: "Not specified",
      prefLang: "Preferred contact language",
      photo: "Photo (optional)",
      photoAdd: "Add a photo",
      photoChange: "Change photo",
      photoRemove: "Remove",
      photoTooLarge: "That photo is too large. Please pick one under 8 MB.",
      locRoom: "Room",
      locBathroom: "Bathroom",
      locKitchen: "Kitchen",
      locCommonArea: "Common area",
      locEntrance: "Entrance",
      locStaircase: "Staircase",
      locExternalArea: "External area",
      locOther: "Other",
      langEnglish: "English",
      langArabic: "Arabic",
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
      back: "Back to requests",
      detailTitle: "Request details",
      reference: "Reference",
      timeline: "Status timeline",
      timelineCreated: "Request raised",
      timelineCurrent: "Current status",
      timelineClosed: "Request closed",
      details: "Details",
      location: "Location",
      triage: "Triage notes",
      noTriage: "No triage notes yet.",
      noResolution: "No resolution notes yet.",
      attachment: "Attachment",
      viewAttachment: "View attachment",
      notFound: "This request couldn't be found.",
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
      offline: "أنت دون اتصال — نعرض آخر معلومة معروفة.",
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
      home: "الرئيسية",
      profile: "ملفي",
      accommodation: "السكن",
      transport: "النقل",
      custody: "العهدة",
      requests: "الطلبات",
    },
    home: {
      title: "اليوم",
      nextRide: "الرحلة القادمة",
      noRide: "لا توجد رحلة قادمة.",
      today: "اليوم",
      inHm: "خلال {h} س {m} د",
      inM: "خلال {m} د",
      now: "الآن",
      openRequests: "طلبات مفتوحة",
      tileNextRide: "الرحلة القادمة",
      tileIqama: "الإقامة",
      daysShort: "{n} يوم",
      expiredShort: "منتهية",
      bed: "السرير",
      alerts: "مستندات بحاجة للتجديد",
      alertExpired: "منتهية",
      alertDaysLeft: "متبقٍ {n} يوم",
      notifyHr: "إبلاغ الموارد البشرية",
      notifyHrSending: "جارٍ الإبلاغ…",
      notifyHrDone: "تم إبلاغ الموارد البشرية",
      notifyHrFailed: "تعذّر إبلاغ الموارد البشرية. حاول مرة أخرى.",
    },
    contacts: {
      title: "جهات الاتصال",
      buildingInCharge: "مسؤول المبنى",
      todayDriver: "سائق اليوم",
      housingOffice: "مكتب الإسكان",
      empty: "لا توجد جهات اتصال متاحة حالياً.",
    },
    profile: {
      title: "ملفي الشخصي",
      more: "المزيد",
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
      emptyHint: "أعد فتح رابطك، أو تواصل مع مشرفك.",
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
    custody: {
      title: "عهدتي",
      qty: "الكمية",
      building: "المبنى",
      receivedDate: "تاريخ الاستلام",
      issuedBy: "سُلِّمت بواسطة",
      acknowledge: "تأكيد الاستلام",
      empty: "لا توجد لديك عُهدة حالياً.",
      emptyHint: "ستظهر هنا الأصناف المسلَّمة إليك.",
    },
    transport: {
      title: "نقلي",
      pickup: "الاستلام",
      pickupPoint: "نقطة الاستلام",
      departs: "المغادرة",
      stops: "محطات المسار",
      stop: "محطة",
      noRoutePlanned: "هذه الرحلة ليس لها خطة مسار بعد، فلا محطات لعرضها.",
      vehicle: "المركبة",
      plate: "اللوحة",
      driver: "السائق",
      status: "الحالة",
      empty: "لا يوجد نقل قادم",
      emptyHint: "لا توجد لديك رحلة مجدولة حالياً.",
      past: "رحلات سابقة",
      reportIssue: "الإبلاغ عن مشكلة في النقل",
      atPickup: "أنا عند نقطة الاستلام",
      atPickupSending: "جارٍ التأكيد…",
      atPickupDone: "تم تأكيد الركوب",
      atPickupFailed: "تعذّر التأكيد. حاول مرة أخرى.",
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
      emptyHint: "استخدم النموذج بالأعلى لرفع أوّل طلب.",
      resolution: "المعالجة",
      issueLocation: "أين توجد المشكلة؟",
      issueLocationNone: "غير محدد",
      prefLang: "لغة التواصل المفضلة",
      photo: "صورة (اختياري)",
      photoAdd: "إضافة صورة",
      photoChange: "تغيير الصورة",
      photoRemove: "إزالة",
      photoTooLarge: "حجم الصورة كبير جداً. يرجى اختيار صورة أقل من 8 ميجابايت.",
      locRoom: "الغرفة",
      locBathroom: "دورة المياه",
      locKitchen: "المطبخ",
      locCommonArea: "منطقة مشتركة",
      locEntrance: "المدخل",
      locStaircase: "الدرج",
      locExternalArea: "منطقة خارجية",
      locOther: "أخرى",
      langEnglish: "الإنجليزية",
      langArabic: "العربية",
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
      back: "العودة إلى الطلبات",
      detailTitle: "تفاصيل الطلب",
      reference: "المرجع",
      timeline: "مسار الحالة",
      timelineCreated: "تم إنشاء الطلب",
      timelineCurrent: "الحالة الحالية",
      timelineClosed: "تم إغلاق الطلب",
      details: "التفاصيل",
      location: "الموقع",
      triage: "ملاحظات الفرز",
      noTriage: "لا توجد ملاحظات فرز بعد.",
      noResolution: "لا توجد ملاحظات معالجة بعد.",
      attachment: "المرفق",
      viewAttachment: "عرض المرفق",
      notFound: "تعذّر العثور على هذا الطلب.",
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
    // [#t322il]
    issueLocation: {
      Room: "الغرفة",
      Bathroom: "دورة المياه",
      Kitchen: "المطبخ",
      "Common Area": "منطقة مشتركة",
      Entrance: "المدخل",
      Staircase: "الدرج",
      "External Area": "منطقة خارجية",
      Other: "أخرى",
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
