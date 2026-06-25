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
      attendance: "Attendance",
      myTrips: "My Trips",
      requestFuel: "Request Fuel",
      support: "Support",
      profile: "My Profile",
      myVehicle: "My Vehicle",
      myRoute: "My Route",
    },
    route: {
      title: "My Worker Route Today",
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
      attendance: "الحضور",
      myTrips: "رحلاتي",
      requestFuel: "طلب وقود",
      support: "الدعم",
      profile: "ملفي الشخصي",
      myVehicle: "مركبتي",
      myRoute: "مساري",
    },
    route: {
      title: "مسار العمال اليوم",
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

// [#90zqoh]
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
    // [#p3xobl]
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
