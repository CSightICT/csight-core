/// <reference types="vite/client" />
// Build-time opt-in. The server independently enforces the local-only scope.
export const internalFeedbackEnabled = import.meta.env.VITE_INTERNAL_MODEL_FEEDBACK === "true";
