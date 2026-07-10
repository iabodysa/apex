// Copyright (c) 2026, AFMCO and contributors
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
    install: {
      title: "Add to Home Screen",
      body: "Install Salis Driver for quick, full-screen access.",
      manual: "Tap Share, then “Add to Home Screen”.",
      add: "Install",
      dismiss: "Not now",
    },
    offline: {
      banner: "You're offline. Showing saved data; changes are paused.",
      stale: "Offline — showing last saved data.",
    },
    update: {
      available: "A new version is available.",
      reload: "Reload",
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
    push: {
      title: "Background notifications",
      body: "Get a push for new trips and approvals even when the app is closed.",
      enable: "Turn on",
      disable: "Turn off",
      on: "Background notifications are on.",
      off: "Background notifications are off.",
      denied: "Notifications are blocked. Allow them in your browser settings to turn this on.",
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
      callWorker: "Call worker",
      empty: "No worker trips today",
      emptyHint: "You have no worker pickups scheduled for today.",
      noRoutePlanned: "No route planned for this trip",
      noRoutePlannedHint: "This trip has no route plan yet, so there are no stops to show.",
      stopsDone: "{n} of {m} done",
      stopDone: "Mark stop done",
      stopUndo: "Mark stop not done",
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
      more: "More",
      dashboard: "Home dashboard",
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
      lastSite: "Last-known site",
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
      photo: "Shift photo",
      photoAttached: "Photo attached",
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
      boardedOf: "{n} of {m} boarded",
      scanBoarding: "Scan boarding",
      manualBoarding: "Manual boarding",
      fullRoute: "Navigate full route",
      todayTrips: "Today's trips",
      completedTrips: "Completed",
      totalBoarded: "Boarded",
      waitRequestTitle: "Wait request!",
      waitRequestBody: "asks to wait",
      secondsShort: "s",
      defaultWorker: "Worker",
    },
    boarding: {
      title: "Scan boarding pass",
      hint: "Point the camera at the worker's QR boarding pass.",
      cameraDenied: "Camera access is needed to scan. Allow it in your browser, or use manual boarding.",
      unsupported: "Live scanning isn't supported on this device. Use manual boarding instead.",
      starting: "Starting camera…",
      scanning: "Scanning…",
      close: "Close",
      again: "Scan another",
      resultValid: "Boarded",
      resultDuplicate: "Already boarded",
      resultWrongTrip: "Wrong trip",
      resultExpired: "Pass expired",
      resultInvalid: "Invalid pass",
      validHint: "Worker boarded successfully.",
      duplicateHint: "This worker is already aboard this trip.",
      wrongTripHint: "This pass isn't for this trip's manifest.",
      expiredHint: "This pass is past its validity window.",
      invalidHint: "This pass couldn't be verified.",
    },
    manual: {
      title: "Manual boarding",
      hint: "Can't scan? Tick each worker who boarded, then confirm.",
      aboard: "Aboard",
      board: "Board ({n})",
      boarded: "Boarded {n} worker(s)",
      empty: "No workers on this trip's manifest.",
      close: "Close",
    },
    manifest: {
      open: "Boarding",
      title: "Boarding manifest",
      hint: "Workers self-confirm boarding. Tap ✕ on anyone marked aboard by mistake, then depart.",
      empty: "No workers on this trip's boarding list yet.",
      notBoarded: "Not boarded",
      unmarked: "Worker reset to pending",
      workerAboard: "{name} is aboard",
      notify: "Notify remaining",
      notifySoft: "Ping remaining",
      notifyHint: "{n} of {max} reminders sent",
      notifyDone: "Reminder sent to remaining workers",
      notifySoftDone: "Soft ping sent (grace period — no reminder counted yet)",
      graceWaiting: "Grace period — workers are still arriving",
      depart: "Depart & finalize",
      departHint: "Mark exhausted workers absent and close the manifest.",
      departSummary: "{boarded} boarded · {absent} absent · {pending} pending",
      waitRequest: "{name} asks to wait ({n} of {max})",
      close: "Close",
      remaining: "{n} remaining",
    },
    fuel: {
      title: "Request Fuel",
      litres: "Litres",
      placeholder: "e.g. 40",
      submit: "Submit Request",
      submitted: "Submitted: {name}",
      typeStandard: "Standard fuel request",
      typeStandardHint: "This creates a standard request that draws on your monthly quota.",
      approvalThreshold: "Requests over {litres} need approval.",
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
    install: {
      title: "إضافة إلى الشاشة الرئيسية",
      body: "ثبّت تطبيق سائق سالس للوصول السريع بملء الشاشة.",
      manual: "اضغط على مشاركة، ثم «إضافة إلى الشاشة الرئيسية».",
      add: "تثبيت",
      dismiss: "ليس الآن",
    },
    offline: {
      banner: "أنت غير متصل. تُعرض بيانات محفوظة، وتم إيقاف التغييرات مؤقتاً.",
      stale: "غير متصل — تُعرض آخر بيانات محفوظة.",
    },
    update: {
      available: "يتوفّر إصدار جديد.",
      reload: "إعادة التحميل",
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
    push: {
      title: "الإشعارات في الخلفية",
      body: "استلم إشعارًا بالرحلات والموافقات الجديدة حتى عندما يكون التطبيق مغلقًا.",
      enable: "تفعيل",
      disable: "إيقاف",
      on: "تم تفعيل الإشعارات في الخلفية.",
      off: "تم إيقاف الإشعارات في الخلفية.",
      denied: "الإشعارات محظورة. اسمح بها في إعدادات المتصفح لتفعيل هذا الخيار.",
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
      callWorker: "الاتصال بالعامل",
      empty: "لا توجد رحلات عمال اليوم",
      emptyHint: "لا توجد لديك عمليات نقل عمال مجدولة لهذا اليوم.",
      noRoutePlanned: "لا يوجد مسار مخطط لهذه الرحلة",
      noRoutePlannedHint: "هذه الرحلة ليس لها خطة مسار بعد، لذا لا توجد محطات لعرضها.",
      stopsDone: "{n} من {m} مكتملة",
      stopDone: "تحديد المحطة كمكتملة",
      stopUndo: "إلغاء اكتمال المحطة",
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
      more: "المزيد",
      dashboard: "لوحة الرئيسية",
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
      lastSite: "آخر موقع معروف",
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
      photo: "صورة الوردية",
      photoAttached: "تم إرفاق الصورة",
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
      boardedOf: "صعد {n} من {m}",
      scanBoarding: "مسح الصعود",
      manualBoarding: "صعود يدوي",
      fullRoute: "التنقل في كامل المسار",
      todayTrips: "رحلات اليوم",
      completedTrips: "مكتملة",
      totalBoarded: "صعدوا",
      waitRequestTitle: "طلب انتظار!",
      waitRequestBody: "يطلب الانتظار",
      secondsShort: "ث",
      defaultWorker: "موظف",
    },
    boarding: {
      title: "مسح بطاقة الصعود",
      hint: "وجّه الكاميرا إلى رمز QR لبطاقة صعود العامل.",
      cameraDenied: "يلزم الوصول إلى الكاميرا للمسح. اسمح به في المتصفح، أو استخدم الصعود اليدوي.",
      unsupported: "المسح المباشر غير مدعوم على هذا الجهاز. استخدم الصعود اليدوي بدلاً من ذلك.",
      starting: "جارٍ تشغيل الكاميرا…",
      scanning: "جارٍ المسح…",
      close: "إغلاق",
      again: "مسح آخر",
      resultValid: "تم الصعود",
      resultDuplicate: "صعد بالفعل",
      resultWrongTrip: "رحلة خاطئة",
      resultExpired: "انتهت صلاحية البطاقة",
      resultInvalid: "بطاقة غير صالحة",
      validHint: "تم صعود العامل بنجاح.",
      duplicateHint: "هذا العامل على متن هذه الرحلة بالفعل.",
      wrongTripHint: "هذه البطاقة ليست ضمن قائمة هذه الرحلة.",
      expiredHint: "هذه البطاقة تجاوزت مدة صلاحيتها.",
      invalidHint: "تعذّر التحقق من هذه البطاقة.",
    },
    manual: {
      title: "الصعود اليدوي",
      hint: "تعذّر المسح؟ حدّد كل عامل صعد، ثم أكّد.",
      aboard: "على المتن",
      board: "تأكيد الصعود ({n})",
      boarded: "تم صعود {n} عامل",
      empty: "لا يوجد عمال في قائمة هذه الرحلة.",
      close: "إغلاق",
    },
    manifest: {
      open: "الصعود",
      title: "قائمة الصعود",
      hint: "يؤكد العمال صعودهم بأنفسهم. اضغط ✕ على من وُسم على المتن خطأً، ثم غادر.",
      empty: "لا يوجد عمال في قائمة صعود هذه الرحلة بعد.",
      notBoarded: "لم يصعد",
      unmarked: "أُعيد العامل إلى الانتظار",
      workerAboard: "{name} على المتن",
      notify: "تنبيه المتبقّين",
      notifySoft: "تذكير المتبقّين",
      notifyHint: "تم إرسال {n} من {max} تذكير",
      notifyDone: "تم إرسال تذكير للعمال المتبقّين",
      notifySoftDone: "تم إرسال تذكير مبدئي (فترة سماح — لم يُحتسب تذكير بعد)",
      graceWaiting: "فترة سماح — لا يزال العمال في طريقهم",
      depart: "المغادرة والإنهاء",
      departHint: "وسم العمال المتأخّرين كغائبين وإغلاق القائمة.",
      departSummary: "{boarded} على المتن · {absent} غائب · {pending} منتظر",
      waitRequest: "{name} يطلب الانتظار ({n} من {max})",
      close: "إغلاق",
      remaining: "{n} متبقٍ",
    },
    fuel: {
      title: "طلب وقود",
      litres: "اللترات",
      placeholder: "مثال: 40",
      submit: "إرسال الطلب",
      submitted: "تم الإرسال: {name}",
      typeStandard: "طلب وقود قياسي",
      typeStandardHint: "يُنشئ هذا طلباً قياسياً يُخصم من حصتك الشهرية.",
      approvalThreshold: "الطلبات التي تتجاوز {litres} تحتاج إلى موافقة.",
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

// Server enum values (Select options / Issue masters) per namespace -> localized label.
// Stored values stay English for the API round-trip; only the label localizes, and
// translateEnum falls back to the raw value (a new option renders English in Arabic).
// test_driver_portal _enum_coverage locks each namespace to its live source options so
// drift fails the build. Keys are the exact stored values.
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
    boardingStatus: {
      Pending: "Pending",
      "Worker Claimed": "Claimed",
      Boarded: "Aboard",
      "Driver Rejected": "Rejected",
      Absent: "Absent",
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
    boardingStatus: {
      Pending: "بالانتظار",
      "Worker Claimed": "ادّعى الصعود",
      Boarded: "على المتن",
      "Driver Rejected": "مرفوض",
      Absent: "غائب",
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
