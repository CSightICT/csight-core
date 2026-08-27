/**
 * Compile-time convenience aliases sourced from the committed FastAPI OpenAPI
 * snapshot. Runtime decoding remains mandatory for endpoints that intentionally
 * expose loose dict projections (retrieval, grounding, review packets, and PoC
 * reporting while Sprint 5C is landing).
 */
import type { components, paths } from "./openapi.generated";

export type ApiPaths = paths;
export type ApiSchemas = components["schemas"];
export type OpenApiCaseDetail = components["schemas"]["CaseDetailResponse"];
export type OpenApiReviewTask = components["schemas"]["ReviewTaskResponse"];
