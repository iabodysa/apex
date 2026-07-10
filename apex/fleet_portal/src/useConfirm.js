// Copyright (c) 2026, AFMCO and contributors
// Promise-based confirm modal (his cfShow) — an await-able replacement for
// window.confirm so an action can `if (!(await cfShow(...))) return`. `icon` is a
// Lucide icon name rendered by <Icon> in the modal.
import { reactive } from "vue";

export function useConfirm(t) {
  const cf = reactive({
    open: false,
    icon: "triangle-alert",
    title: "",
    msg: "",
    okLabel: "",
    okCls: "btn-blue",
  });
  let cfResolve = null;
  function cfShow(title, msg, icon = "triangle-alert", okLabel = t("confirm.ok"), okCls = "btn-blue") {
    cf.title = title;
    cf.msg = msg;
    cf.icon = icon;
    cf.okLabel = okLabel;
    cf.okCls = okCls;
    cf.open = true;
    return new Promise((resolve) => {
      cfResolve = resolve;
    });
  }
  function cfDo(val) {
    cf.open = false;
    if (cfResolve) {
      cfResolve(val);
      cfResolve = null;
    }
  }
  return { cf, cfShow, cfDo };
}
