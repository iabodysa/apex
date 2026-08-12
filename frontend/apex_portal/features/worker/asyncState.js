import { reactive, ref } from "vue";

export function createDraftAction(initial) {
  const draft = reactive({ ...initial });
  const state = ref("ready");
  const error = ref("");

  async function submit(operation) {
    state.value = "saving";
    error.value = "";
    try {
      const result = await operation({ ...draft });
      state.value = "saved";
      return result;
    } catch (reason) {
      state.value = "error";
      error.value = reason?.message || "تعذّر الحفظ. حاول مرة أخرى.";
      return undefined;
    }
  }

  return { draft, state, error, submit };
}
