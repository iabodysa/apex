import { __ } from "../../core/i18n.js";

export function createSingleFlight() {
    const pending = new Map();
    return (key, action) => {
        if (pending.has(key)) return pending.get(key);
        let result;
        try {
            result = action();
        } catch (error) {
            result = Promise.reject(error);
        }
        const request = Promise.resolve(result).finally(() => pending.delete(key));
        pending.set(key, request);
        return request;
    };
}

export function actionAvailability(capability = {}) {
    return {
        disabled: capability.allowed !== true,
        reason: capability.allowed ? "" : capability.reason || __("This action is not available."),
    };
}
