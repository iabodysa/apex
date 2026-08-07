// Copyright (c) 2026, AFMCO and contributors
//
// Strings every portal says the same way, written once.
//
// These are the messages about the CONNECTION and the SESSION — the ones that have
// nothing to do with what a given portal is for. Seven portals had written them
// separately and they had drifted: the same rate-limit refusal existed in two wordings
// and the same expired-session notice in two, so one operator was told "please refresh
// the page" and another "please reload the page" by the same product.
//
// A portal that genuinely needs its own wording still wins — createI18n consults the
// portal's own messages first and only falls through to here. That matters, because
// most keys shared across portals SHOULD differ: `boarding.hint` tells the driver to
// point the camera at a worker's pass and tells the worker to show theirs, and
// collapsing those two into one sentence would be the real defect. Only put a string
// here when every portal means exactly the same thing by it.

export const SHARED_MESSAGES = {
  en: {
    common: {
      error: "Something went wrong.",
    },
    errors: {
      rateLimited: "Too many requests. Please wait a moment and try again.",
      sessionExpired: "Your session expired. Please refresh the page.",
      loadError: "Couldn't load this section.",
    },
  },
  ar: {
    common: {
      error: "حدث خطأ ما.",
    },
    errors: {
      rateLimited: "طلبات كثيرة جداً. يرجى الانتظار قليلاً ثم المحاولة مرة أخرى.",
      sessionExpired: "انتهت صلاحية الجلسة. يرجى تحديث الصفحة.",
      loadError: "تعذّر تحميل هذا القسم.",
    },
  },
};

// Deliberately NOT here, and the reason is worth keeping. `errors.retryHint` looked
// universal — three portals said a version of "check your connection" — but Housing
// says "Check the connection, then load the list again", which is better advice on a
// list screen than the generic sentence. A key belongs above only when no portal has a
// reason to say it differently; one portal with a good reason is enough to keep it out.
