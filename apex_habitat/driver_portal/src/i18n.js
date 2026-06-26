// [#7qn779]
import { computed, ref } from "vue";

const STORAGE_KEY = "salis_portal_lang";
export const SUPPORTED = ["en", "ar"];

// [#f0vfv7]
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
      route: "Route",
      vehicle: "Vehicle",
      fuel: "Fuel",
      tickets: "Support",
      profile: "Profile",
    },
    home: {
      vehicle: "Vehicle",
      license: "License",
      quickActions: "Quick actions",
      more: "More",
      attendance: "Attendance",
      myTrips: "My Trips",
      requestFuel: "Request Fuel",
      support: "Support",
      profile: "My Profile",
      myVehicle: "My Vehicle",
      myRoute: "My Route",
      today: "Today",
      checkInNow: "Check in",
      checkOutNow: "Check out",
      doneForToday: "Done for today",
      checkedInAt: "Checked in {time}",
      notCheckedIn: "Not checked in yet",
      nextTrip: "Next trip",
      noTripToday: "No trip scheduled today",
      depart: "Depart",
      return: "Return",
      viewTrip: "View trip",
      alertLicense: "License expires in {n} day(s)",
      alertLicenseExpired: "License expired",
      alertNoVehicle: "No vehicle assigned",
      alertClearance: "Open exit clearance",
    },
    notifications: {
      title: "Notifications",
      empty: "No new notifications",
    },
    route: {
      title: "My Worker Route Today",
      subtitle: "Stops, pickups, and passengers for your route.",
      tripTitle: "Trip Route",
      departs: "Departs",
      expected: "{n} expected",
      stops: "Stops",
      stop: "Stop",
      openMap: "Open map",
      workers: "Workers",
      empty: "No worker trips today",
      emptyHint: "You have no worker pickups scheduled for today.",
      noRoutePlanned: "No route planned for this trip",
      noRoutePlannedHint: "This trip has no route plan yet, so there are no stops to show.",
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
      myRequests: "My Requests",
      fuelRequest: "Fuel Request",
      supportTickets: "Support Tickets",
      documents: "My Documents",
      iqama: "Iqama",
      passport: "Passport",
      docExpiry: "Expiry",
      docNoExpiry: "No expiry on file",
      requestRenewal: "Request renewal",
      renewalSent: "Renewal request sent",
    },
    clearance: {
      title: "Exit Clearance",
      status: "Status",
      reason: "Reason",
      blocked: "Blocked",
      blockedHint: "Resolve the items below to clear.",
      openExceptions: "Open fuel exceptions",
      openRecoveries: "Open cost recoveries",
      vehicleReturned: "Vehicle returned",
      fuelChipReturned: "Fuel chip returned",
      custodyReturned: "Custody returned",
      downloadCertificate: "Download certificate",
      issued: "Cleared",
    },
    vehicle: {
      title: "My Vehicle",
      plate: "Plate",
      category: "Category",
      status: "Status",
      assignmentStart: "Assigned since",
      project: "Project",
      details: "Details",
      odometer: "Odometer",
      km: "km",
      fuelGrade: "Fuel grade",
      compliance: "Documents & Expiry",
      registration: "Registration (Istimara)",
      insurance: "Insurance",
      inspection: "Periodic Inspection (Fahes)",
      noDocNumber: "No number",
      valid: "Valid",
      expiringSoon: "Expires in {n} day(s)",
      expiresToday: "Expires today",
      expired: "Expired",
      expiredAgo: "Expired {n} day(s) ago",
      empty: "No vehicle is assigned to you yet.",
      emptyHint: "Ask your supervisor to assign one.",
      reportProblem: "Report a problem",
      problemSubject: "Vehicle problem",
      problemPlaceholder: "Describe the problem with the vehicle",
      problemSent: "Problem reported",
      cancel: "Cancel",
      send: "Send",
    },
    attendance: {
      title: "Daily Attendance",
      hint: "Record your shift below. We stamp the time for you.",
      checkIn: "Check In",
      checkOut: "Check Out",
      checkedInAt: "Checked in at {time}",
      checkedOutAt: "Checked out at {time}",
      today: "Today",
      notCheckedIn: "Not checked in yet",
      checkedInLabel: "Checked in",
      checkedOutLabel: "Checked out",
      hoursPresent: "Hours present",
      doneForToday: "You're done for today",
      checkInDone: "Checked in. Have a good shift.",
      checkOutDone: "Checked out. See you tomorrow.",
      statusPresent: "Present",
      statusLate: "Late",
      statusAbsent: "Absent",
      statusOnLeave: "On Leave",
      history: "This month",
      historyEmpty: "No attendance recorded this month yet.",
      noTime: "—",
    },
    trips: {
      title: "My Trips Today",
      subtitle: "Your scheduled trips and their status for today.",
      empty: "No trips scheduled",
      emptyHint: "You have nothing on the board today.",
      today: "Today",
      recent: "Recent",
      recentEmpty: "No recent trips",
      recentEmptyHint: "You have no trips in the last 30 days.",
      start: "Start trip",
      complete: "Complete trip",
      started: "Started",
      completed: "Completed",
      startedAt: "Started {time}",
    },
    fuel: {
      title: "Request Fuel",
      litres: "Litres",
      placeholder: "e.g. 40",
      submit: "Submit Request",
      submitted: "Submitted: {name}",
      quota: "This month's quota",
      quotaAllowance: "Allowance",
      quotaConsumed: "Consumed",
      quotaRemaining: "Remaining",
      litreUnit: "L",
      history: "My Requests",
      historyEmpty: "No fuel requests yet",
      historyEmptyHint: "Your fuel requests will appear here.",
      noPlatform: "—",
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
      attachment: "Photo",
      addPhoto: "Add a photo",
      photoAttached: "Photo attached",
      open: "Open ticket",
      detail: "Ticket",
      sla: "Service level",
      respondBy: "Respond by",
      resolveBy: "Resolve by",
      responded: "First responded",
      resolved: "Resolved on",
      conversation: "Conversation",
      noReplies: "No replies yet",
      reply: "Your reply",
      replyPlaceholder: "Type a reply…",
      send: "Send",
      replySent: "Reply sent",
      you: "You",
      raised: "Raised",
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
      afternoon: "نهارك سعيد",
      evening: "مساء الخير",
    },
    nav: {
      home: "الرئيسية",
      attendance: "الحضور",
      trips: "الرحلات",
      route: "المسار",
      vehicle: "المركبة",
      fuel: "الوقود",
      tickets: "الدعم",
      profile: "الملف",
    },
    home: {
      vehicle: "المركبة",
      license: "الرخصة",
      quickActions: "إجراءات سريعة",
      more: "المزيد",
      attendance: "الحضور",
      myTrips: "رحلاتي",
      requestFuel: "طلب وقود",
      support: "الدعم",
      profile: "ملفي الشخصي",
      myVehicle: "مركبتي",
      myRoute: "مساري",
      today: "اليوم",
      checkInNow: "تسجيل الدخول",
      checkOutNow: "تسجيل الخروج",
      doneForToday: "أنهيت يومك",
      checkedInAt: "تم تسجيل الدخول {time}",
      notCheckedIn: "لم يتم تسجيل الدخول بعد",
      nextTrip: "الرحلة التالية",
      noTripToday: "لا توجد رحلة مجدولة اليوم",
      depart: "المغادرة",
      return: "العودة",
      viewTrip: "عرض الرحلة",
      alertLicense: "تنتهي الرخصة خلال {n} يوم",
      alertLicenseExpired: "انتهت الرخصة",
      alertNoVehicle: "لا توجد مركبة مُعيَّنة",
      alertClearance: "إخلاء طرف مفتوح",
    },
    notifications: {
      title: "الإشعارات",
      empty: "لا توجد إشعارات جديدة",
    },
    route: {
      title: "مسار العمال اليوم",
      subtitle: "المحطات ونقاط الالتقاط والركاب لمسارك.",
      tripTitle: "مسار الرحلة",
      departs: "المغادرة",
      expected: "{n} متوقع",
      stops: "المحطات",
      stop: "محطة",
      openMap: "فتح الخريطة",
      workers: "العمال",
      empty: "لا توجد رحلات عمال اليوم",
      emptyHint: "لا توجد لديك عمليات نقل عمال مجدولة لهذا اليوم.",
      noRoutePlanned: "لا يوجد مسار مخطط لهذه الرحلة",
      noRoutePlannedHint: "هذه الرحلة ليس لها خطة مسار بعد، لذا لا توجد محطات لعرضها.",
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
      myRequests: "طلباتي",
      fuelRequest: "طلب بنزين",
      supportTickets: "تذاكر الدعم",
      documents: "وثائقي",
      iqama: "الإقامة",
      passport: "الجواز",
      docExpiry: "الانتهاء",
      docNoExpiry: "لا يوجد تاريخ انتهاء مسجَّل",
      requestRenewal: "طلب تجديد",
      renewalSent: "تم إرسال طلب التجديد",
    },
    clearance: {
      title: "إخلاء الطرف",
      status: "الحالة",
      reason: "السبب",
      blocked: "محظور",
      blockedHint: "عالج البنود أدناه لإتمام الإخلاء.",
      openExceptions: "حالات استثناء وقود مفتوحة",
      openRecoveries: "استردادات تكلفة مفتوحة",
      vehicleReturned: "تم إرجاع المركبة",
      fuelChipReturned: "تم إرجاع بطاقة الوقود",
      custodyReturned: "تم إرجاع العهدة",
      downloadCertificate: "تنزيل الشهادة",
      issued: "تم الإخلاء",
    },
    vehicle: {
      title: "مركبتي",
      plate: "اللوحة",
      category: "الفئة",
      status: "الحالة",
      assignmentStart: "مُعيَّنة منذ",
      project: "المشروع",
      details: "التفاصيل",
      odometer: "العدّاد",
      km: "كم",
      fuelGrade: "نوع الوقود",
      compliance: "الوثائق والانتهاء",
      registration: "الاستمارة",
      insurance: "التأمين",
      inspection: "الفحص الدوري",
      noDocNumber: "بدون رقم",
      valid: "سارية",
      expiringSoon: "تنتهي خلال {n} يوم",
      expiresToday: "تنتهي اليوم",
      expired: "منتهية",
      expiredAgo: "انتهت منذ {n} يوم",
      empty: "لا توجد مركبة مُعيَّنة لك بعد.",
      emptyHint: "اطلب من مشرفك تعيين مركبة.",
      reportProblem: "الإبلاغ عن مشكلة",
      problemSubject: "مشكلة في المركبة",
      problemPlaceholder: "صف المشكلة في المركبة",
      problemSent: "تم الإبلاغ عن المشكلة",
      cancel: "إلغاء",
      send: "إرسال",
    },
    attendance: {
      title: "الحضور اليومي",
      hint: "سجّل ورديتك أدناه. نقوم بتسجيل الوقت نيابةً عنك.",
      checkIn: "تسجيل الدخول",
      checkOut: "تسجيل الخروج",
      checkedInAt: "تم تسجيل الدخول في {time}",
      checkedOutAt: "تم تسجيل الخروج في {time}",
      today: "اليوم",
      notCheckedIn: "لم يتم تسجيل الدخول بعد",
      checkedInLabel: "تم تسجيل الدخول",
      checkedOutLabel: "تم تسجيل الخروج",
      hoursPresent: "ساعات الحضور",
      doneForToday: "أنهيت يومك",
      checkInDone: "تم تسجيل الدخول. نتمنى لك وردية موفقة.",
      checkOutDone: "تم تسجيل الخروج. نراك غداً.",
      statusPresent: "حاضر",
      statusLate: "متأخر",
      statusAbsent: "غائب",
      statusOnLeave: "في إجازة",
      history: "هذا الشهر",
      historyEmpty: "لا يوجد حضور مسجَّل هذا الشهر بعد.",
      noTime: "—",
    },
    trips: {
      title: "رحلاتي اليوم",
      subtitle: "رحلاتك المجدولة وحالتها لهذا اليوم.",
      empty: "لا توجد رحلات مجدولة",
      emptyHint: "لا يوجد لديك شيء على اللوحة اليوم.",
      today: "اليوم",
      recent: "الأخيرة",
      recentEmpty: "لا توجد رحلات حديثة",
      recentEmptyHint: "لا توجد لديك رحلات خلال آخر 30 يوماً.",
      start: "بدء الرحلة",
      complete: "إنهاء الرحلة",
      started: "بدأت",
      completed: "اكتملت",
      startedAt: "بدأت {time}",
    },
    fuel: {
      title: "طلب وقود",
      litres: "اللترات",
      placeholder: "مثال: 40",
      submit: "إرسال الطلب",
      submitted: "تم الإرسال: {name}",
      quota: "حصة هذا الشهر",
      quotaAllowance: "المخصص",
      quotaConsumed: "المستهلك",
      quotaRemaining: "المتبقي",
      litreUnit: "لتر",
      history: "طلباتي",
      historyEmpty: "لا توجد طلبات وقود بعد",
      historyEmptyHint: "ستظهر طلبات الوقود الخاصة بك هنا.",
      noPlatform: "—",
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
      attachment: "صورة",
      addPhoto: "إضافة صورة",
      photoAttached: "تم إرفاق الصورة",
      open: "فتح التذكرة",
      detail: "التذكرة",
      sla: "مستوى الخدمة",
      respondBy: "الرد قبل",
      resolveBy: "الحل قبل",
      responded: "أول رد",
      resolved: "تم الحل في",
      conversation: "المحادثة",
      noReplies: "لا توجد ردود بعد",
      reply: "ردّك",
      replyPlaceholder: "اكتب رداً…",
      send: "إرسال",
      replySent: "تم إرسال الرد",
      you: "أنت",
      raised: "أُنشئت",
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

// Server enum values (DocType Select options / Issue masters) shown in the portal,
// mapped to a localized label per namespace. Stored values stay English for the API
// round-trip; only the displayed label localizes. translateEnum falls back to the raw
// value, so a NEW/renamed option renders English in Arabic mode — test_driver_portal
// _enum_coverage locks every namespace to its live source options so that drift fails
// the build. Keys are the exact stored values.
//   tripStatus    -> Dispatch Trip.status
//   issueStatus   -> Issue.status (native ERPNext)
//   issueCategory -> Issue Type masters (salis_issue_seed)
//   issuePriority -> Issue Priority masters (salis_issue_seed)
//   fuelStatus    -> Fuel Request.status
const enums = {
  en: {
    tripStatus: {
      Planned: "Planned",
      Dispatched: "Dispatched",
      Completed: "Completed",
      Cancelled: "Cancelled",
    },
    issueStatus: {
      Open: "Open",
      Replied: "Replied",
      "On Hold": "On Hold",
      Resolved: "Resolved",
      Closed: "Closed",
    },
    issueCategory: {
      Vehicle: "Vehicle",
      Fuel: "Fuel",
      Attendance: "Attendance",
      Salary: "Salary",
      Other: "Other",
    },
    issuePriority: {
      Low: "Low",
      Medium: "Medium",
      High: "High",
      Urgent: "Urgent",
    },
    fuelStatus: {
      Pending: "Pending",
      Approved: "Approved",
      Done: "Done",
      Failed: "Failed",
      Reverted: "Reverted",
      Cancelled: "Cancelled",
    },
  },
  ar: {
    tripStatus: {
      Planned: "مخططة",
      Dispatched: "منطلقة",
      Completed: "مكتملة",
      Cancelled: "ملغاة",
    },
    issueStatus: {
      Open: "مفتوحة",
      Replied: "تم الرد",
      "On Hold": "معلّقة",
      Resolved: "محلولة",
      Closed: "مغلقة",
    },
    issueCategory: {
      Vehicle: "مركبة",
      Fuel: "وقود",
      Attendance: "حضور",
      Salary: "راتب",
      Other: "أخرى",
    },
    issuePriority: {
      Low: "منخفضة",
      Medium: "متوسطة",
      High: "عالية",
      Urgent: "عاجلة",
    },
    fuelStatus: {
      Pending: "قيد الانتظار",
      Approved: "معتمد",
      Done: "منفَّذ",
      Failed: "فشل",
      Reverted: "مُعاد",
      Cancelled: "ملغى",
    },
  },
};

// The ordered option values per ticket-form dropdown, single-sourced from `enums`
// so the form, the rendered list, and the coverage test never drift apart.
export const ISSUE_CATEGORIES = Object.keys(enums.en.issueCategory);
export const ISSUE_PRIORITIES = Object.keys(enums.en.issuePriority);

function detectInitial() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch (e) {
    // [#9qybx5]
  }
  return "ar"; // drivers default to Arabic (mirrors worker_portal/safety_portal)
}

