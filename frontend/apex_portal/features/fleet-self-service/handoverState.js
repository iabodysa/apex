export function inspectionRowsFromTemplate(items) {
  return (items || []).map((item) => ({
    check_item: String(item?.check_item || "").trim(),
    ok: null,
    default_remark: String(item?.default_remark || ""),
    remark: "",
  }));
}

export function isInspectionComplete(rows) {
  return Boolean(rows?.length) && rows.every((row) => (
    typeof row.ok === "boolean" && (row.ok || String(row.remark || "").trim())
  ));
}

export function buildHandoverPayload(form, checklist, rows) {
  if (!checklist?.template || !Array.isArray(checklist.items) || !checklist.items.length) {
    throw new Error("لا يوجد قالب فحص نشط لهذه العملية.");
  }
  if (!checklist.assignment) {
    throw new Error("تعذّر ربط الفحص بعهدة المركبة. أعد تحميل الصفحة.");
  }
  if (!form?.signed_evidence) {
    throw new Error("أرفق الإثبات الموقّع قبل التأكيد.");
  }
  const odometer = Number(form.odometer);
  if (form.odometer === "" || form.odometer === null || form.odometer === undefined
    || !Number.isFinite(odometer) || odometer < 0) {
    throw new Error("أدخل قراءة عداد صحيحة.");
  }
  if (rows?.length !== checklist.items.length || !isInspectionComplete(rows)) {
    throw new Error("أكمل نتيجة كل بند وأضف ملاحظة لكل بند غير سليم.");
  }
  const inspectionRows = rows.map((row, index) => {
    const expected = String(checklist.items[index]?.check_item || "").trim();
    if (!expected || row.check_item !== expected) {
      throw new Error("تغيّر قالب الفحص. أعد تحميل الصفحة قبل المتابعة.");
    }
    return {
      check_item: row.check_item,
      ok: row.ok ? 1 : 0,
      remark: String(row.remark || "").trim(),
    };
  });
  return {
    assignment: checklist.assignment,
    odometer,
    fuel_level: form.fuel_level || "",
    condition_notes: form.condition_notes || "",
    signed_evidence: form.signed_evidence,
    checklist_template: checklist.template,
    inspection_rows: JSON.stringify(inspectionRows),
  };
}