// [#o7zbpi]
const lang = ref(detectInitial());

function lookup(locale, key) {
  return key.split(".").reduce((o, part) => (o == null ? undefined : o[part]), messages[locale]);
}

function interpolate(str, params) {
  if (!params) return str;
  return str.replace(/\{(\w+)\}/g, (m, k) => (params[k] != null ? params[k] : m));
}

// BCP-47 locale for Intl, keyed to the active UI language. Arabic uses the
// Saudi locale so dates/numbers shape consistently with the rest of the app.
const INTL_LOCALE = { ar: "ar-SA", en: "en-US" };
function intlLocale() {
  return INTL_LOCALE[lang.value] || "en-US";
}

// Locale-aware integer formatting (Intl.NumberFormat). Non-numeric input is
// returned untouched so a server label never breaks the render.
export function fmtNumber(n, opts) {
  if (n == null || n === "" || isNaN(Number(n))) return n;
  return new Intl.NumberFormat(intlLocale(), opts).format(Number(n));
}

// "HH:MM[:SS]" (Frappe Time) -> locale-aware short time. Falls back to the raw
// value when it can't be parsed, so a malformed time never blanks the field.
export function fmtTime(v) {
  if (!v) return "";
  const m = String(v).match(/(\d{1,2}):(\d{2})/);
  if (!m) return String(v);
  const d = new Date();
  d.setHours(Number(m[1]), Number(m[2]), 0, 0);
  return new Intl.DateTimeFormat(intlLocale(), { hour: "2-digit", minute: "2-digit" }).format(d);
}

// "YYYY-MM-DD" -> locale-aware medium date. Returns the raw value on a parse miss.
export function fmtDate(v) {
  if (!v) return "";
  const d = new Date(String(v) + "T00:00:00");
  if (isNaN(d.getTime())) return String(v);
  return new Intl.DateTimeFormat(intlLocale(), { year: "numeric", month: "short", day: "numeric" }).format(d);
}

// [#90zqoh]
export function translate(key, params) {
  const val = lookup(lang.value, key);
  if (val != null) return interpolate(val, params);
  const fallback = lookup("en", key);
  return interpolate(fallback != null ? fallback : key, params);
}

// Localize a stored server enum value; returns the raw value if the namespace or
// key is unknown (so an unmapped option degrades to English, never blanks).
export function translateEnum(namespace, value) {
  if (value == null || value === "") return value;
  const ns = (enums[lang.value] || {})[namespace] || (enums.en || {})[namespace];
  return (ns && ns[value]) != null ? ns[value] : value;
}

export function setLang(next) {
  if (!SUPPORTED.includes(next)) return;
  lang.value = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch (e) {
    // [#p3xobl]
  }
}

const dir = computed(() => (lang.value === "ar" ? "rtl" : "ltr"));

export function useI18n() {
  return {
    t: (key, params) => translate(key, params),
    te: (namespace, value) => translateEnum(namespace, value),
    n: fmtNumber,
    fmtTime,
    fmtDate,
    lang,
    dir,
    setLang,
  };
}
